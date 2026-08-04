from __future__ import annotations

from typing import Any


SOURCE_REGISTRY: list[dict[str, Any]] = [
    {
        "id": "alforaij_board",
        "name": "الفريج - بيانات اللوحة المحلية",
        "category": "مصدر أساسي",
        "connection": "ملف بيانات محلي",
        "role": "يدخل في البحث والمطابقة والتقييم",
        "trustLevel": "مرتفع داخل حدود بيانات الفريج",
        "scoringPolicy": "يدخل في درجة المطابقة والتقييم عند توفر السعر/المساحة/الرابط.",
        "evidencePolicy": "كل نتيجة تحتفظ برابط الإعلان الأصلي والحقول الخام عند توفرها.",
        "status": "connected",
    },
    {
        "id": "opensooq_kw",
        "name": "OpenSooq Kuwait",
        "category": "سوق إعلانات خارجي",
        "connection": "بحث حي من صفحة النتائج العامة",
        "role": "يدخل في البحث والتقييم بعد فلترة النوع والمنطقة والعملية",
        "trustLevel": "متوسط",
        "scoringPolicy": "لا يدخل الإعلان إلا إذا كان تصنيفه عقاريًا ويطابق الطلب صراحة.",
        "evidencePolicy": "الرابط والسعر والمنطقة والوصف تحفظ كمصدر لكل رقم مستخرج.",
        "status": "live_scored",
    },
    {
        "id": "mourjan_kw",
        "name": "Mourjan Kuwait",
        "category": "سوق إعلانات خارجي",
        "connection": "قراءة HTML من صفحة البحث العامة",
        "role": "يدخل في البحث والتقييم عند وجود كارت إعلان مطابق",
        "trustLevel": "متوسط",
        "scoringPolicy": "يتم تحديد نوع العقار من مسار الإعلان، وليس من طلب المستخدم.",
        "evidencePolicy": "الرابط والوصف والسعر الصريح تدخل كدليل عند توفرها.",
        "status": "live_scored",
    },
    {
        "id": "q8aqar",
        "name": "Q8Aqar",
        "category": "دليل عقاري كويتي",
        "connection": "صفحات منطقة/نوع العقار العامة",
        "role": "يدخل فقط عند ظهور رابط إعلان يثبت نفس الطلب",
        "trustLevel": "متوسط كرابط دليل، أعلى عند قراءة صفحة التفاصيل",
        "scoringPolicy": "إذا لم يثبت الإعلان أنه نفس المنطقة والنوع والعملية لا يدخل في التقييم.",
        "evidencePolicy": "عند نقص السعر أو المساحة يظهر كرابط دليل ولا يرفع تقييم السعر.",
        "status": "live_conditional",
    },
    {
        "id": "sakan",
        "name": "Sakan",
        "category": "بوابة بحث عقاري",
        "connection": "فحص صفحة البحث العامة",
        "role": "حاليًا دليل توفر فقط وليس تقييم سعر",
        "trustLevel": "منخفض للتقييم حتى يتوفر API أو endpoint تفاصيل",
        "scoringPolicy": "لا يدخل في الدرجة إلا بعد استخراج إعلانات تفصيلية قابلة للتحقق.",
        "evidencePolicy": "يعرض عدد المتاح ورابط الصفحة فقط.",
        "status": "availability_only",
    },
    {
        "id": "official_transactions",
        "name": "الصفقات الرسمية / التسجيل العقاري",
        "category": "مصدر رسمي",
        "connection": "استيراد ملف أو API عند توفره",
        "role": "المصدر الأقوى لتقييم السعر عند ربطه",
        "trustLevel": "مرتفع جدًا",
        "scoringPolicy": "يستخدم كمرجع سوقي مرجح أعلى من الإعلانات عند توفر صفقات مشابهة.",
        "evidencePolicy": "يجب حفظ رقم/تاريخ الصفقة والمنطقة والنوع والمساحة والسعر.",
        "status": "planned",
    },
    {
        "id": "other_marketplaces",
        "name": "منصات أخرى: 4Sale / Aqarat / مصادر مكاتب",
        "category": "مصادر توسعة",
        "connection": "روابط بحث أو API/Feed لاحق",
        "role": "لا تدخل في التقييم إلا بعد مصدر بيانات مستقر",
        "trustLevel": "غير محدد حتى الربط",
        "scoringPolicy": "تدخل تدريجيًا بنفس قواعد الفلترة والدليل.",
        "evidencePolicy": "كل مصدر جديد يجب أن يمر من سجل تشغيل وتوثيق رابط/رقم الإعلان.",
        "status": "planned",
    },
]


def source_registry() -> list[dict[str, Any]]:
    return [dict(item) for item in SOURCE_REGISTRY]
