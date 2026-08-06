from __future__ import annotations

import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from backend.config import FRONTEND_DIR, HOST, PORT
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
            json_response(self, {"status": "ok", "records": len(listings), "supabase": supabase_is_configured()})
            return
        if path == "/api/sources":
            json_response(self, {"sources": source_registry()})
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
        json_response(self, {"error": "Unknown endpoint"}, status=404)

    def log_message(self, format: str, *args) -> None:
        return


def main() -> None:
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    print(f"Alforaij Research Assistant running on http://{HOST}:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    main()
