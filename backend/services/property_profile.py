from __future__ import annotations

from typing import Any

from backend.services.request_parser import normalize_text


def _has(text: str, words: tuple[str, ...]) -> bool:
    normalized = normalize_text(text)
    return any(normalize_text(word) in normalized for word in words)


def detect_property_profile(listing) -> dict[str, Any]:
    """تصنيف قانوني/تمويلي تشغيلي من نص الإعلان.

    هذا ليس بديلًا عن الوثيقة الرسمية، لكنه يفصل ما هو مذكور صراحة في الإعلان
    عن التقييم السعري حتى لا تضيع عبارات مثل بيت حكومي أو بنك الائتمان داخل الوصف.
    """
    text = " ".join(
        str(value or "")
        for value in (
            getattr(listing, "property_type", ""),
            getattr(listing, "detail_class", ""),
            getattr(listing, "listing_mode", ""),
            getattr(listing, "summary", ""),
            getattr(listing, "features", ""),
            getattr(listing, "seller_info", ""),
            (getattr(listing, "raw", {}) or {}).get("detailText", ""),
            (getattr(listing, "raw", {}) or {}).get("detailTitle", ""),
        )
    )

    tenure = "غير محدد"
    reasons: list[str] = []
    flags: list[str] = []

    if _has(text, ("بيت حكومي", "حكومي", "بنك الائتمان", "بنك التسليف", "مطلوب للاسكان", "مطلوب للإسكان")):
        tenure = "حكومي/رعاية سكنية"
        reasons.append("ذُكرت عبارة حكومي أو بنك الائتمان/التسليف في الإعلان.")
    elif _has(text, ("سكن خاص", "خاص", "وثيقة حرة", "حر")):
        tenure = "سكن خاص"
        reasons.append("ذُكرت عبارة سكن خاص أو وثيقة/ملك حر.")

    usage = "سكني"
    if _has(text, ("استثماري", "عمارة", "بناية", "شقق مؤجرة", "مؤجر بالكامل", "دخل")):
        usage = "استثماري"
        reasons.append("توجد مؤشرات دخل أو تأجير أو عمارة/بناية.")
    if _has(text, ("تجاري", "محل", "مكاتب", "مجمع", "قسيمة صناعية", "صناعي")):
        usage = "تجاري/صناعي"
        reasons.append("توجد مؤشرات نشاط تجاري أو صناعي.")

    base_type = str(getattr(listing, "property_type", "") or getattr(listing, "detail_class", "") or "")
    asset_class = base_type or "عقار"
    land_terms = ("ارض", "أرض", "فضاء", "قسيمة صناعية", "للبيع قسيمة", "قسيمة فضاء")
    if _has(text, ("بيت", "منزل", "فيلا")) or "بيت" in base_type:
        asset_class = "بيت"
    elif _has(text, ("شقة", "شقتين", "تمليك")) or "شقة" in base_type:
        asset_class = "شقة"
    elif _has(text, ("عمارة", "بناية")):
        asset_class = "عمارة"
    elif _has(text, land_terms) or "أرض" in base_type or "ارض" in base_type:
        asset_class = "أرض/قسيمة"

    finance_status = "غير مذكور"
    if _has(text, ("بنك الائتمان", "بنك التسليف", "مطلوب للاسكان", "مطلوب للإسكان")):
        finance_status = "مرتبط ببنك الائتمان/الإسكان"
        flags.append("يلزم احتساب أو التحقق من مطلوب بنك الائتمان قبل الحكم النهائي.")
    elif _has(text, ("رهن", "مرهون", "تحويل بنك", "بنك")):
        finance_status = "يحتاج تحقق بنكي"
        flags.append("ذُكر بنك/رهن/تحويل؛ يلزم تحقق تمويلي.")

    legal_status = "غير مذكور"
    if _has(text, ("وثيقة", "الوثيقة", "شهادة الاوصاف", "شهادة الأوصاف", "جاهزة للتحويل")):
        legal_status = "مذكور مستند/وثيقة"
        reasons.append("ذُكر مستند أو شهادة أوصاف في الإعلان.")
    if _has(text, ("خالي من المخالفات", "لا يوجد مخالفات")):
        flags.append("الإعلان يذكر خلوه من المخالفات، يحتاج تحقق رسمي.")
    elif _has(text, ("مخالفات", "مخالفة")):
        flags.append("ذُكرت مخالفات؛ يجب خفض الثقة لحين التحقق.")

    confidence = 35
    if tenure != "غير محدد":
        confidence += 20
    if finance_status != "غير مذكور":
        confidence += 15
    if legal_status != "غير مذكور":
        confidence += 15
    if asset_class not in {"عقار", ""}:
        confidence += 10
    if usage != "سكني":
        confidence += 15

    return {
        "assetClass": asset_class,
        "tenure": tenure,
        "usage": usage,
        "financeStatus": finance_status,
        "legalStatus": legal_status,
        "confidence": min(confidence, 95),
        "reasons": reasons or ["لا توجد عبارات قانونية/تمويلية كافية في الإعلان."],
        "flags": flags,
        "source": "تحليل نص الإعلان فقط؛ لا يغني عن وثيقة رسمية أو استعلام وزارة العدل/PACI.",
    }
