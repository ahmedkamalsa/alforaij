"""خدمة تحليل رسائل الواتساب المُ Forwarded — تستخرج تفاصيل الإعلان العقاري تلقائيًا."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from backend.services.request_parser import (
    KNOWN_AREAS,
    PROPERTY_TYPES,
    detect_area_in_text,
    detect_site_features,
    detect_seller_type,
    extract_area_range,
    extract_rental_income,
    parse_money,
    parse_request,
    normalize_text,
)


@dataclass
class WhatsAppMessage:
    """رسالة واتساب مُحلّلة."""
    raw_text: str
    sender: str = ""
    phone: str = ""
    timestamp: str = ""
    # النتائج المستخرجة
    property_type: str = ""
    transaction: str = ""
    area: str = ""
    governorate: str = ""
    price: float | None = None
    price_text: str = ""
    space: float | None = None
    bedrooms: int | None = None
    features: list[str] = field(default_factory=list)
    seller_type: str = ""
    summary: str = ""
    is_property_listing: bool = False
    confidence: float = 0.0


def _extract_phone(text: str) -> str:
    """استخراج رقم هاتف من الرسالة."""
    patterns = [
        r'(?:\+965|965)?[\s-]?([569]\d{7})',
        r'(?:هاتف|جوال|موبايل|اتصال|رقم)\s*[:：]?\s*([569]\d{7})',
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return f"+965{match.group(1)}"
    return ""


def _extract_sender(text: str) -> str:
    """استخراج اسم المرسل من الرسالة."""
    lines = text.strip().split("\n")
    if lines:
        first_line = lines[0].strip()
        if len(first_line) < 30 and re.match(r'^[\u0600-\u06FF\s]+$', first_line):
            return first_line
    return ""


def _is_property_listing(text: str) -> bool:
    """هل الرسالة إعلان عقاري؟"""
    normalized = normalize_text(text)
    property_keywords = [
        "للبيع", "للإيجار", "للايجار", "مطلوب للشراء", "مطلوب للإيجار",
        "بيت", "شقة", "أرض", "فيلا", "عمارة", "محل", "مكتب",
        "غرف", "دور", "شوارع", "زاوية", "شارعين",
        "الكويت", "العاصمة", "حولي", "الفروانية", "الأحمدي", "الجهراء", "مبارك الكبير",
        "السالمية", "الجابرية", "خيطان", "صباح الأحمد", "جابر الأحمد",
        "مساحه", "المساحه", "المساحة", "م2", "م²",
        "سعر", "Dinars", "د.ك", "دينار",
    ]
    has_property_keyword = any(kw in text for kw in property_keywords)
    has_area = bool(detect_area_in_text(text))
    has_price = parse_money(text) is not None
    score = sum([has_property_keyword, has_area, has_price])
    return score >= 2


def analyze_whatsapp_message(text: str, sender: str = "", phone: str = "") -> WhatsAppMessage:
    """تحليل رسالة واتساب واستخراج تفاصيل الإعلان العقاري."""
    if not text or not text.strip():
        return WhatsAppMessage(raw_text=text, summary="رسالة فارغة")
    clean_text = re.sub(r'[\u200e\u200f\u202a-\u202e\u2066-\u2069\ufeff]', '', text)
    extracted_phone = _extract_phone(clean_text) or phone
    extracted_sender = _extract_sender(clean_text) or sender
    request = parse_request(clean_text)
    area = detect_area_in_text(clean_text)
    governorate = ""
    if area:
        from backend.services.request_parser import AREA_TO_GOVERNORATE
        governorate = AREA_TO_GOVERNORATE.get(area, "")
    price = parse_money(clean_text)
    price_text = ""
    if price:
        if price >= 1_000_000:
            price_text = f"{price/1_000_000:.1f} مليون د.ك"
        elif price >= 1_000:
            price_text = f"{price/1_000:.0f} ألف د.ك"
        else:
            price_text = f"{price:.0f} د.ك"
    min_area, max_area, _ = extract_area_range(clean_text)
    space = max_area or min_area
    bedrooms_match = re.search(r'(\d+)\s*(?:غرف|غرفه|غرفة)', normalize_text(clean_text))
    bedrooms = int(bedrooms_match.group(1)) if bedrooms_match else None
    features = detect_site_features(clean_text)
    seller_type = detect_seller_type(clean_text)
    is_listing = _is_property_listing(clean_text)
    confidence = 0.0
    if is_listing:
        confidence += 0.3
    if area:
        confidence += 0.2
    if price:
        confidence += 0.2
    if request.property_type:
        confidence += 0.15
    if request.transaction:
        confidence += 0.15
    summary_parts = []
    if request.property_type:
        summary_parts.append(request.property_type)
    if area:
        summary_parts.append(area)
    if request.transaction:
        summary_parts.append(request.transaction)
    if price_text:
        summary_parts.append(price_text)
    if space:
        summary_parts.append(f"{space:.0f} م²")
    summary = " — ".join(summary_parts) if summary_parts else clean_text[:100]
    return WhatsAppMessage(
        raw_text=clean_text,
        sender=extracted_sender,
        phone=extracted_phone,
        property_type=request.property_type,
        transaction=request.transaction,
        area=area,
        governorate=governorate,
        price=price,
        price_text=price_text,
        space=space,
        bedrooms=bedrooms,
        features=features,
        seller_type=seller_type,
        summary=summary,
        is_property_listing=is_listing,
        confidence=round(confidence, 2),
    )


def analyze_bulk_messages(text: str) -> list[WhatsAppMessage]:
    """تحليل رسائل متعددة مفصلة بفاصل واضح."""
    messages = []
    parts = re.split(r'\n\s*\n', text.strip())
    for part in parts:
        part = part.strip()
        if not part or len(part) < 10:
            continue
        msg = analyze_whatsapp_message(part)
        if msg.is_property_listing or msg.confidence > 0.3:
            messages.append(msg)
    if not messages and text.strip():
        msg = analyze_whatsapp_message(text)
        if msg.is_property_listing or msg.confidence > 0.2:
            messages.append(msg)
    return messages
