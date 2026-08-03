from __future__ import annotations

import re

from backend.models import PropertyRequest


AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

KNOWN_AREAS = [
    "المطلاع",
    "صباح الاحمد",
    "صباح الأحمد",
    "صباح السالم",
    "السالمية",
    "الرميثية",
    "حولي",
    "الجهراء",
    "جابر الاحمد",
    "جابر الأحمد",
    "شمال غرب الصليبيخات",
    "الفحيحيل",
    "سعد العبدالله",
    "الفروانية",
    "الفردوس",
    "صباح الناصر",
    "الدسمة",
]

PROPERTY_TYPES = {
    "بيت": ["بيت", "منزل", "فيلا", "قسيمة", "هدام", "دور"],
    "شقة": ["شقة", "شقه", "دوبلكس"],
    "أرض": ["ارض", "أرض", "قسيمة"],
    "عمارة": ["عمارة", "عقار استثماري", "استثماري", "بناية"],
    "تجاري": ["تجاري", "محل", "مكتب"],
}


def normalize_text(text: str) -> str:
    text = (text or "").translate(AR_DIGITS)
    text = re.sub(r"[إأآا]", "ا", text)
    text = re.sub(r"ى", "ي", text)
    text = re.sub(r"ة", "ه", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


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

    exact_match = re.search(r"(?:مساحه|المساحه|مساحتها|مساحته)\s*[:=]?\s*([0-9]+(?:\.[0-9]+)?)\s*(?:متر|م2|م²|متر مربع)?", text)
    if exact_match:
        value = float(exact_match.group(1))
        return value, value, excluded

    return None, None, excluded


def parse_request(raw_text: str) -> PropertyRequest:
    normalized = normalize_text(raw_text)
    transaction = ""
    if any(word in normalized for word in ("ابي", "ابغى", "مطلوب", "نشتري", "شراء")):
        transaction = "مطلوب للشراء"
    if any(word in normalized for word in ("ايجار", "استأجر", "استاجر")):
        transaction = "للإيجار" if "عندي" in normalized or "اعرض" in normalized else "مطلوب للإيجار"
    if any(word in normalized for word in ("للبيع", "بيع", "عندي", "اعرض")) and "ايجار" not in normalized:
        transaction = "للبيع"
    if "بدل" in normalized:
        transaction = "بدل"

    property_type = ""
    for canonical, aliases in PROPERTY_TYPES.items():
        if any(normalize_text(alias) in normalized for alias in aliases):
            property_type = canonical
            break

    areas = []
    for area in KNOWN_AREAS:
        if normalize_text(area) in normalized and area not in areas:
            areas.append(area)

    min_area, max_area, excluded = extract_area_range(raw_text)
    budget = parse_money(raw_text)
    rent_budget = budget if transaction == "مطلوب للإيجار" else None
    if rent_budget is not None and rent_budget > 10_000:
        rent_budget = None

    bedrooms_match = re.search(r"([0-9]+)\s*(?:غرف|غرفه|غرفة)", normalized)
    income_match = re.search(r"(?:دخلها|الدخل|مدخولها)\s*([0-9]+)\s*(?:الف|ألف)?", normalized)
    income = None
    if income_match:
        income = float(income_match.group(1))
        if income < 100:
            income *= 1000

    condition = [word for word in ("هدام", "صالح للسكن", "سكن المالك", "جديد") if normalize_text(word) in normalized]
    features = [word for word in ("زاويه", "شارعين", "شارع واحد", "مصعد", "موقف", "مواقف", "قرب الخدمات") if normalize_text(word) in normalized]

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
        features=features,
        excluded_area_numbers=excluded,
    )

