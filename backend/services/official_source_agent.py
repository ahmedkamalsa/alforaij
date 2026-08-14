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


def _check_one(source: dict[str, Any], timeout: int) -> dict[str, Any]:
    status = "unchecked"
    detail = ""
    try:
        request = urllib.request.Request(
            source["url"],
            headers={"User-Agent": "Mozilla/5.0 alforaij-research-assistant/1.0"},
            method="GET",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            if 200 <= response.status < 400:
                status = "reachable"
                # المصادر المرشحة قد تعيد بوابة أخرى أو صفحة تحدي — فاحص محتوى
                # اختياري (validate) يصنّف الحالة الفعلية بدل مجرد نجاح HTTP.
                validate = source.get("validate")
                if validate:
                    try:
                        sample = response.read(8000).decode("utf-8", errors="replace")
                    except Exception:
                        sample = ""
                    override = validate(sample)
                    if override:
                        status, detail = override[0], override[1]
            else:
                status = f"http_{response.status}"
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


# المنصات العقارية المرشحة: مواقع أخرى مفيدة للمجال طلب المستخدم إدراجها ومراقبتها
# يوميًا مثل بقية المصادر. بعضها سوق إعلانات (قد يكون محجوبًا جغرافيًا أو محميًا
# بـ captcha من الخوادم) وبعضها مرجع رسمي (بوابة حكومية أو تطبيق PACI المكاني).
# الفحص اليومي يكتشف أي تغيّر في التوفر — بمجرد أن تصبح أي منصة قابلة للقراءة
# يبدأ موصلها (في live_sources) في إسهام بياناتها بالبحث والتقييم وقاعدة المعرفة.
CANDIDATE_PLATFORMS: list[dict[str, str]] = [
    {
        "id": "propertyfinder_kw",
        "name": "Property Finder Kuwait",
        "url": "https://www.propertyfinder.kw/",
        "kind": "marketplace",
        "role": "بحث وتقييم عند توفر الوصول (محجوب جغرافيًا من شبكات الخوادم حاليًا).",
    },
    {
        "id": "aqarmap_kw",
        "name": "Aqarmap Kuwait",
        "url": "https://aqarmap.com/kw/",
        "kind": "marketplace",
        "role": "بحث وتقييم عند إعادة تفعيل النسخة الكويتية (متوقفة حاليًا — يعيد بوابة مصر).",
        "validate": lambda body: (
            ("discontinued", "الموقع يعيد بوابة مصر حاليًا (النسخة الكويتية متوقفة)")
            if ("عقارماب مصر" in body or "aqarmap.com.eg" in body.lower())
            else None
        ),
    },
    {
        "id": "bayut_kw",
        "name": "Bayut Kuwait",
        "url": "https://www.bayut.com/kuwait/",
        "kind": "marketplace",
        "role": "بحث وتقييم عند توفر وصول غير محمي (نظام captcha يمنعه حاليًا).",
    },
    {
        "id": "e_gov_kw_portal",
        "name": "بوابة الكويت العقارية (e.gov.kw)",
        "url": "https://www.e.gov.kw/sites/kgoArabic/Pages/ServicesPortal/RealEstateServices.aspx",
        "kind": "official",
        "role": "مرجع خدمي وتحقق قانوني؛ لا تغذية إعلانات عامة (HTTP 403 من WAF للخوادم حاليًا).",
    },
    {
        "id": "paci_kuwait_finder",
        "name": "Kuwait Finder (PACI)",
        "url": "https://kuwaitfinder.paci.gov.kw/",
        "kind": "official",
        "role": "تأكيد الموقع/المنطقة/القطعة؛ غير قابل للوصول من شبكات الخوادم حاليًا.",
    },
]

_CANDIDATE_CACHE: dict[str, Any] = {"at": 0.0, "payload": None}
_CANDIDATE_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 ساعات — يكفي الفحص اليومي


def _build_candidate_payload(timeout: int) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=len(CANDIDATE_PLATFORMS)) as pool:
        futures = {pool.submit(_check_one, source, timeout): source for source in CANDIDATE_PLATFORMS}
        for future in as_completed(futures):
            row = future.result()
            # إزالة الحقول غير القابلة للتمثيل في JSON (مثل فاحص المحتوى validate)
            # قبل دخول النتيجة في الحالة اليومية/الإشعارات
            row.pop("validate", None)
            checks.append(row)
    checks.sort(key=lambda row: (row["status"] != "reachable", row["name"]))
    reachable = [row for row in checks if row["status"] == "reachable"]
    discontinued = [row for row in checks if row["status"] == "discontinued"]
    blocked = [
        row for row in checks
        if row["status"] == "unreachable" or str(row.get("status") or "").startswith("http_")
    ]
    note = (
        "منصات مرشحة أُدرجت في قاعدة المصادر بطلب المستخدم. تُفحص يوميًا لاكتشاف أي تغيّر في التوفر؛ "
        "المتاحة منها تدخل في البحث والتقييم فورًا عبر موصلاتها، وغير المتاحة تُسجَّل حالتها بشفافية "
        "(حجب جغرافي/حماية captcha/توقف خدمة) دون إسقاط بقية المصادر."
    )
    return {
        "count": len(checks),
        "reachable": len(reachable),
        "blocked": len(blocked),
        "discontinued": len(discontinued),
        "sources": checks,
        "note": note,
    }


def check_candidate_platforms(timeout: int = 10, force: bool = False) -> dict[str, Any]:
    """فحص توفر المنصات المرشحة بالتوازي مع كاش بفترة صلاحية (6 ساعات)."""
    now = time.time()
    cached = _CANDIDATE_CACHE.get("payload")
    if not force and cached is not None and (now - _CANDIDATE_CACHE["at"]) < _CANDIDATE_CACHE_TTL_SECONDS:
        return cached
    payload = _build_candidate_payload(timeout)
    _CANDIDATE_CACHE.update(at=time.time(), payload=payload)
    return payload
