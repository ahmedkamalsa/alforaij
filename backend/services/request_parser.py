from __future__ import annotations

import re

from backend.models import PropertyRequest


AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# ─────────────────────────────────────────────
# جميع مناطق الكويت (120+ منطقة) مع مراعاة
# الكتابات المختلفة في كلتا اللغتين
# ─────────────────────────────────────────────
KNOWN_AREAS = [
    # محافظة العاصمة
    "الديرة", "القبلة", "الشرق", "مرقاب", "كيفان", "الدسمة",
    "الروضة", "الخالدية", "الفيحاء", "اليرموك", "القادسية",
    "النزهة", "الأندلس", "الاندلس", "الشويخ", "الصليبخات",
    "الريان", "العديلية", "غرناطة", "إشبيلية", "اشبيلية",
    "الشامية", "الصوابر", "دسمة", "نزهة", "ضاحية عبدالله السالم",
    "عبدالله السالم", "قرطبة", "بنيد القار", "مطرف",
    # محافظة حولي
    "السالمية", "الجابرية", "حولي", "الرميثية", "بيان",
    "مشرف", "الشعب", "حطين", "سلوى", "الزهراء",
    "البدع", "الفردوس", "صباح السالم", "ميدان حولي",
    "خيطان", "أبو حليفة", "ابو حليفة",
    # محافظة مبارك الكبير
    "صباح السالم", "أبو فطيرة", "ابو فطيرة", "القصور",
    "المسيلة", "صبحان", "العقيلة", "مبارك الكبير",
    "أبو الحصانية", "ابو الحصانية", "فنيطيس", "القرين",
    # محافظة الفروانية
    "الفروانية", "خيطان", "عمان", "الرابية", "أبو فطيرة",
    "الأندلس", "العارضية", "صباح الناصر", "الرحاب",
    "الجهراء الجديدة", "الضجيج", "الرقة",
    # محافظة الأحمدي
    "الأحمدي", "الفحيحيل", "المهبولة", "أبو حليفة",
    "الرقة", "الصباحية", "الوفرة", "الزور", "ميناء عبدالله",
    "هدية", "الخيران", "صباح الأحمد", "صباح الاحمد",
    "العدان", "المنقف", "البصري", "الجليعة", "ضاحية الفحيحيل",
    "بنيدر", "مزيرعة الوفرة", "نويصيب", "أم قدير",
    # محافظة الجهراء
    "الجهراء", "المطلاع", "جابر الأحمد", "جابر الاحمد",
    "سعد العبدالله", "الصليبية", "الوهاب", "تيماء",
    "شمال غرب الصليبيخات", "الواحة", "كاظمة",
    "القصر", "الجهراء الجديدة", "الأمغرة",
]

# إزالة المكررات مع الحفاظ على الترتيب
_seen: set[str] = set()
_unique: list[str] = []
for _a in KNOWN_AREAS:
    if _a not in _seen:
        _seen.add(_a)
        _unique.append(_a)
KNOWN_AREAS = _unique

# ─────────────────────────────────────────────
# أسماء بديلة (Aliases) لكل منطقة
# ─────────────────────────────────────────────
AREA_ALIASES: dict[str, list[str]] = {
    "بنيد القار": ["بنيدالقار", "بنييد القار", "بند القار", "bnaid al-qar", "bnaid al qar", "bneid al-qar"],
    "إشبيلية": ["اشبيلية", "اشبيليه", "إشبيليه", "ishbiliya", "ishbilia", "eshbiliya"],
    "غرناطة": ["غرناطه", "قرناطة", "granada", "gharnata"],
    "قرطبة": ["قرطبه", "القرطبة", "cordoba", "qurtuba"],
    "الأندلس": ["الاندلس", "اندلس", "andalus"],
    "اليرموك": ["يرموك", "yarmouk"],
    "القادسية": ["قادسية", "القادسيه", "qadisiya"],
    "العدان": ["عدان", "addan", "adan"],
    "المنقف": ["منقف", "mangaf", "al-mangaf"],
    "الفحيحيل": ["فحيحيل", "fahaheel", "faheel"],
    "صباح الأحمد": ["صباح الاحمد", "صباح احمد", "sabah al ahmed", "sabah al-ahmad"],
    "جابر الأحمد": ["جابر الاحمد", "جابر احمد", "jaber al ahmed", "jaber al-ahmed"],
    "سعد العبدالله": ["سعد عبدالله", "saad al abdallah", "saad al-abdallah"],
    "شمال غرب الصليبيخات": ["شمال غرب صليبيخات", "north west sulaibikhat", "nwsk"],
    "صباح السالم": ["صباح السالم", "sabah al salem", "sabah al-salem"],
    "السالمية": ["سالمية", "salmiya", "salamiya"],
    "الرميثية": ["رميثية", "rumaithiya", "rumaithia"],
    "المطلاع": ["مطلاع", "mutlaa", "mutla"],
    "أبو فطيرة": ["ابو فطيرة", "ابو فطيره", "abu fatira", "abu-fatira"],
    "الجابرية": ["جابرية", "jabriya", "jabriyya"],
    "خيطان": ["khaitan", "kheitan"],
    "حولي": ["hawalli", "hawally"],
    "بيان": ["bayan"],
    "سلوى": ["salwa", "salwah"],
    "الأحمدي": ["احمدي", "ahmadi", "al-ahmadi"],
    "الجهراء": ["جهراء", "jahra", "al-jahra"],
    "الفروانية": ["فروانية", "farwaniya", "farwaniyya"],
}

PROPERTY_TYPES = {
    "بيت":   ["بيت", "منزل", "فيلا", "قسيمة", "هدام", "دور", "house", "villa"],
    "شقة":   ["شقة", "شقه", "دوبلكس", "apartment", "flat"],
    "أرض":   ["ارض", "أرض", "قسيمة", "قسيمه", "land", "plot"],
    "عمارة": ["عمارة", "عماره", "عقار استثماري", "استثماري", "بناية", "building"],
    "تجاري": ["تجاري", "محل", "مكتب", "مجمع تجاري", "commercial"],
}

# ميزات الموقع المهمة في التقييم
SITE_FEATURES = {
    "زاوية":        ["زاوية", "زاويه", "corner", "زاوي"],
    "شارعين":       ["شارعين", "على شارعين", "واجهتين", "two streets"],
    "شارع رئيسي":   ["شارع رئيسي", "شارع عام", "main street", "طريق رئيسي"],
    "قرب خدمات":    ["قرب الخدمات", "قريب الخدمات", "بالقرب من", "قريب من"],
    "مصعد":         ["مصعد", "elevator", "اسانسير"],
    "موقف سيارات":  ["موقف", "مواقف", "garage", "كراج"],
}

# أنواع البائع
SELLER_TYPES = {
    "مباشر": [
        "المالك مباشرة", "مالك مباشر", "بدون سمسرة", "بدون سمسار",
        "بدون عمولة", "مباشرة من المالك", "مالك", "مباشر",
        "owner direct", "no commission", "بدون وسيط",
    ],
    "مكتب": [
        "مكتب عقاري", "شركة عقارية", "مكتب", "شركة", "office",
        "company", "للتواصل مع الشركة", "agency",
        "بوشملان", "الكويتية للعقار", "دار الوسم",
    ],
}


def normalize_text(text: str) -> str:
    text = (text or "").translate(AR_DIGITS)
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def area_terms(area: str) -> list[str]:
    return [area, *AREA_ALIASES.get(area, [])]


def text_has_area(area: str, text: str) -> bool:
    normalized = normalize_text(text)
    lower_text = (text or "").lower()
    for term in area_terms(area):
        if normalize_text(term) in normalized or term.lower() in lower_text:
            return True
    return False


def detect_site_features(text: str) -> list[str]:
    """استخراج مميزات الموقع من النص (زاوية، شارعين، إلخ)."""
    normalized = normalize_text(text)
    found = []
    for feature, keywords in SITE_FEATURES.items():
        if any(normalize_text(kw) in normalized for kw in keywords):
            found.append(feature)
    return found


def detect_seller_type(text: str) -> str:
    """تحديد نوع البائع: مباشر أو مكتب أو غير محدد."""
    normalized = normalize_text(text)
    for seller_type, keywords in SELLER_TYPES.items():
        if any(normalize_text(kw) in normalized for kw in keywords):
            return seller_type
    return "غير محدد"


def parse_money(text: str) -> float | None:
    text = normalize_text(text)
    million_match = re.search(r"(?:مليون)\s*(?:و\s*)?([0-9]+)?", text)
    if million_match:
        extra = float(million_match.group(1) or 0) * 1000
        return 1_000_000 + extra
    matches = re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*(الف|ألف|دينار|د\.ك|دك)?", text)
    candidates: list[float] = []
    for raw, unit in matches:
        value = float(raw)
        if unit in {"الف", "ألف"}:
            value *= 1000
        candidates.append(value)
    if not candidates:
        return None
    money_words = ("ميزانيه", "حدود", "سعر", "مطلوب", "بياع", "ايجار", "دينار", "د.ك", "دك")
    if any(word in text for word in money_words):
        return max(candidates)
    return None


def extract_area_range(text: str) -> tuple[float | None, float | None, dict[str, float]]:
    text = normalize_text(text)
    excluded: dict[str, float] = {}
    for label in ("ارتداد", "واجهه", "واجهة", "شارع عرض", "عرض الشارع"):
        match = re.search(rf"{label}\s*([0-9]+(?:\.[0-9]+)?)\s*(?:متر|م)", text)
        if match:
            excluded[label] = float(match.group(1))

    range_match = re.search(r"(?:مساحه|المساحه)\s*(?:من)?\s*([0-9]+)\s*(?:الى|إلى|-)\s*([0-9]+)", text)
    if range_match:
        return float(range_match.group(1)), float(range_match.group(2)), excluded

    # دعم كسور عشرية مثل 487.5م²
    exact_match = re.search(
        r"(?:مساحه|المساحه|مساحتها|مساحته|المساحة|مساحة)?\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:متر|م2|م²|م\s*²|متر مربع|م(?:\s|$))",
        text,
    )
    if exact_match:
        value = float(exact_match.group(1))
        return value, value, excluded

    return None, None, excluded


def parse_request(raw_text: str) -> PropertyRequest:
    normalized = normalize_text(raw_text)

    # نوع العملية
    transaction = ""
    if any(word in normalized for word in ("ابي", "ابغى", "مطلوب", "نشتري", "شراء")):
        transaction = "مطلوب للشراء"
    if any(word in normalized for word in ("ايجار", "استأجر", "استاجر")):
        transaction = "للإيجار" if "عندي" in normalized or "اعرض" in normalized else "مطلوب للإيجار"
    if any(word in normalized for word in ("للبيع", "بيع", "عندي", "اعرض")) and "ايجار" not in normalized:
        transaction = "للبيع"
    if "بدل" in normalized:
        transaction = "بدل"

    # نوع العقار
    property_type = ""
    for canonical, aliases in PROPERTY_TYPES.items():
        if any(normalize_text(alias) in normalized for alias in aliases):
            property_type = canonical
            break

    # المناطق
    areas = []
    for area in KNOWN_AREAS:
        if text_has_area(area, raw_text) and area not in areas:
            areas.append(area)

    # المساحة
    min_area, max_area, excluded = extract_area_range(raw_text)
    budget = parse_money(raw_text)
    rent_budget = budget if transaction == "مطلوب للإيجار" else None
    if rent_budget is not None and rent_budget > 10_000:
        rent_budget = None

    # الغرف
    bedrooms_match = re.search(r"([0-9]+)\s*(?:غرف|غرفه|غرفة)", normalized)

    # الدخل
    income_match = re.search(r"(?:دخلها|الدخل|مدخولها)\s*([0-9]+)\s*(?:الف|ألف)?", normalized)
    income = None
    if income_match:
        income = float(income_match.group(1))
        if income < 100:
            income *= 1000

    # الحالة ومميزات الموقع
    condition = [word for word in ("هدام", "صالح للسكن", "سكن المالك", "جديد") if normalize_text(word) in normalized]

    # ميزات الموقع (زاوية، شارعين، إلخ)
    site_features = detect_site_features(raw_text)

    # المميزات العامة
    features = [word for word in ("زاويه", "زاوية", "شارعين", "شارع واحد", "مصعد", "موقف", "مواقف", "قرب الخدمات") if normalize_text(word) in normalized]

    # القصد
    intent = "valuation" if any(word in normalized for word in ("قيم", "تقييم", "سعرها المناسب", "تسوى")) else "search"
    if intent == "valuation" and any(word in normalized for word in ("ابي", "مطلوب", "ابغى", "بحث")):
        intent = "search_and_value"

    return PropertyRequest(
        raw_text=raw_text,
        intent=intent,
        transaction=transaction,
        property_type=property_type,
        areas=areas,
        min_area=min_area,
        max_area=max_area,
        budget=budget if transaction != "مطلوب للإيجار" else None,
        rent_budget=rent_budget,
        bedrooms=int(bedrooms_match.group(1)) if bedrooms_match else None,
        income=income,
        condition=condition,
        features=list(set(features + site_features)),
        excluded_area_numbers=excluded,
    )
