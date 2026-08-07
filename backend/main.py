from __future__ import annotations

import json
import mimetypes
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from backend.config import FRONTEND_DIR, HOST, PORT, AGENT_ROUTER_API_KEY
from backend.connectors.alforaij import load_listings
from backend.connectors.live_sources import search_external_sources
from backend.services.deduplication import deduplicate_ranked
from backend.services.matching import top_matches
from backend.services.report_generator import build_report
from backend.services.request_parser import parse_request
from backend.services.source_registry import source_registry
from backend.services.supabase_store import is_configured as supabase_is_configured
from backend.services.supabase_store import persist_analysis
from backend.services.valuation import enrich_rankings


from backend.services.ai_evaluator import generate_professional_analysis

# ذاكرة مؤقتة للفرص (تُحدَّث أول بأول): تُبنى عند أول طلب وتُعاد لفترة قصيرة
import threading as _threading

_OPPORTUNITIES_LOCK = _threading.Lock()
_OPPORTUNITIES_CACHE: dict | None = None
_OPPORTUNITIES_PREVIOUS: dict | None = None  # اللقطة السابقة للمقارنة (تنبيهات واتساب)
_OPPORTUNITIES_CACHE_AT = 0.0
_OPPORTUNITIES_TTL_SECONDS = 300


def json_response(handler: BaseHTTPRequestHandler, payload: dict, status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            listings = load_listings()
            json_response(self, {
                "status": "ok",
                "records": len(listings),
                "supabase": supabase_is_configured(),
                "aiAnalysis": bool(AGENT_ROUTER_API_KEY),
            })
            return
        if path == "/api/sources":
            json_response(self, {"sources": source_registry()})
            return
        if path == "/api/opportunities":
            import time
            from urllib.parse import parse_qs
            from backend.services.opportunities import build_opportunities
            from backend.services.supabase_store import save_opportunities

            params = parse_qs(urlparse(self.path).query)
            force_refresh = params.get("refresh", ["0"])[0] == "1"
            now = time.time()
            global _OPPORTUNITIES_CACHE, _OPPORTUNITIES_CACHE_AT, _OPPORTUNITIES_PREVIOUS
            stale = _OPPORTUNITIES_CACHE is None or now - _OPPORTUNITIES_CACHE_AT > _OPPORTUNITIES_TTL_SECONDS
            if not stale and not force_refresh:
                json_response(self, _OPPORTUNITIES_CACHE)
                return
            with _OPPORTUNITIES_LOCK:
                try:
                    # الفحص الحي للمصادر الخارجية فقط عند طلب صريح (?refresh=1) أو أول بناء
                    # حتى لا يتكرر سحب المواقع كل دقائق (حماية من الحظر/Rate limiting)
                    include_external = force_refresh or _OPPORTUNITIES_CACHE is None
                    snapshot = build_opportunities(include_external=include_external)
                    if _OPPORTUNITIES_CACHE is not None and snapshot.get("generatedAt") != _OPPORTUNITIES_CACHE.get("generatedAt"):
                        _OPPORTUNITIES_PREVIOUS = _OPPORTUNITIES_CACHE
                    _OPPORTUNITIES_CACHE = snapshot
                    _OPPORTUNITIES_CACHE_AT = time.time()
                    try:
                        save_opportunities(snapshot)
                    except Exception as exc:
                        print(f"Supabase opportunities save skipped: {exc}")
                except Exception as exc:
                    import traceback
                    traceback.print_exc()
                    # احتياط: عرض آخر لقطة محفوظة في Supabase بدل فشل الطلب
                    from backend.services.supabase_store import fetch_latest_opportunities
                    fallback = fetch_latest_opportunities()
                    if fallback:
                        _OPPORTUNITIES_CACHE = fallback
                        _OPPORTUNITIES_CACHE_AT = time.time()
                        json_response(self, fallback)
                        return
                    json_response(self, {"error": "Opportunities build failed", "detail": str(exc)}, status=500)
                    return
            json_response(self, _OPPORTUNITIES_CACHE)
            return
        if path == "/api/opportunities/history":
            # أرشفة وتتبع أداء الفرص عبر اللقطات المحفوظة في Supabase (أقدم → أحدث)
            from backend.services.opportunities import build_history_series
            from backend.services.supabase_store import fetch_opportunity_snapshots
            try:
                snapshots = fetch_opportunity_snapshots(limit=100)
                snapshots.reverse()  # أقدم أولًا كما يتوقع build_history_series
                json_response(self, build_history_series(snapshots))
            except Exception as exc:
                import traceback
                traceback.print_exc()
                json_response(self, {"error": "History build failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/whatsapp-alerts":
            # تنبيهات واتساب: مقارنة آخر لقطتين (الحالية مقابل السابقة) لكل عميل مطابق
            from backend.services.opportunities import build_whatsapp_alerts
            from backend.services.supabase_store import fetch_opportunity_snapshots

            def _generated(snap):
                # اللقطات في الذاكرة تستخدم generatedAt، وصفوف Supabase تستخدم generated_at
                return snap.get("generatedAt") or snap.get("generated_at") or ""

            try:
                snapshots = fetch_opportunity_snapshots(limit=3)
                previous = _OPPORTUNITIES_PREVIOUS
                current = _OPPORTUNITIES_CACHE
                if snapshots:
                    newest = snapshots[0]
                    current = current or newest
                    if len(snapshots) >= 2 and (not previous or _generated(previous) == _generated(current)):
                        previous = snapshots[1]
                json_response(self, build_whatsapp_alerts(previous, current or {}))
            except Exception as exc:
                import traceback
                traceback.print_exc()
                json_response(self, {"error": "WhatsApp alerts build failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/clients":
            # قائمة العملاء المحتملين: ملف CSV + قاعدة Supabase مدمجة + روابط واتساب جاهزة
            from backend.services.opportunities import _load_clients, normalize_phone
            try:
                clients = _load_clients()
                for client in clients:
                    wa_links = []
                    for part in re.split(r"[|،,]+", str(client.get("phones") or "")):
                        normalized = normalize_phone(part)
                        if normalized:
                            wa_links.append(f"https://wa.me/{normalized}")
                    client["waLinks"] = wa_links
                json_response(self, {"count": len(clients), "clients": clients})
            except Exception as exc:
                json_response(self, {"error": "Clients load failed", "detail": str(exc)}, status=500)
            return
        if path == "/":
            path = "/index.html"
        file_path = (FRONTEND_DIR / path.lstrip("/")).resolve()
        if not str(file_path).startswith(str(FRONTEND_DIR.resolve())) or not file_path.exists():
            self.send_error(404)
            return
        body = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", mimetypes.guess_type(str(file_path))[0] or "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        # منع المتصفح من استخدام نسخة قديمة مخزنة من ملفات الواجهة
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(body or "{}")
        except json.JSONDecodeError:
            json_response(self, {"error": "Invalid JSON"}, status=400)
            return
        path = urlparse(self.path).path
        text = str(payload.get("text") or "")
        if path == "/api/parse":
            json_response(self, {"request": parse_request(text).__dict__})
            return
        if path == "/api/analyze":
            try:
                request = parse_request(text)
                if payload.get("mode") in {"search", "valuation", "search_and_value"}:
                    request.intent = str(payload["mode"])
                listings = load_listings()
                local_count = len(listings)
                external_statuses = []
                if payload.get("includeExternal", True):
                    external_listings, external_statuses = search_external_sources(request)
                    listings.extend(external_listings)
                ranked = top_matches(request, listings, limit=40)
                enriched = enrich_rankings(request, ranked, listings)
                deduped = deduplicate_ranked(enriched)[:20]
                
                # Fetch AI professional analysis
                ai_insights = generate_professional_analysis(request, deduped, external_statuses)
                
                report = build_report(request, deduped, local_count, external_statuses, ai_insights)
                try:
                    report["persistence"] = persist_analysis(request, report, report["sourceStatus"])
                except Exception as persist_error:
                    report["persistence"] = {
                        "enabled": supabase_is_configured(),
                        "status": "failed",
                        "error": str(persist_error),
                    }
                json_response(self, report)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                json_response(self, {"error": "Analysis failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/report-pdf":
            try:
                from backend.services.pdf_report import build_pdf
                pdf_bytes = build_pdf(payload.get("report") or {})
                self.send_response(200)
                self.send_header("Content-Type", "application/pdf")
                self.send_header("Content-Disposition", 'attachment; filename="alforaij-report.pdf"')
                self.send_header("Content-Length", str(len(pdf_bytes)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(pdf_bytes)
            except Exception as exc:
                import traceback
                traceback.print_exc()
                json_response(self, {"error": "PDF generation failed", "detail": str(exc)}, status=500)
            return
        if path == "/api/clients":
            # إضافة/تحديث عميل محتمل: يُحفظ في Supabase (إن مضبوط) + الملف المحلي دائمًا
            from backend.services.opportunities import append_csv_client
            from backend.services.supabase_store import save_client as supabase_save_client
            try:
                result = append_csv_client(payload)
                supabase_status = "skipped"
                if supabase_is_configured():
                    try:
                        supabase_save_client(payload)
                        supabase_status = "saved"
                    except Exception as exc:
                        supabase_status = f"failed: {exc}"
                json_response(self, {"status": result.get("status"), "code": result.get("code"), "supabase": supabase_status})
            except Exception as exc:
                json_response(self, {"error": "Client save failed", "detail": str(exc)}, status=500)
            return
        json_response(self, {"error": "Unknown endpoint"}, status=404)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Alforaij Research Assistant running on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
