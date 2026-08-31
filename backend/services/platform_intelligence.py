from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
from typing import Any

from backend.services.source_registry import source_registry


STATUS_BUCKETS: dict[str, str] = {
    "connected": "connected",
    "connected_reference": "connected",
    "live_scored": "connected",
    "live_conditional": "conditional",
    "official_service": "official",
    "planned_verified_data": "official",
    "geo_verification": "official",
    "reference_link": "reference",
    "live_blocked": "partner_required",
    "planned": "partner_required",
    "discontinued": "inactive",
}


INTELLIGENCE_OVERLAY: dict[str, dict[str, Any]] = {
    "alforaij_board": {
        "accessModel": "owned",
        "integrationMode": "direct_database",
        "databaseTables": ["listings"],
        "professionalUse": "مصدر داخلي للمطابقة الأولية وحساب فجوة السعر.",
        "nextAction": "تنظيف الحقول الناقصة وربط كل سجل برابط أو مرجع داخلي.",
    },
    "market_ads": {
        "accessModel": "owned_live",
        "integrationMode": "supabase_feed",
        "databaseTables": ["market_ads", "market_listings"],
        "professionalUse": "تحويل لوحة السوق إلى corpus حي للتقييم والمقارنات.",
        "nextAction": "الاستمرار في حفظ source_url وfirst_seen_at وnormalized_area.",
    },
    "official_transactions": {
        "accessModel": "official_data",
        "integrationMode": "verified_import",
        "databaseTables": ["official_transactions"],
        "professionalUse": "مرجع الصفقات الفعلية الأعلى وزنا عند توفر بيانات منظمة.",
        "nextAction": "استيراد دوري للصفقات مع تاريخ/منطقة/نوع/مساحة/سعر.",
    },
    "official_indicators": {
        "accessModel": "official_data",
        "integrationMode": "verified_import",
        "databaseTables": ["official_market_indicators"],
        "professionalUse": "مرجع سعر متر أو مؤشر منطقة حين تتوفر بيانات رسمية موثقة.",
        "nextAction": "تحديث المؤشرات حسب الربع والفترة وربطها بالمصدر.",
    },
    "moj_real_estate": {
        "accessModel": "official_service",
        "integrationMode": "licensed_or_manual_import",
        "databaseTables": ["official_transactions", "source_registry"],
        "professionalUse": "صفقات وتحقق تسجيل عقاري، وليس إعلانات بيع متاحة.",
        "nextAction": "اعتماد ملف/واجهة رسمية قبل إدخالها في التقييم.",
    },
    "e_gov_kw_portal": {
        "accessModel": "official_service",
        "integrationMode": "reference_link",
        "databaseTables": ["source_registry"],
        "professionalUse": "خدمة تحقق حالة عقار للمستخدم، لا مصدر سعر.",
        "nextAction": "إظهارها كدليل تحقق قانوني عند تفاصيل العقار.",
    },
    "paci_kuwait_finder": {
        "accessModel": "official_geo",
        "integrationMode": "geo_reference",
        "databaseTables": ["market_listings"],
        "professionalUse": "تأكيد الموقع/القطعة ورفع ثقة المنطقة.",
        "nextAction": "تطبيع المنطقة والقطعة عند توفر معرف مكاني موثق.",
    },
    "opensooq_kw": {
        "accessModel": "public_marketplace",
        "integrationMode": "live_public_search",
        "databaseTables": ["market_listings", "source_runs"],
        "professionalUse": "مقارنات سوقية مباشرة بعد تصنيف عقاري صارم.",
        "nextAction": "الاحتفاظ بسعر/مساحة/منطقة/رابط كل إعلان وسبب قبوله.",
    },
    "mourjan_kw": {
        "accessModel": "public_marketplace",
        "integrationMode": "live_public_search",
        "databaseTables": ["market_listings", "source_runs"],
        "professionalUse": "مقارنات إضافية من إعلانات عامة مع إثبات الرابط.",
        "nextAction": "تقوية فلترة النصوص القصيرة وتسجيل سبب الاستبعاد.",
    },
    "q8aqar": {
        "accessModel": "public_marketplace",
        "integrationMode": "detail_page_enrichment",
        "databaseTables": ["market_listings", "source_runs"],
        "professionalUse": "تحسين السعر/المساحة من صفحة التفاصيل عند توفرها.",
        "nextAction": "إعطاء وزن أعلى عند قراءة صفحة التفاصيل لا بطاقة البحث فقط.",
    },
    "yebtah": {
        "accessModel": "public_marketplace",
        "integrationMode": "structured_public_pages",
        "databaseTables": ["market_listings", "source_runs"],
        "professionalUse": "منصة كويتية حديثة تغطي المحافظات الست ببيانات قابلة للفهرسة.",
        "nextAction": "ربط JSON-LD والحفاظ على first_seen_at لكل إعلان.",
    },
    "four_sale": {
        "accessModel": "paid_visibility_marketplace",
        "integrationMode": "conditional_public_search_or_partner_feed",
        "databaseTables": ["market_listings", "source_runs", "source_registry"],
        "professionalUse": "مصدر مهم للسوق الكويتي، لكن ميزات الظهور فيه مدفوعة ويجب فصل الإعلان عن التقييم.",
        "nextAction": "تفضيل شراكة/Feed رسمي عند توفره وعدم تجاوز حماية المنصة.",
    },
    "propertyfinder_kw": {
        "accessModel": "paid_agent_platform",
        "integrationMode": "partner_feed_required",
        "databaseTables": ["partner_feeds", "market_listings", "source_runs"],
        "professionalUse": "بوابة وكلاء مدفوعة؛ تدخل عند توفر وصول مصرح به فقط.",
        "nextAction": "فتح مسار شراكة أو استيراد CSV مرخص بدل الاعتماد على صفحات محجوبة.",
    },
    "bayut_kw": {
        "accessModel": "paid_or_partner_marketplace",
        "integrationMode": "partner_feed_required",
        "databaseTables": ["partner_feeds", "market_listings", "source_runs"],
        "professionalUse": "تطبيق/بوابة كويتية نشطة، لكن القراءة الآلية تحتاج تصريح أو Feed.",
        "nextAction": "عرضها كمرشح شراكة موثق وعدم استخدامها في التسعير حتى تصل بيانات فعلية.",
    },
    "sakan": {
        "accessModel": "marketplace",
        "integrationMode": "conditional_public_search",
        "databaseTables": ["market_listings", "source_runs"],
        "professionalUse": "دليل توفر سوقي، يدخل في السعر فقط عند استخراج إعلان تفصيلي.",
        "nextAction": "عدم رفع وزن المصدر حتى تتوفر تفاصيل سعر/مساحة مستقرة.",
    },
    "dallal_kw": {
        "accessModel": "candidate_marketplace",
        "integrationMode": "planned_partner_or_public_check",
        "databaseTables": ["partner_feeds", "source_registry"],
        "professionalUse": "مرشح توسعة حديث لسوق الكويت عبر المحافظات.",
        "nextAction": "إضافة فحص وصول يومي ثم بناء موصل فقط إذا كانت البيانات عامة ومستقرة.",
    },
}


def _bucket_for_status(status: str) -> str:
    return STATUS_BUCKETS.get(str(status or ""), "reference")


def build_platform_intelligence() -> dict[str, Any]:
    """خريطة مهنية للمصادر: حالة الربط، قيمة قاعدة البيانات، وما يحتاج شراكة."""
    rows: list[dict[str, Any]] = []
    for source in source_registry():
        source_id = str(source.get("id") or "")
        overlay = INTELLIGENCE_OVERLAY.get(source_id, {})
        status = str(source.get("status") or "")
        bucket = _bucket_for_status(status)
        tables = overlay.get("databaseTables") or ["source_registry"]
        rows.append({
            "id": source_id,
            "name": source.get("name") or source_id,
            "category": source.get("category") or "مصدر",
            "status": status,
            "bucket": bucket,
            "accessModel": overlay.get("accessModel", "registry_source"),
            "integrationMode": overlay.get("integrationMode", "registry_policy"),
            "databaseTables": tables,
            "professionalUse": overlay.get("professionalUse") or source.get("role") or "",
            "nextAction": overlay.get("nextAction") or source.get("evidencePolicy") or "",
            "trustLevel": source.get("trustLevel") or "",
            "url": source.get("url") or "",
        })

    overlay_only = sorted(set(INTELLIGENCE_OVERLAY) - {row["id"] for row in rows})
    for source_id in overlay_only:
        overlay = INTELLIGENCE_OVERLAY[source_id]
        rows.append({
            "id": source_id,
            "name": "Dallal Kuwait" if source_id == "dallal_kw" else source_id,
            "category": "مصدر مرشح",
            "status": "planned",
            "bucket": "partner_required",
            "accessModel": overlay.get("accessModel", "candidate"),
            "integrationMode": overlay.get("integrationMode", "planned"),
            "databaseTables": overlay.get("databaseTables") or ["source_registry"],
            "professionalUse": overlay.get("professionalUse") or "",
            "nextAction": overlay.get("nextAction") or "",
            "trustLevel": "غير محدد حتى الربط",
            "url": "",
        })

    counts = Counter(row["bucket"] for row in rows)
    evidence_sources = [
        {
            "name": "Kuwait Ministry of Justice",
            "use": "الصفقات والإحصاءات العقارية الرسمية عند توفرها ببيانات منظمة.",
            "url": "https://www.moj.gov.kw/EN/pages/DeptDisplay.aspx?I=26",
        },
        {
            "name": "Kuwait Government Online",
            "use": "خدمة الاستعلام عن حالة العقار كمرجع تحقق قانوني.",
            "url": "https://e.gov.kw/sites/kgoenglish/Pages/eServices/MOJ/QueryStatusRealEstate.aspx",
        },
        {
            "name": "Global Property Portal Index",
            "use": "مرجع خارجي لترتيب بوابات الكويت ونمط السوق المجزأ.",
            "url": "https://globalpropertyportalindex.com/kuwait-property-portals/",
        },
        {
            "name": "Bayut Kuwait app listing",
            "use": "إثبات نشاط بوابة Bayut Kuwait وخصائص البحث والتقييم داخل التطبيق.",
            "url": "https://play.google.com/store/apps/details?id=com.bayut.bayutkw",
        },
        {
            "name": "Yebtah",
            "use": "إثبات تغطية المحافظات الست وتوفر قوائم بيع/إيجار حديثة.",
            "url": "https://yebtah.com/en",
        },
    ]

    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(rows),
            "connected": counts.get("connected", 0),
            "conditional": counts.get("conditional", 0),
            "official": counts.get("official", 0),
            "partnerRequired": counts.get("partner_required", 0),
            "reference": counts.get("reference", 0),
            "inactive": counts.get("inactive", 0),
        },
        "databaseStrategy": {
            "principle": "لا يدخل أي مصدر في التسعير حتى يحفظ رابط/تاريخ/منطقة/نوع/سعر أو سبب استبعاد واضح.",
            "coreTables": [
                "market_listings",
                "market_ads",
                "official_transactions",
                "official_market_indicators",
                "source_runs",
                "source_registry",
                "partner_feeds",
            ],
            "qualityRules": [
                "كل إعلان له source_id مطابق لسجل المصادر أو يسقط لسلة other_marketplaces.",
                "first_seen_at يمثل بداية معرفتنا بالإعلان عندما لا تنشر المنصة تاريخ الإعلان.",
                "المصادر المدفوعة أو المحجوبة لا تدخل التقييم إلا عبر شراكة/تصدير مرخص.",
                "المصادر الرسمية ترفع الثقة ولا تستبدل إعلان البيع إلا إذا كانت صفقة فعلية منظمة.",
            ],
        },
        "sources": rows,
        "evidenceSources": evidence_sources,
    }
