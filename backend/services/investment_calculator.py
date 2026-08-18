"""حاسبة الاستثمار العقاري — مقارنة أحياء + حساب العائد + تمويل عقاري.

هذه الوحدة توفر:
1. حاسبة العائد الاستثماري (ROI) الشاملة
2. حاسبة التمويل العقاري (القرض)
3. مقارنة الأحياء بالعائد والسعر والمخاطرة
4. توقع العائد المستقبلي

الاستخدام:
    from backend.services.investment_calculator import calculate_roi, compare_neighborhoods
    roi = calculate_roi(buy_price=280000, rent=800, renovation=15000)
    comparison = compare_neighborhoods(["السالمية", "الجابرية", "حولي"])
"""
from __future__ import annotations

import json
import logging
import urllib.request
from typing import Any

from backend.config import SUPABASE_SERVICE_ROLE_KEY, SUPABASE_URL

logger = logging.getLogger(__name__)


def _headers() -> dict[str, str]:
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }


def _fetch_rows(endpoint: str) -> list[dict]:
    if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
        return []
    request = urllib.request.Request(endpoint, headers=_headers(), method="GET")
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read().decode())
    except Exception as e:
        logger.warning(f"Investment calc fetch failed: {e}")
        return []


# ─── 1. حاسبة العائد الاستثماري (ROI) ───

def calculate_roi(
    buy_price: float,
    monthly_rent: float,
    renovation: float = 0,
    annual_maintenance_pct: float = 1.0,
    vacancy_months: float = 1,
    management_pct: float = 5,
    appreciation_pct: float = 3,
) -> dict[str, Any]:
    """حساب شامل للعائد الاستثماري العقاري.

    Args:
        buy_price: سعر الشراء (د.ك)
        monthly_rent: الإيجار الشهري المتوقع (د.ك)
        renovation: تكلفة الترميم/التجديد (د.ك)
        annual_maintenance_pct: نسبة الصيانة السنوية من الإيجار
        vacancy_months: عدد أشهر الفراغ سنوياً
        management_pct: نسبة إدارة العقار من الإيجار
        appreciation_pct: نسبة ارتفاع قيمة العقار سنوياً
    """
    total_investment = buy_price + renovation
    annual_rent = monthly_rent * 12
    effective_rent = annual_rent * ((12 - vacancy_months) / 12)
    maintenance_cost = effective_rent * (annual_maintenance_pct / 100)
    management_cost = effective_rent * (management_pct / 100)
    net_rental_income = effective_rent - maintenance_cost - management_cost

    # العائد الإيجاري الصافي
    rental_yield = (net_rental_income / total_investment * 100) if total_investment > 0 else 0

    # العائد الكلي (إيجار + ارتفاع القيمة)
    appreciation_gain = buy_price * (appreciation_pct / 100)
    total_return = net_rental_income + appreciation_gain
    total_return_pct = (total_return / total_investment * 100) if total_investment > 0 else 0

    # فترة الاسترداد
    payback_years = (total_investment / net_rental_income) if net_rental_income > 0 else float('inf')

    # القيمة بعد 5 سنوات
    future_value_5y = buy_price * ((1 + appreciation_pct / 100) ** 5)
    total_profit_5y = (future_value_5y - buy_price) + (net_rental_income * 5)
    roi_5y = (total_profit_5y / total_investment * 100) if total_investment > 0 else 0

    # تقييم الفرصة
    if rental_yield >= 8:
        verdict = "فرصة ممتازة"
        verdict_color = "green"
    elif rental_yield >= 6:
        verdict = "فرصة جيدة"
        verdict_color = "blue"
    elif rental_yield >= 4:
        verdict = "فرصة متوسطة"
        verdict_color = "amber"
    else:
        verdict = "فرصة ضعيفة"
        verdict_color = "red"

    return {
        "buy_price": buy_price,
        "renovation": renovation,
        "total_investment": total_investment,
        "monthly_rent": monthly_rent,
        "annual_rent": annual_rent,
        "effective_rent": round(effective_rent, 2),
        "vacancy_months": vacancy_months,
        "maintenance_cost": round(maintenance_cost, 2),
        "management_cost": round(management_cost, 2),
        "net_rental_income": round(net_rental_income, 2),
        "rental_yield_pct": round(rental_yield, 2),
        "appreciation_gain": round(appreciation_gain, 2),
        "total_return": round(total_return, 2),
        "total_return_pct": round(total_return_pct, 2),
        "payback_years": round(payback_years, 1) if payback_years != float('inf') else None,
        "future_value_5y": round(future_value_5y, 0),
        "total_profit_5y": round(total_profit_5y, 0),
        "roi_5y_pct": round(roi_5y, 1),
        "verdict": verdict,
        "verdict_color": verdict_color,
        "monthly_cashflow": round(net_rental_income / 12, 2),
    }


# ─── 2. حاسبة التمويل العقاري ───

def calculate_mortgage(
    property_price: float,
    down_payment_pct: float = 20,
    interest_rate_pct: float = 5.5,
    years: int = 20,
    monthly_rent: float = 0,
) -> dict[str, Any]:
    """حساب أقساط التمويل العقاري والمقارنة مع الإيجار.

    Args:
        property_price: سعر العقار (د.ك)
        down_payment_pct: نسبة الدفعة المقدمة (20% افتراضي)
        interest_rate_pct: نسبة الفائدة السنوية (5.5% افتراضي)
        years: مدة القرض بالسنوات
        monthly_rent: الإيجار الشهري المماثل (للمقارنة)
    """
    down_payment = property_price * (down_payment_pct / 100)
    loan_amount = property_price - down_payment
    monthly_rate = (interest_rate_pct / 100) / 12
    num_payments = years * 12

    # حساب القسط الشهري (ثابت)
    if monthly_rate > 0:
        monthly_payment = loan_amount * (
            monthly_rate * (1 + monthly_rate) ** num_payments
        ) / ((1 + monthly_rate) ** num_payments - 1)
    else:
        monthly_payment = loan_amount / num_payments

    # إجمالي الفائدة
    total_paid = monthly_payment * num_payments
    total_interest = total_paid - loan_amount

    # المقارنة مع الإيجار
    rent_equivalent = monthly_rent if monthly_rent > 0 else monthly_payment
    savings_vs_rent = rent_equivalent - monthly_payment if monthly_rent > 0 else 0

    return {
        "property_price": property_price,
        "down_payment_pct": down_payment_pct,
        "down_payment": round(down_payment, 2),
        "loan_amount": round(loan_amount, 2),
        "interest_rate_pct": interest_rate_pct,
        "years": years,
        "num_payments": num_payments,
        "monthly_payment": round(monthly_payment, 2),
        "total_paid": round(total_paid, 2),
        "total_interest": round(total_interest, 2),
        "monthly_rent_equivalent": round(rent_equivalent, 2),
        "savings_vs_rent": round(savings_vs_rent, 2),
        "verdict": (
            f"القرض أرخص بـ{abs(savings_vs_rent):,.0f} د.ك/شهر من الإيجار"
            if savings_vs_rent > 0
            else f"الإيجار أرخص بـ{abs(savings_vs_rent):,.0f} د.ك/شهر من القرض"
        ) if monthly_rent > 0 else "أدخل الإيجار المماثل للمقارنة",
    }


# ─── 3. مقارنة الأحياء ───

def compare_neighborhoods(areas: list[str]) -> dict[str, Any]:
    """مقارنة الأحياء بالعائد والسعر ومتوسط الإيجار.

    يجلب البيانات من market_listings ويعيد مقارنة شاملة.
    """
    if not areas:
        return {"areas": [], "note": "حدد مناطق للمقارنة"}

    # جلب البيانات من Supabase
    all_rows = _fetch_rows(
        f"{SUPABASE_URL}/rest/v1/market_listings?select=area,price,space,transaction"
        f"&limit=5000"
    )

    if not all_rows:
        return {"areas": [], "note": "لا توجد بيانات كافية للمقارنة"}

    area_data = {}
    for area in areas:
        area_rows = [r for r in all_rows if str(r.get("area") or "") == area]
        sale_rows = [r for r in area_rows if "بيع" in str(r.get("transaction") or "")]
        rent_rows = [r for r in area_rows if "إيجار" in str(r.get("transaction") or "")]

        # متوسط سعر البيع
        sale_prices = [float(r.get("price")) for r in sale_rows if r.get("price")]
        avg_sale = sum(sale_prices) / len(sale_prices) if sale_prices else 0

        # متوسط الإيجار الشهري
        rent_prices = [float(r.get("price")) for r in rent_rows if r.get("price")]
        avg_rent = sum(rent_prices) / len(rent_prices) if rent_prices else 0

        # متوسط المساحة
        spaces = [float(r.get("space")) for r in area_rows if r.get("space")]
        avg_space = sum(spaces) / len(spaces) if spaces else 0

        # سعر المتر
        price_per_m2 = avg_sale / avg_space if avg_space > 0 else 0

        # العائد الإيجاري
        rental_yield = (avg_rent * 12 / avg_sale * 100) if avg_sale > 0 and avg_rent > 0 else 0

        area_data[area] = {
            "area": area,
            "avg_sale_price": round(avg_sale, 0),
            "avg_monthly_rent": round(avg_rent, 0),
            "avg_space_m2": round(avg_space, 0),
            "price_per_m2": round(price_per_m2, 0),
            "rental_yield_pct": round(rental_yield, 2),
            "sale_listings": len(sale_rows),
            "rent_listings": len(rent_rows),
            "total_listings": len(area_rows),
        }

    # ترتيب حسب العائد الإيجاري
    ranked = sorted(area_data.values(), key=lambda x: -x["rental_yield_pct"])

    return {
        "areas": ranked,
        "best_yield": ranked[0] if ranked else None,
        "most_affordable": min(ranked, key=lambda x: x["avg_sale_price"]) if ranked else None,
        "note": "مقارنة بناءً على بيانات الحصاد المتراكمة",
    }


# ─── 4. توقع العائد المستقبلي ───

def forecast_return(
    buy_price: float,
    monthly_rent: float,
    years: int = 5,
    rent_growth_pct: float = 3,
    price_growth_pct: float = 4,
) -> dict[str, Any]:
    """توقع العائد المستقبلي على مدى عدة سنوات.

    Args:
        buy_price: سعر الشراء (د.ك)
        monthly_rent: الإيجار الشهري الحالي (د.ك)
        years: عدد السنوات
        rent_growth_pct: نسبة نمو الإيجار سنوياً
        price_growth_pct: نسبة نمو سعر العقار سنوياً
    """
    yearly_data = []
    cumulative_rent = 0
    current_rent = monthly_rent * 12
    current_price = buy_price

    for year in range(1, years + 1):
        current_rent *= (1 + rent_growth_pct / 100)
        current_price *= (1 + price_growth_pct / 100)
        cumulative_rent += current_rent

        yearly_data.append({
            "year": year,
            "annual_rent": round(current_rent, 0),
            "cumulative_rent": round(cumulative_rent, 0),
            "property_value": round(current_price, 0),
            "appreciation": round(current_price - buy_price, 0),
            "total_return": round(cumulative_rent + (current_price - buy_price), 0),
        })

    final = yearly_data[-1] if yearly_data else {}

    return {
        "buy_price": buy_price,
        "monthly_rent": monthly_rent,
        "years": years,
        "rent_growth_pct": rent_growth_pct,
        "price_growth_pct": price_growth_pct,
        "yearly": yearly_data,
        "final_property_value": final.get("property_value", 0),
        "final_total_return": final.get("total_return", 0),
        "final_roi_pct": round(
            final.get("total_return", 0) / buy_price * 100, 1
        ) if buy_price > 0 else 0,
    }
