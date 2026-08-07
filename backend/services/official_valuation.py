import json
import os
from typing import Any
from backend.services.request_parser import normalize_text, AREA_ALIASES

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "area_benchmarks.json")

def load_benchmarks() -> dict[str, float]:
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

AREA_BENCHMARKS = load_benchmarks()

def derive_market_benchmark(area_name: str, listings: list | None) -> tuple[float | None, int]:
    """اشتقاق وسيط سعر المتر من الإعلانات الفعلية في المنطقة عند غياب معيار رسمي.

    يعيد (سعر المتر الوسيط، عدد الأدلة المستخدمة). حتمي بالكامل — لا عشوائية.
    """
    if not area_name or not listings:
        return None, 0
    rates = []
    for listing in listings:
        if listing.area == area_name and listing.price and listing.space:
            rates.append(listing.price / listing.space)
    if not rates:
        return None, 0
    rates.sort()
    return rates[len(rates) // 2], len(rates)

def get_area_benchmark(area_name: str) -> float | None:
    """إرجاع وسيط سعر المتر للمنطقة بناءً على الاسم أو الاسم البديل."""
    if not area_name:
        return None
        
    normalized_target = normalize_text(area_name)
    
    # محاولة المطابقة المباشرة
    for known_area, price in AREA_BENCHMARKS.items():
        if normalize_text(known_area) == normalized_target:
            return price
            
    # البحث في الأسماء البديلة
    for known_area, price in AREA_BENCHMARKS.items():
        aliases = AREA_ALIASES.get(known_area, [])
        for alias in aliases:
            if normalize_text(alias) == normalized_target:
                return price
                
    return None

def calculate_valuation(area_name: str, space: float | None, site_features: list[str]) -> tuple[float | None, list[dict[str, Any]]]:
    """
    حساب القيمة العادلة للعقار بناءً على:
    1. السعر الأساسي (وسيط سعر المتر في المنطقة × المساحة)
    2. تعديلات الموقع (زاوية، شارعين، إلخ)
    """
    if not space or space <= 0:
        return None, []
        
    base_price_per_sqm = get_area_benchmark(area_name)
    if not base_price_per_sqm:
        return None, []
        
    base_valuation = base_price_per_sqm * space
    breakdown = [{"factor": "السعر الأساسي للمنطقة", "value": base_valuation}]
    
    final_valuation = base_valuation
    
    # تعديلات الموقع
    features_text = " ".join([normalize_text(f) for f in site_features])
    
    if "زاويه" in features_text or "زاوية" in features_text:
        corner_bonus = base_valuation * 0.10  # +10% للزاوية
        final_valuation += corner_bonus
        breakdown.append({"factor": "ميزة الزاوية (+10%)", "value": corner_bonus})
        
    if "شارعين" in features_text:
        two_streets_bonus = base_valuation * 0.15  # +15% للشارعين
        final_valuation += two_streets_bonus
        breakdown.append({"factor": "ميزة شارعين (+15%)", "value": two_streets_bonus})
        
    if "شارع رئيسي" in features_text:
        main_street_bonus = base_valuation * 0.12  # +12% للشارع الرئيسي
        final_valuation += main_street_bonus
        breakdown.append({"factor": "ميزة الشارع الرئيسي (+12%)", "value": main_street_bonus})
        
    return final_valuation, breakdown

def assess_deal_quality(asking_price: float | None, fair_value: float | None) -> str:
    """تقييم جودة الصفقة مقارنة بالسعر العادل."""
    if not asking_price or not fair_value:
        return "غير قابل للتقييم"
        
    ratio = asking_price / fair_value
    
    if ratio < 0.85:
        return "لقطة ممتازة (أقل من السوق بوضوح)"
    elif ratio <= 0.95:
        return "فرصة جيدة (أقل من السوق)"
    elif ratio <= 1.05:
        return "سعر عادل (مطابق للسوق)"
    elif ratio <= 1.15:
        return "مرتفع قليلاً"
    else:
        return "مبالغ فيه"
