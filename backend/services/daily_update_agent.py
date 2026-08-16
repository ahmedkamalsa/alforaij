from __future__ import annotations

import json
import logging
import os
import tempfile
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from backend.config import load_local_env
from backend.connectors.alforaij import load_listings
from backend.services.developments_agent import discover_market_developments, save_developments_local
from backend.services.official_source_agent import check_candidate_platforms, check_official_reference_sources
from backend.services.opportunities import build_opportunities
from backend.services.source_registry import source_registry, sync_remote_registry as sync_source_registry
from backend.services.supabase_store import (
    dedupe_market_listings,
    fetch_latest_opportunities,
    is_configured,
    mark_stale_market_listings,
    save_listings,
    save_market_developments,
    save_market_listings,
    save_official_transactions,
    save_opportunities,
    save_price_trends,
    supabase_data_summary,
)
from backend.services.update_notifications import build_update_notifications, save_update_notifications
from scripts.import_official_transactions import normalize, read_file

ROOT = Path(__file__).resolve().parents[2]
STATUS_FILE = ROOT / "data" / "daily_agent_status.json"


def _write_status(status: dict[str, Any]) -> None:
    STATUS_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATUS_FILE.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")


def _median(values: list[float]) -> float | None:
    """وسيط قائمة أرقام (مقربًا لمنزلة واحدة) أو None عند الفراغ."""
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return round(ordered[middle], 1)
    return round((ordered[middle - 1] + ordered[middle]) / 2, 1)


def _build_price_trends(external_rows: list[dict[str, Any]], local_listings: list[Any]) -> list[dict[str, Any]]:
    """حساب اتجاهات الأسعار الشهرية من الحصاد + الإعلانات المحلية.

    يجمع كل الإعلانات التي تحمل سعرًا صالحًا في خلايا (منطقة × نوع × شهر × معاملة)
    ويحسب وسيط السعر الإجمالي ووسيط سعر المتر (حيثما وُجدت المساحة). شهر كل
    إعلان = fetched_at (للحصاد) أو published_date (للمحلي) بصيغة YYYY-MM.
    يعيد صفوفًا جاهزة للحفظ في price_trends (upsert على الخلية).
    """
    buckets: dict[tuple[str, str, str, str], dict[str, list[float]]] = {}

    def _month_of(fetched_at: Any, published_date: Any) -> str:
        raw = str(fetched_at or published_date or "")
        month = raw[:7]
        if len(month) == 7 and month[:4].isdigit() and month[5:7].isdigit():
            return month
        return datetime.now().strftime("%Y-%m")

    def _add(row: dict[str, Any], *, use_fetched: bool) -> None:
        try:
            price = float(row.get("price"))
        except (TypeError, ValueError):
            return
        if not price or price <= 0:
            return
        area = str(row.get("area") or "").strip()
        if not area:
            return
        property_type = str(row.get("property_type") or "").strip()
        transaction = str(row.get("transaction") or "").strip() or "للبيع"
        month = _month_of(
            row.get("fetched_at") if use_fetched else row.get("published_date"),
            row.get("published_date"),
        )
        key = (area, property_type, month, transaction)
        bucket = buckets.setdefault(key, {"prices": [], "per_m2": []})
        bucket["prices"].append(price)
        try:
            space = float(row.get("space"))
            if space and space > 0:
                bucket["per_m2"].append(price / space)
        except (TypeError, ValueError):
            pass

    for row in external_rows:
        _add(row, use_fetched=True)
    for listing in local_listings:
        _add(getattr(listing, "__dict__", listing), use_fetched=False)

    rows = []
    for (area, property_type, month, transaction), bucket in buckets.items():
        rows.append({
            "area": area,
            "property_type": property_type,
            "month": month,
            "transaction": transaction,
            "median_price": _median(bucket["prices"]),
            "median_price_per_m2": _median(bucket["per_m2"]),
            "sample_count": len(bucket["prices"]),
        })
    rows.sort(key=lambda row: (row["area"], row["month"]))
    return rows


def load_daily_agent_status() -> dict[str, Any]:
    if not STATUS_FILE.exists():
        return {
            "agent": "daily_data_update_agent",
            "status": "not_run",
            "startedAt": "",
            "finishedAt": "",
            "steps": [],
            "summary": {},
            "error": "",
        }
    try:
        return json.loads(STATUS_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "agent": "daily_data_update_agent",
            "status": "status_file_error",
            "startedAt": "",
            "finishedAt": "",
            "steps": [],
            "summary": {},
            "error": str(exc),
        }


def _download_source(url: str) -> Path:
    suffix = ".json" if ".json" in url.lower() else ".csv"
    target = Path(tempfile.gettempdir()) / f"alforaij_official_transactions{suffix}"
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 alforaij-research-assistant/1.0",
            "Accept": "text/csv,application/json,*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=45) as response:
        target.write_bytes(response.read())
    return target


def _import_official(source: str) -> dict[str, Any]:
    if not source:
        return {
            "status": "skipped",
            "count": 0,
            "note": "لا يوجد مصدر صفقات رسمي مضبوط لهذا التشغيل.",
        }
    path = _download_source(source) if source.lower().startswith(("http://", "https://")) else Path(source)
    if not path.is_absolute():
        path = ROOT / path
    if not path.exists():
        return {"status": "missing", "count": 0, "note": f"ملف الصفقات غير موجود: {path}"}
    rows = normalize(read_file(path))
    if not rows:
        return {"status": "empty", "count": 0, "note": "الملف موجود لكن لا يحتوي صفقات صالحة."}
    save_official_transactions(rows)
    return {"status": "saved", "count": len(rows), "source": str(path)}


def run_daily_update_agent(
    *,
    official_source: str = "",
    include_external: bool = True,
) -> dict[str, Any]:
    """وكيل تحديث يومي كامل: مصادر، صفقات، تقييم، فرص، إشعارات، وحالة تشغيل."""
    load_local_env()
    started = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
    steps: list[dict[str, Any]] = []
    status = {
        "agent": "daily_data_update_agent",
        "status": "running",
        "startedAt": started,
        "finishedAt": "",
        "steps": steps,
        "summary": {},
        "error": "",
    }
    _write_status(status)

    def step(name: str, result: dict[str, Any] | None = None, state: str = "ok") -> None:
        steps.append({"name": name, "status": state, "result": result or {}})
        status["steps"] = steps
        _write_status(status)

    try:
        if not is_configured():
            raise RuntimeError("Supabase is not configured. Add SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY to .env.")

        source_count = len(source_registry())
        sync_result = sync_source_registry()
        # المزامنة تعيد ملخصًا بالعدد وتقرير الانجراف (مصادر محلية غير مسجلة في
        # الجدول الحي) — يظهر في حالة الوكيل اليومي بدل أن يتحول لاحقًا إلى
        # فشل صامت عند حفظ source_runs (قيد المفتاح الأجنبي يوقف الدفعة كاملة).
        step("sync_source_registry", sync_result if isinstance(sync_result, dict) else {"count": source_count})

        reference_sources = check_official_reference_sources(timeout=8)
        step("check_official_reference_sources", {
            "count": reference_sources.get("count"),
            "reachable": reference_sources.get("reachable"),
        })

        # المنصات المرشحة (Property Finder / Aqarmap / Bayut / بوابة الكويت العقارية /
        # Kuwait Finder): فحص يومي لتوفرها — بمجرد أن تصبح أي منصة قابلة للقراءة يبدأ
        # موصلها في إسهام بياناتها بالبحث والتقييم وقاعدة المعرفة، واليوم تُسجَّل
        # حالتها الحقيقية بشفافية دون إسقاط بقية المصادر.
        candidate_platforms = check_candidate_platforms(timeout=8)
        step("check_candidate_platforms", {
            "count": candidate_platforms.get("count"),
            "reachable": candidate_platforms.get("reachable"),
            "blocked": candidate_platforms.get("blocked"),
        })

        listings = load_listings()
        save_listings(listings)
        step("sync_local_listings", {"count": len(listings)})

        source = official_source.strip() or os.getenv("OFFICIAL_TRANSACTIONS_SOURCE", "").strip()
        official_result = _import_official(source)
        step("import_official_transactions", official_result, "ok" if official_result.get("status") == "saved" else "needs_source")

        previous_snapshot = fetch_latest_opportunities()
        snapshot = build_opportunities(include_external=include_external, return_external=True)
        # قاعدة المعرفة: حفظ إعلانات السوق الخارجية المحصودة في market_listings
        # (مثل بيانات الفريج المحلية تمامًا) حتى تتراكم كل إعلانات المواقع في القاعدة
        # وتصبح أساس التحليلات الدقيقة — بلا اعتماد على الفحص الحي لحظة الطلب فقط.
        # تُستبعد صفوف المراجع (مؤشرات رسمية OFFIND-*) لأنها أسعار متر مرجعية لا إعلانات.
        external_rows = [
            row
            for row in snapshot.pop("externalListings", [])
            if not str(row.get("code") or "").startswith("OFFIND")
            and "مؤشرات" not in str(row.get("source") or "")
        ]
        save_opportunities(snapshot)
        step("build_and_save_opportunities", {"totalScored": snapshot.get("totalScored", 0), "includeExternal": include_external})

        harvest = save_market_listings(external_rows)
        step(
            "persist_market_listings",
            harvest,
            "ok" if harvest.get("status") in ("saved", "empty", "not_configured") else "needs_table",
        )

        # كسح الإعلانات القديمة/المباعة: يوسم stale كل إعلان لم يُرَ منذ 14 يومًا
        # (يبقى في قاعدة المعرفة للتاريخ ولا يُعرض في اللوحة/الفرص/المؤشرات).
        stale = mark_stale_market_listings(days=14)
        step(
            "sweep_stale_market_listings",
            stale,
            "ok" if stale.get("status") in ("swept", "not_configured") else "needs_table",
        )

        # كسح شبه التكرار بحذر: الإعلان المُعاد جلبه برمز مختلف يُوسم duplicate
        # ويُحال إلى نظيره (مصدر+منطقة+نوع+سعر+عنوان مطبع + بوابات هاتف/مساحة).
        dedup = dedupe_market_listings()
        step(
            "dedupe_market_listings",
            dedup,
            "ok" if dedup.get("status") in ("deduped", "not_configured") else "needs_table",
        )

        # اتجاهات الأسعار الشهرية: وسيط لكل (منطقة × نوع × شهر × معاملة) من الحصاد
        # المُخزَّن في market_listings + الإعلانات المحلية — تغذي الرسوم الزمنية.
        trends = _build_price_trends(external_rows, listings)
        trends_save = save_price_trends(trends)
        step(
            "persist_price_trends",
            trends_save,
            "ok" if trends_save.get("status") in ("saved", "empty", "not_configured") else "needs_table",
        )

        # وكيل اكتشاف التطورات: أخبار ومؤشرات عقارية من مصادر كويتية + فحص منصات
        # إضافية — يُحفظ في market_developments (Supabase) وملف محلي، ولا يُفشل
        # الوكيل اليومي مهما تعطلت بعض المصادر (كل مصدر يُسجَّل حالته).
        try:
            discoveries = discover_market_developments()
            local_save = save_developments_local(discoveries)
            dev_save = save_market_developments(discoveries.get("developments", []))
            step("discover_market_developments", {
                "status": discoveries.get("status"),
                "count": discoveries.get("count", 0),
                "local": local_save.get("status"),
                "database": dev_save.get("status"),
                "note": discoveries.get("note", ""),
            })
        except Exception as exc:
            logger.exception("discover_market_developments failed")
            step("discover_market_developments", {"status": "failed", "error": str(exc)}, "ok")

        summary = supabase_data_summary(len(listings))
        notifications = build_update_notifications(
            previous_snapshot,
            snapshot,
            official_result=official_result,
            data_summary=summary,
            candidate_platforms=candidate_platforms,
        )
        save_update_notifications(notifications)
        step("build_update_notifications", notifications.get("counts") or {})

        # إرسال تنبيهات واتساب المجدولة: مقارنة آخر لقطتين → فرص جديدة أو
        # انخفاض سعر يطابق عملاء مسجلين → رسالة فعلية لكل رقم عبر Meta Cloud API.
        # لا يكسر الوكيل أبدًا: غياب الضبط يعيد not_configured ويُسجَّل كخطوة.
        whatsapp_result: dict[str, Any] = {"status": "not_configured", "sent": 0, "failed": 0, "total": 0}
        try:
            from backend.services.opportunities import build_whatsapp_alerts
            from backend.services.whatsapp_sender import send_whatsapp_alerts

            alerts_payload = build_whatsapp_alerts(previous_snapshot, snapshot)
            whatsapp_result = send_whatsapp_alerts(alerts_payload.get("alerts", []))
            step(
                "send_whatsapp_alerts",
                {k: whatsapp_result.get(k) for k in ("status", "sent", "failed", "skippedDuplicates", "total")},
                "ok" if whatsapp_result.get("status") in ("sent", "partial", "empty", "not_configured") else "needs_setup",
            )
        except Exception as exc:
            logger.exception("send_whatsapp_alerts failed")
            step("send_whatsapp_alerts", {"status": "failed", "error": str(exc)}, "ok")

        finished = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        status.update({
            "status": "success",
            "finishedAt": finished,
            "summary": {
                "localListings": len(listings),
                "officialTransactionsImported": official_result.get("count", 0),
                "marketListingsHarvested": harvest.get("count", 0),
                "opportunitiesScored": snapshot.get("totalScored", 0),
                "notificationCounts": notifications.get("counts") or {},
                "whatsappAlerts": {
                    "status": whatsapp_result.get("status"),
                    "sent": whatsapp_result.get("sent"),
                    "failed": whatsapp_result.get("failed"),
                    "total": whatsapp_result.get("total"),
                },
                "officialReferenceSources": reference_sources,
                "candidatePlatforms": candidate_platforms,
                "dataSummary": summary,
            },
        })
        _write_status(status)
        return status
    except Exception as exc:
        status.update({
            "status": "failed",
            "finishedAt": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "error": str(exc),
        })
        _write_status(status)
        return status
