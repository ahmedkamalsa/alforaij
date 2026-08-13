from __future__ import annotations

import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

# كاش بفترة صلاحية: روابط المصادر المرجعية لا تتغير كل لحظة،
# فلا داعي لإعادة فحصها تسلسليًا (حتى ~48 ثانية) عند كل استدعاء.
_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 ساعات


OFFICIAL_REFERENCE_SOURCES: list[dict[str, str]] = [
    {
        "id": "moj_sale_deals",
        "name": "وزارة العدل - صفقات التسجيل العقاري",
        "url": "https://www.moj.gov.kw/EN/Apps/Pages/Realestate.aspx",
        "role": "مصدر الصفقات الرسمية عند توفر ملف/جدول قابل للاستيراد.",
        "dataUse": "official_transactions",
    },
    {
        "id": "moj_property_status",
        "name": "وزارة العدل - الاستعلام عن حالة العقار",
        "url": "https://e.gov.kw/sites/kgoenglish/Pages/eServices/MOJ/QueryStatusRealEstate.aspx",
        "role": "تحقق قانوني من حالة العقار عند توفر رقم الوثيقة/العقار.",
        "dataUse": "legal_verification",
    },
    {
        "id": "paci_kuwait_finder",
        "name": "PACI / Kuwait Finder",
        "url": "https://e.gov.kw/sites/kgoenglish/Pages/ApplicationPages/Application-KuwaitFinder.aspx",
        "role": "تأكيد الموقع والمنطقة والقطعة والاتجاهات.",
        "dataUse": "geo_verification",
    },
    {
        "id": "kcb_building_loans",
        "name": "بنك الائتمان الكويتي - القروض العقارية",
        "url": "https://e.gov.kw/sites/kgoenglish/Pages/Services/KCB/BuildingLoans.aspx",
        "role": "تصنيف وتمويل: بيت حكومي/قرض بناء/شراء/ترميم ومطلوب الائتمان.",
        "dataUse": "finance_rules",
    },
    {
        "id": "kfh_real_estate_reports",
        "name": "بيت التمويل الكويتي - تقارير عقارية",
        "url": "https://www.kfh.com/en/home/Investor-Relations/Real-estate-Reports.html",
        "role": "مؤشرات سوقية مرجعية عند غياب صفقات كافية.",
        "dataUse": "market_indicators",
    },
    {
        "id": "nbk_housing_loan",
        "name": "NBK - Housing Loan",
        "url": "https://www.nbk.com/kuwait/personal/loans/housing-loan.html",
        "role": "مؤشر تمويل بنكي خاص لا يحل محل التقييم الرسمي.",
        "dataUse": "finance_rules",
    },
]


def _check_one(source: dict[str, str], timeout: int) -> dict[str, Any]:
    status = "unchecked"
    detail = ""
    try:
        request = urllib.request.Request(
            source["url"],
            headers={"User-Agent": "Mozilla/5.0 alforaij-research-assistant/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = "reachable" if 200 <= response.status < 400 else f"http_{response.status}"
    except Exception as exc:
        status = "unreachable"
        detail = str(exc)[:180]
    return {**source, "status": status, "detail": detail}


def _build_payload(timeout: int) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(OFFICIAL_REFERENCE_SOURCES)) as pool:
        futures = {pool.submit(_check_one, source, timeout): source for source in OFFICIAL_REFERENCE_SOURCES}
        for future in as_completed(futures):
            checks.append(future.result())
    checks.sort(key=lambda row: (row["status"] != "reachable", row["name"]))
    return {
        "count": len(checks),
        "reachable": sum(1 for row in checks if row["status"] == "reachable"),
        "sources": checks,
        "note": "هذه مصادر مرجعية مجانية. لا تدخل أرقامها في التقييم إلا عند استخراج بيانات منظمة أو إدخال CSV/JSON موثق.",
    }


def check_official_reference_sources(timeout: int = 10, force: bool = False) -> dict[str, Any]:
    """فحص المصادر الرسمية بالتوازي مع كاش بفترة صلاحية.

    - الفحص المتوازي يحدّ زمن الانتظار إلى أقصى مهلة واحدة بدل مجموعها.
    - الكاش (6 ساعات) يمنع إعادة الفحص عند كل استدعاء — يكفي الوكيل اليومي.
    """
    now = time.time()
    cached = _CACHE.get("payload")
    if not force and cached is not None and (now - _CACHE["at"]) < _CACHE_TTL_SECONDS:
        return cached
    payload = _build_payload(timeout)
    _CACHE.update(at=time.time(), payload=payload)
    return payload
