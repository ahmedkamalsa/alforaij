from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)


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
        "connection": "صفحات منطقة/نوع العقار العامة + قراءة صفحات التفاصيل",
        "role": "يدخل في البحث والتقييم عند إثبات نفس الطلب، ويُحسَّن السعر/المساحة من صفحة التفاصيل",
        "trustLevel": "متوسط، أعلى عند قراءة صفحة التفاصيل نفسها",
        "scoringPolicy": "إذا لم يثبت الإعلان أنه نفس المنطقة والنوع والعملية لا يدخل في التقييم.",
        "evidencePolicy": "السعر والمساحة يُستخرجان من العنوان ثم تُقرأ صفحات التفاصيل لتحسينهما عند توفرها.",
        "status": "live_scored",
    },
    {
        "id": "findq8",
        "name": "FindQ8",
        "category": "دليل عقاري كويتي",
        "connection": "بحث حي من صفحة النتائج العامة",
        "role": "يدخل في البحث والتقييم عند توفر بيانات الإعلان",
        "trustLevel": "متوسط (منصة عقارية كويتية نشطة)",
        "scoringPolicy": "يدخل في التقييم عند استخراج السعر والمساحة والمنطقة.",
        "evidencePolicy": "يحتفظ برابط الإعلان والسعر والمساحة كدليل.",
        "status": "connected",
    },
    {
        "id": "sakan",
        "category": "بوابة بحث عقاري",
        "name": "Sakan",
        "connection": "فحص صفحة البحث العامة + محاولة قراءة الحالة المضمّنة في الصفحة",
        "role": "يُستخرج من الحالة المضمّنة عند توفرها، وإلا يبقى دليل توفر وعدد متاح",
        "trustLevel": "متوسط عند استخراج إعلانات مضمّنة قابلة للتحقق، منخفض عند عدم توفرها",
        "scoringPolicy": "لا يدخل في الدرجة إلا بعد استخراج إعلانات تفصيلية تثبت نفس الطلب.",
        "evidencePolicy": "يعرض عدد المتاح ورابط الصفحة، مع إعلانات مستخرجة عند ظهورها في الحالة المضمّنة.",
        "status": "live_conditional",
    },
    {
        "id": "official_transactions",
        "name": "الصفقات الرسمية / التسجيل العقاري",
        "category": "مصدر رسمي",
        "connection": "جدول official_transactions في Supabase + ملف data/official_transactions.json",
        "role": "المصدر الأقوى لتقييم السعر: وسيط مرجح أعلى من الإعلانات عند توفر صفقات",
        "trustLevel": "مرتفع جدًا",
        "scoringPolicy": "يُستخدم كمرجع سوقي مرجح أولًا قبل المعيار الرسمي والإعلانات عند توفر صفقات بنفس المنطقة.",
        "evidencePolicy": "يحفظ رقم/تاريخ الصفقة والمنطقة والنوع والمساحة والسعر ووسيط سعر المتر المشتق.",
        "status": "connected",
    },
    {
        "id": "alhisba_public_deals",
        "name": "الحسبة - الصفقات المسجلة العامة",
        "category": "مصدر مرجعي كويتي",
        "connection": "قراءة الصفحة العامة للحسبة واستخراج الصفقات وروابط الإعلانات الشبيهة الظاهرة علنًا",
        "role": "يدخل كدليل سعر مرجعي ومقارنة سوقية، وليس كإعلان متاح للبيع",
        "trustLevel": "مرتفع كمرجع سوقي عند ظهور السعر والمساحة والمنطقة ورابط المصدر",
        "scoringPolicy": "يرجّح تقييم السعر عند تطابق المنطقة والنوع، ولا يُحسب كفرصة شراء متاحة.",
        "evidencePolicy": "يحفظ المنطقة، النوع، المساحة، السعر، سعر المتر، تاريخ الصفقة عند توفره، ورابط الحسبة.",
        "status": "connected_reference",
    },
    {
        "id": "nabdaqar",
        "name": "نبض عقار (NabdAqar)",
        "category": "منصة عقارية كويتية",
        "connection": "بحث حي وتنقيب HTML في الإعلانات المباشرة",
        "role": "يدخل في البحث والمطابقة والتقييم عند توفر بيانات الإعلان",
        "trustLevel": "مرتفع (منصة عقارية كويتية متخصصة)",
        "scoringPolicy": "يدخل في التقييم بحسب السعر والمواصفات المستخرجة.",
        "evidencePolicy": "يحتفظ برابط الإعلان والنص الأصلي كدليل.",
        "status": "connected",
    },
    {
        "id": "bu3qar",
        "name": "بوعقار / بوشملان (Bu3qar)",
        "category": "منصة عقارية كويتية",
        "connection": "بحث حي واستخراج من نتائج بوعقار",
        "role": "يدخل في البحث والمطابقة والتقييم",
        "trustLevel": "مرتفع (سوق كويتي نشط)",
        "scoringPolicy": "يدخل في التقييم عند استخراج السعر والمساحة صراحة.",
        "evidencePolicy": "يرتبط مباشرة برابط العقار كدليل.",
        "status": "connected",
    },
    {
        "id": "waseet",
        "name": "وسيط الكويت (Waseet)",
        "category": "سوق إعلانات خارجي",
        "connection": "قراءة HTML من صفحة البحث العامة",
        "role": "يدخل في البحث والمطابقة عند توفر بطاقة إعلان",
        "trustLevel": "متوسط",
        "scoringPolicy": "يدخل في التقييم عند استخراج السعر والمنطقة.",
        "evidencePolicy": "الرابط والنص الأصلي يُحفظان كدليل عند توفرهما.",
        "status": "connected",
    },
    {
        "id": "aqarat",
        "name": "Aqarat",
        "category": "مصادر توسعة",
        "connection": "بحث حي من صفحة البحث العامة",
        "role": "يدخل في البحث والتقييم عند ظهور إعلان يثبت نفس الطلب",
        "trustLevel": "متوسط",
        "scoringPolicy": "تدخل بنفس قواعد الفلترة والدليل (المنطقة والنوع والعملية).",
        "evidencePolicy": "كل نتيجة تحفظ الرابط والنص الأصلي كدليل.",
        "status": "live_conditional",
    },
    {
        "id": "four_sale",
        "name": "4Sale",
        "category": "مصادر توسعة",
        "connection": "فحص روابط HTML لأحدث العقارات (q84sale.com — النطاق القديم غير متاح DNS)",
        "role": "يدخل في البحث والتقييم عند ظهور إعلان يثبت نفس الطلب",
        "trustLevel": "متوسط",
        "scoringPolicy": "تدخل بنفس قواعد الفلترة والدليل.",
        "evidencePolicy": "كل نتيجة تحفظ الرابط والنص الأصلي كدليل.",
        "status": "live_conditional",
    },
    {
        "id": "yebtah",
        "name": "Yebtah",
        "category": "مصادر توسعة",
        "connection": "بيانات ItemList منظمة (JSON-LD) من صفحتي البيع والإيجار",
        "role": "يدخل في البحث والتقييم عند ظهور إعلان يثبت نفس الطلب",
        "trustLevel": "متوسط",
        "scoringPolicy": "تدخل بنفس قواعد الفلترة والدليل (المنطقة والنوع والعملية).",
        "evidencePolicy": "كل نتيجة تحفظ الرابط والنص الأصلي كدليل.",
        "status": "live_scored",
    },
    {
        "id": "market_ads",
        "name": "السوق المباشر (Supabase market_ads)",
        "category": "مصدر أساسي حي",
        "connection": "جدول market_ads في Supabase (إعلانات لوحة العرض)",
        "role": "يدخل في البحث والمطابقة والتقييم من بيانات السوق الحية",
        "trustLevel": "مرتفع (بيانات فعلية من لوحة العرض)",
        "scoringPolicy": "يدخل في التقييم عند توفر السعر والمساحة والمنطقة.",
        "evidencePolicy": "يحفظ الرابط الأصلي وسعر المتر المستخرج والمساحة كدليل.",
        "status": "connected",
    },
    {
        "id": "official_indicators",
        "name": "مؤشرات رسمية (official_market_indicators)",
        "category": "مصدر رسمي",
        "connection": "جدول official_market_indicators في Supabase",
        "role": "مرجع سعر المتر الرسمي للمنطقة: يدخل كمرجع تقييم مرجّح",
        "trustLevel": "مرتفع جدًا",
        "scoringPolicy": "يُستخدم كمرجع سوقي مرجّح عند توفر مؤشر رسمي للمنطقة المطلوبة.",
        "evidencePolicy": "يحفظ السعر المرجعي ومصدره والربع والفترة كمصدر للرقم.",
        "status": "connected",
    },
    {
        "id": "moj_real_estate",
        "name": "وزارة العدل / التسجيل العقاري",
        "category": "مصدر رسمي",
        "connection": "استيراد صفقات موثقة إلى official_transactions أو ربط API عند توفره",
        "role": "المرجع الأعلى للصفقات الفعلية، ولا يدخل الحساب إلا بصفقة منظمة قابلة للتدقيق",
        "trustLevel": "مرتفع جدًا عند توفر رقم/تاريخ/منطقة/نوع/سعر الصفقة",
        "scoringPolicy": "يعطي وزنًا أعلى من الإعلانات عند وجود صفقات حديثة بنفس المنطقة والنوع.",
        "evidencePolicy": "يجب حفظ تاريخ الصفقة، المنطقة، نوع العقار، المساحة، السعر، ومصدر السجل.",
        "status": "planned_verified_data",
    },
    {
        "id": "paci_kuwait_finder",
        "name": "PACI / Kuwait Finder",
        "category": "مصدر مكاني رسمي",
        "connection": "التطبيق المكاني الرسمي kuwaitfinder.paci.gov.kw؛ يُفحص توفره يوميًا، ويُستخدم عند توفر بيانات GIS/عناوين منظمة",
        "role": "تأكيد المنطقة/القطعة/الموقع، وليس مصدر سعر مستقل",
        "trustLevel": "مرتفع جدًا للموقع والعنوان عند توفر بيانات منظمة",
        "scoringPolicy": "يرفع ثقة مطابقة الموقع ولا يغيّر السعر وحده.",
        "evidencePolicy": "يحفظ معرف الموقع أو القطعة أو رابط الخريطة عند توفره.",
        "status": "geo_verification",
        "url": "https://kuwaitfinder.paci.gov.kw/",
    },
    {
        "id": "propertyfinder_kw",
        "name": "Property Finder Kuwait",
        "category": "سوق إعلانات خارجي",
        "connection": "بحث حي في صفحات النتائج + استخراج JSON-LD/الحمولة المضمّنة؛ محجوب جغرافيًا من شبكات الخوادم حاليًا ويُعاد فحصه يوميًا",
        "role": "يدخل في البحث والتقييم وقاعدة المعرفة عند توفر الوصول — يبدأ فور نجاح الفحص",
        "trustLevel": "متوسط إلى مرتفع (منصة عقارية كويتية نشطة)",
        "scoringPolicy": "يدخل في التقييم عند استخراج سعر ومساحة ومنطقة تثبت نفس الطلب.",
        "evidencePolicy": "يحفظ الرابط الأصلي والسعر والمساحة والنص الخام كدليل لكل رقم.",
        "status": "live_blocked",
    },
    {
        "id": "aqarmap_kw",
        "name": "Aqarmap Kuwait (عقارماب)",
        "category": "سوق إعلانات خارجي",
        "connection": "بحث حي في صفحات النتائج؛ النسخة الكويتية متوقفة حاليًا والمسار /kw/ يعيد بوابة مصر",
        "role": "يدخل في البحث والتقييم عند إعادة تفعيل النسخة الكويتية — يُرصد تلقائيًا",
        "trustLevel": "متوسط",
        "scoringPolicy": "لا تُؤخذ بيانات بوابة أخرى (مصر) كبيانات كويتية — يتحقق الموصل من هوية الصفحة أولًا.",
        "evidencePolicy": "يحفظ الرابط الأصلي والنص الخام كدليل عند استخراج أي إعلان.",
        "status": "discontinued",
    },
    {
        "id": "bayut_kw",
        "name": "Bayut Kuwait (بيوت)",
        "category": "سوق إعلانات خارجي",
        "connection": "بحث حي في صفحات النتائج؛ محمي بنظام captcha يمنع القراءة البرمجية حاليًا",
        "role": "يدخل في البحث والتقييم عند توفر وصول غير محمي — يُرصد يوميًا",
        "trustLevel": "متوسط",
        "scoringPolicy": "لا يُحتسب أي إعلان إلا بعد استخراج بيانات فعلية تثبت نفس الطلب.",
        "evidencePolicy": "يحفظ الرابط الأصلي والنص الخام كدليل لكل إعلان مستخرج.",
        "status": "live_blocked",
    },
    {
        "id": "e_gov_kw_portal",
        "name": "بوابة الكويت العقارية (e.gov.kw)",
        "category": "مصدر رسمي",
        "connection": "مرجع حكومي للخدمات العقارية؛ لا يوجد تغذية إعلانات عامة — يُفحص توفره ضمن المصادر الرسمية",
        "role": "مرجع خدمي وتحقق قانوني (حالة العقار/التسجيل) وليس مصدر إعلانات متاحة",
        "trustLevel": "مرتفع كمرجع حكومي عند توفر بيانات منظمة قابلة للاستيراد",
        "scoringPolicy": "لا يدخل في تقييم السعر؛ يُستخدم للتحقق من حالة العقار والخدمات عند الحاجة.",
        "evidencePolicy": "يحفظ رابط الخدمة واسمها ونوع التحقق.",
        "status": "official_service",
        "url": "https://www.e.gov.kw/sites/kgoArabic/Pages/ServicesPortal/RealEstateServices.aspx",
    },
    {
        "id": "alhisba_estimators",
        "name": "الحسبة - حاسبات العقار والإيجار والتمويل",
        "category": "منصة تقدير ومؤشرات",
        "connection": "روابط تحقق وحاسبات عامة؛ لا يوجد API عام موثق ضمن المشروع حتى الآن",
        "role": "مقارنة مرجعية خارجية ووجهة تحقق للمستخدم، ولا تدخل كنموذج حسابي مغلق بلا بيانات منظمة",
        "trustLevel": "مرتفع كمنصة متخصصة، لكن الإدخال الآلي يحتاج API/ملف مرخص",
        "scoringPolicy": "لا تغيّر درجة الفرصة إلا عند توفر بيانات منظمة قابلة للتدقيق.",
        "evidencePolicy": "يعرض رابط المصدر ونوع الحاسبة/الخدمة المستخدمة.",
        "status": "reference_link",
    },
    {
        "id": "bank_market_reports",
        "name": "تقارير البنوك وشركات التمويل",
        "category": "مصدر مالي",
        "connection": "تقارير بيت التمويل الكويتي، NBK، ومؤشرات التمويل عند توفر رابط/ملف منظم",
        "role": "مؤشر مساعد للاتجاهات والتمويل، وليس بديلًا عن الصفقات الرسمية",
        "trustLevel": "مرتفع للتوجهات العامة، متوسط للتقييم الفردي",
        "scoringPolicy": "يستخدم كعامل داعم عند غياب صفقات كافية، مع إظهار أنه مؤشر لا تقييم رسمي.",
        "evidencePolicy": "يحفظ اسم التقرير، الفترة، المؤشر المستخدم، ورابط المصدر.",
        "status": "planned_verified_data",
    },
    {
        "id": "dallal_kw",
        "name": "Dallal Kuwait",
        "category": "مصدر توسعة كويتي",
        "connection": "مرشح ربط: فحص صفحة عامة أو Feed شراكة عند توفره",
        "role": "يدخل كمنصة مرشحة فقط حتى يثبت توفر بيانات إعلانات كويتية منظمة ومصرح بها",
        "trustLevel": "غير محدد حتى الربط",
        "scoringPolicy": "لا يدخل في التقييم إلا بعد استخراج سعر ومساحة ومنطقة ورابط مصدر ثابت.",
        "evidencePolicy": "يحفظ الرابط الأصلي ووقت أول رصد وسبب الإدخال أو الاستبعاد.",
        "status": "planned",
    },
    {
        "id": "other_marketplaces",
        "name": "منصات أخرى: مصادر مكاتب / API مستقبلية",
        "category": "مصادر توسعة",
        "connection": "API/Feed عند توفره من شريك",
        "role": "لا تدخل في التقييم إلا بعد مصدر بيانات مستقر",
        "trustLevel": "غير محدد حتى الربط",
        "scoringPolicy": "تدخل تدريجيًا بنفس قواعد الفلترة والدليل.",
        "evidencePolicy": "كل مصدر جديد يجب أن يمر من سجل تشغيل وتوثيق رابط/رقم الإعلان.",
        "status": "planned",
    },
]


def source_registry() -> list[dict[str, Any]]:
    return [dict(item) for item in SOURCE_REGISTRY]


# ─── منطق السجل: المطابقة، حارس قيد المفتاح الأجنبي، المزامنة ────────────────
# الوحدة تملك سؤال «ما المصادر الموجودة؟»: SOURCE_REGISTRY صيغة التأليف، وجدول
# source_registry الحي في Supabase هو سلطة قيد المفتاح الأجنبي. أي انجراف بينهما
# (مصدر محلي غير مسجَّل بعد) كان يكسر حفظ source_runs كاملة بصمت (HTTP 409 =
# «فشل الحفظ» لكل بحث). هنا تُحل المطابقة، وتُتحقق من القيد الحي، وتُسجَّل
# المزامنة مع تقرير الانجراف ليكون ملاحظًا لا صامتًا.

# المعرف الآمن للمصادر غير المسجلة في الجدول الحي — سلة موجودة دائمًا في السجل
# فلا يكسر قيد المفتاح الأجنبي.
SAFE_FALLBACK_ID = "other_marketplaces"


_remote_ids_cache: set[str] | None = None
_remote_ids_fetched_at: float = 0.0


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _remote_reads_enabled() -> bool:
    """هل نسمح بقراءة السجل الحي؟ — نفس بوابة supabase_store: ممنوعة في الاختبارات."""
    if "unittest" in sys.modules and os.getenv("ALFORAIJ_TEST_ALLOW_SUPABASE") != "1":
        return False
    return bool(SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY)


def remote_registry_ids() -> set[str] | None:
    """معرفات source_registry الحية في Supabase — سلطة قيد المفتاح الأجنبي.

    عند توفر القراءة تعيد مجموعة المعرفات الفعلية المسجلة في الجدول الحي؛ عند
    التعذر (غير مضبوط/اختبارات/فشل شبكة) تعيد None فيتخطى المتصل التحقق ولا
    يغيّر سلوكًا غير مضمون. كاش 60 ثانية لأن الدفعة الواحدة تستدعي المطابقة
    عدة مرات.
    """
    global _remote_ids_cache, _remote_ids_fetched_at
    if _remote_ids_cache is not None and time.time() - _remote_ids_fetched_at < 60:
        return _remote_ids_cache
    if not _remote_reads_enabled():
        return None
    request = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/source_registry?select=id&limit=1000",
        method="GET",
        headers=_headers(),
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            rows = json.loads(response.read().decode("utf-8"))
    except Exception:
        logger.warning("source_registry read failed", exc_info=True)
        return None
    ids = {str(row.get("id") or "") for row in rows if row.get("id")}
    if not ids:
        return None
    _remote_ids_cache = ids
    _remote_ids_fetched_at = time.time()
    return ids


def drift_report() -> dict[str, Any]:
    """مقارنة السجل المحلي بالجدول الحي: ما غير المسجل (خطر FK) وما الفائض.

    تُستدعى بعد المزامنة وفي الفحص اليومي؛ لا توفر القراءة تعيد حالة واضحة
    بدل إخفاء الفشل.
    """
    remote_ids = remote_registry_ids()
    if remote_ids is None:
        return {"available": False, "note": "تعذر قراءة السجل الحي (غير مضبوط/اختبارات/فشل شبكة)."}
    local_ids = {str(item.get("id") or "") for item in SOURCE_REGISTRY}
    unregistered = sorted(local_ids - remote_ids)
    remote_only = sorted(remote_ids - local_ids)
    return {
        "available": True,
        "localCount": len(local_ids),
        "remoteCount": len(remote_ids),
        "unregisteredLocal": unregistered,
        "remoteOnly": remote_only,
        "synced": not unregistered and not remote_only,
    }


def match_source_id(source_name: str) -> str:
    """مطابقة اسم المصدر الحي بمعرف من السجل المحلي (قبل التحقق من القيد الحي)."""
    target = str(source_name or "")
    try:
        # 1) مطابقة حرفية أولًا (أسرع وأكثر أمانًا)
        for entry in SOURCE_REGISTRY:
            if str(entry.get("name") or "") == target:
                return str(entry["id"])
        # 2) مطابقة الجذر قبل القوسين: «السوق المباشر (بوشملان)» ← سجل
        #    «السوق المباشر (Supabase market_ads)» — الأسماء الحية تحمل تفاصيل
        #    المصدر الداخلي بين قوسين فلا تطابق حرفيًا اسم السجل.
        target_base = target.split(" (")[0].strip()
        if len(target_base) >= 4:
            for entry in SOURCE_REGISTRY:
                entry_base = str(entry.get("name") or "").split(" (")[0].strip()
                if entry_base and entry_base == target_base:
                    return str(entry["id"])
        # 3) اسم المصدر قد يكون اختصارًا لاسم السجل الطويل (مثل «الصفقات الرسمية»
        #    مقابل «الصفقات الرسمية / التسجيل العقاري») — لكن نمنع الاتجاه العكسي
        #    للأسماء القصيرة: اسم طوله 3 أحرف مثل «عقار» موجود داخل «بوعقار /
        #    بوشملان» و«التسجيل العقاري» فيطابق المصدر الخطأ. القاعدة: سجل الأسماء
        #    يطابق داخل الاسم المطلوب فقط، والاسم المطلوب يطابق داخل السجل بشرط
        #    ألا يكون قصيرًا جدًا (<6 أحرف).
        for entry in SOURCE_REGISTRY:
            entry_name = str(entry.get("name") or "")
            if not entry_name:
                continue
            if entry_name in target or (len(target) >= 6 and target in entry_name):
                return str(entry["id"])
        # 4) تطبيع المسافات وعلامات الترقيم وحالة الأحرف: «PropertyFinder»/«Bayut»
        #    مقابل «Property Finder Kuwait»/«Bayut Kuwait» في السجل (المتصل لا يطابق
        #    الاسم المفصول، وحالة الأحرف تختلف) — يُقارن الشكل الطبيعي دون فراغات.
        def _norm(name: str) -> str:
            return re.sub(r"[^0-9a-zA-Z\u0600-\u06FF]", "", name).lower()

        target_norm = _norm(target)
        if len(target_norm) >= 4:
            for entry in SOURCE_REGISTRY:
                entry_name_norm = _norm(str(entry.get("name") or ""))
                if not entry_name_norm:
                    continue
                # الاسم الطبيعي يساوي أو يُحتوى داخل سجل أطول — بشرط ألا يكون
                # السجل بأكمله مجرد جذر من اسم قصير (نفس حارس الاسم القصير أعلاه).
                if target_norm == entry_name_norm or (
                    len(target_norm) >= 5 and target_norm in entry_name_norm
                ):
                    return str(entry["id"])
        # 5) تطابق بمجموعة الكلمات (رموز): يعالج الاختلافات الترجمة/الكتابة داخل
        #    الأسماء المركبة: «Bu3qar / بوشملان» مقابل «بوعقار / بوشملان (Bu3qar)»
        #    و«الحسبة - صفقات عامة» مقابل «الحسبة - الصفقات المسجلة العامة».
        #    تُجرَّد «ال» التعريف العربية للطرفين ثم تُقارن الكلمات تساويًا (لا
        #    احتواء) — فيبقى «عقار» بلا تطابق مع «بوعقار» (حارس الاسم القصير محفوظ).
        def _tokens(name: str) -> set[str]:
            out = set()
            for token in re.split(r"[^0-9a-zA-Z\u0600-\u06FF]+", name):
                token = token.lower()
                if token.startswith("ال") and len(token) > 2:
                    token = token[2:]
                if len(token) >= 2:
                    out.add(token)
            return out

        target_tokens = _tokens(target)
        if len(target_tokens) >= 2:
            for entry in SOURCE_REGISTRY:
                entry_tokens = _tokens(str(entry.get("name") or ""))
                if entry_tokens and target_tokens.issubset(entry_tokens):
                    return str(entry["id"])
    except Exception:
        logger.exception("source id matching failed for %r", source_name)
    # سقوط آمن لا يكسر قيد المفتاح الأجنبي في source_runs: لا نُرسل معرفًا غير موجود
    # في source_registry (يُفضي إرساله إلى HTTP 409 يوقف حفظ الدفعة كاملة). نبحث عن
    # أقرب معرف سجل معرف؛ وإلا «other_marketplaces» الموجود دائمًا في السجل.
    known_ids = {str(item.get("id") or "") for item in SOURCE_REGISTRY}
    candidate = target.lower().strip() or "unknown"
    if candidate in known_ids:
        return candidate
    return SAFE_FALLBACK_ID


def resolve_source_id(source_name: str) -> str:
    """معرف المصدر موثقًا بقيد FK الحي: المعرف المحلي لا يكفي، الجدول الحي هو السلطة.

    المطابقة تُحسب من السجل المحلي (match_source_id)، لكن source_runs مرتبط
    بمفتاح أجنبي على source_registry في Supabase، والجدول الحي قد يتخلف عن
    الملف المحلي حتى تُشغَّل مزامنة السجل. عند توفر القراءة نتحقق من المعرف
    مقابل الجدول الحي؛ المصادر غير المسجلة تُسقط إلى other_marketplaces
    (سلة معروفة موجودة دائمًا) بدل إيقاف حفظ الدفعة كاملة.
    """
    candidate = match_source_id(source_name)
    remote_ids = remote_registry_ids()
    if remote_ids is None:
        return candidate
    if candidate in remote_ids:
        return candidate
    return SAFE_FALLBACK_ID


def sync_remote_registry() -> dict[str, Any]:
    """مزامنة السجل المحلي إلى جدول source_registry الحي (upsert على id).

    تُسجَّل بها المصادر المخططة (PropertyFinder/Bayut/Aqarmap/بوابة الكويت)
    رسميًا في القاعدة فتزول من قائمة الانجراف. تعيد ملخصًا بالعدد والانجراف
    المتبقي ليظهر في حالة الوكيل اليومي بدل فشل صامت عند أول حفظ لاحق.
    """
    if not _remote_reads_enabled():
        return {"status": "not_configured", "count": 0, "error": "supabase غير مضبوط"}
    rows = [
        {
            "id": row["id"],
            "name": row["name"],
            "category": row["category"],
            "connection": row["connection"],
            "role": row["role"],
            "trust_level": row["trustLevel"],
            "scoring_policy": row["scoringPolicy"],
            "evidence_policy": row["evidencePolicy"],
            "status": row["status"],
        }
        for row in SOURCE_REGISTRY
    ]
    request = urllib.request.Request(
        f"{SUPABASE_URL}/rest/v1/source_registry?on_conflict=id",
        data=json.dumps(rows, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={**_headers(), "Prefer": "resolution=merge-duplicates,return=minimal"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.status not in {200, 201, 204}:
                raise RuntimeError(f"Supabase returned HTTP {response.status}")
    except Exception as exc:
        logger.exception("source_registry sync failed")
        return {"status": "failed", "count": 0, "error": str(exc)}
    # إبطال كاش المعرفات القديم: الكاش كان قد التُقط قبل المزامنة، فإبقاؤه يجعل
    # تقرير الانجراف (المحسوب هنا) يقول إن المعرفات المسجلة حديثًا «غير مسجلة»،
    # ويبقي الحفظ يسقطها لسلة other_marketplaces حتى انتهاء مدة الكاش.
    global _remote_ids_cache
    _remote_ids_cache = None
    return {"status": "synced", "count": len(rows), "drift": drift_report()}
