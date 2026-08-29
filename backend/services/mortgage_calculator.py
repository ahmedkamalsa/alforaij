"""حاسبة الرهن العقاري — مقارنة بنوك الكويت الأربعة.

المصادر:
- KFH (بيت التمويل الكويتي): kfh.com — تقارير عقارية Q1 2026
- KBK (البنك الكويتي للتجارة): kbk.com.kw — تمويل عقاري
- CBK (البنك التجاري الكويتي): cbk.com — رهن عقاري
- Boubyan (بنك بوبيان): boubyanbank.com — تمويل سكني

ملاحظة: الفوائد تقريبية وتتغير حسب العميل وال seguro.
البنوك الكويتية تقدم تمويل حتى 80% للسكني و70% للاستثماري.
"""
from __future__ import annotations

from typing import Optional

# ── بنوك الكويت — بيانات الفائدة والمدة ──
KUWAIT_BANKS = {
    "KFH": {
        "name": "بيت التمويل الكويتي",
        "name_en": "Kuwait Finance House",
        "rate": 4.50,
        "max_years": 25,
        "max_finance_pct": 80,  # % تمويل أقصى للسكني
        "min_down_pct": 20,
        "features": ["أكبر بنك إسلامي", "تمويل حتى 80%", "بدون عمولة ائتمان"],
        "url": "https://www.kfh.com",
    },
    "KBK": {
        "name": "البنك الكويتي للتجارة",
        "name_en": "Al-Ahli United Bank (KBK)",
        "rate": 4.75,
        "max_years": 20,
        "max_finance_pct": 75,
        "min_down_pct": 25,
        "features": ["تخفيض فائدة لل wnkala", "تمويل حتى 75%"],
        "url": "https://www.kbk.com.kw",
    },
    "CBK": {
        "name": "البنك التجاري الكويتي",
        "name_en": "Commercial Bank of Kuwait",
        "rate": 5.00,
        "max_years": 25,
        "max_finance_pct": 80,
        "min_down_pct": 20,
        "features": ["أقدم بنوك الكويت", "خدمة عملاء ممتازة"],
        "url": "https://www.cbk.com",
    },
    "Boubyan": {
        "name": "بنك بوبيان",
        "name_en": "Boubyan Bank",
        "rate": 4.25,
        "max_years": 20,
        "max_finance_pct": 80,
        "min_down_pct": 20,
        "features": ["أقل فائدة", "تطبيق رقمي ممتاز", "approve سريع"],
        "url": "https://www.boubyanbank.com",
    },
}


def calculate_monthly_payment(
    loan_amount: float,
    annual_rate: float,
    years: int,
) -> float:
    """حساب القسط الشهري using standard amortization formula.
    
    M = P × [r(1+r)^n] / [(1+r)^n - 1]
    """
    if loan_amount <= 0 or years <= 0:
        return 0.0
    monthly_rate = annual_rate / 100 / 12
    num_payments = years * 12
    if monthly_rate == 0:
        return loan_amount / num_payments
    factor = (1 + monthly_rate) ** num_payments
    return loan_amount * (monthly_rate * factor) / (factor - 1)


def calculate_total_interest(
    loan_amount: float,
    monthly_payment: float,
    years: int,
) -> float:
    """حساب إجمالي الفائدة المدفوعة."""
    total_paid = monthly_payment * years * 12
    return total_paid - loan_amount


def compare_banks(
    property_value: float,
    down_payment_pct: float = 30.0,
    years: int = 20,
    salary: Optional[float] = None,
) -> dict:
    """مقارنة التمويل العقاري بين بنوك الكويت الأربعة.
    
    Args:
        property_value: قيمة العقار بالدينار الكويتي
        down_payment_pct: نسبة الدفعة المقدمة (0-100)
        years: مدة التمويل بالسنوات
        salary: الراتب الشهري (اختياري — لحساب نسبة الاقساط/الراتب)
    
    Returns:
        مقارنة شاملة بين البنوك مع توصية
    """
    if property_value <= 0:
        return {"error": "قيمة العقار يجب أن تكون أكبر من صفر"}
    
    down_amount = property_value * (down_payment_pct / 100)
    loan_amount = property_value - down_amount
    
    banks_comparison = []
    best_bank = None
    lowest_monthly = float("inf")
    
    for code, info in KUWAIT_BANKS.items():
        # التحقق من الحد الأقصى للتمويل
        max_loan = property_value * (info["max_finance_pct"] / 100)
        actual_loan = min(loan_amount, max_loan)
        
        # التحقق من الحد الأقصى للمدة
        actual_years = min(years, info["max_years"])
        
        monthly = calculate_monthly_payment(actual_loan, info["rate"], actual_years)
        total_interest = calculate_total_interest(actual_loan, monthly, actual_years)
        total_paid = monthly * actual_years * 12 + down_amount
        
        # نسبة القسط من الراتب
        salary_ratio = (monthly / salary * 100) if salary and salary > 0 else None
        
        # تقييم: هل القسط يتجاوز 40% من الراتب؟
        affordable = salary_ratio is None or salary_ratio <= 40
        
        bank_data = {
            "code": code,
            "name": info["name"],
            "name_en": info["name_en"],
            "rate": info["rate"],
            "max_years": info["max_years"],
            "monthly_payment": round(monthly, 2),
            "total_interest": round(total_interest, 2),
            "total_paid": round(total_paid, 2),
            "loan_amount": round(actual_loan, 2),
            "down_payment": round(down_amount, 2),
            "years": actual_years,
            "features": info["features"],
            "url": info["url"],
            "affordable": affordable,
            "salary_ratio": round(salary_ratio, 1) if salary_ratio else None,
        }
        
        banks_comparison.append(bank_data)
        
        # أفضل بنك = أقل قسط شهري + متوافق مع الراتب
        if monthly < lowest_monthly and affordable:
            lowest_monthly = monthly
            best_bank = code
    
    # ترتيب حسب القسط الشهري (الأقل أولاً)
    banks_comparison.sort(key=lambda b: b["monthly_payment"])
    
    # ملخص التوصية
    recommendation = _build_recommendation(banks_comparison, best_bank, salary)
    
    return {
        "property_value": property_value,
        "down_payment_pct": down_payment_pct,
        "down_payment_amount": round(down_amount, 2),
        "loan_amount": round(loan_amount, 2),
        "requested_years": years,
        "banks": banks_comparison,
        "best_bank": best_bank,
        "recommendation": recommendation,
        "salary": salary,
    }


def _build_recommendation(banks: list, best_code: Optional[str], salary: Optional[float]) -> dict:
    """بناء توصية ذكية."""
    if not banks:
        return {"summary": "لا توجد بيانات بنوك"}
    
    best = next((b for b in banks if b["code"] == best_code), banks[0])
    
    summary_parts = [
        f"أفضل خيار: {best['name']} بقسط {best['monthly_payment']:,.0f} د.ك/شهر"
    ]
    
    if salary and salary > 0:
        ratio = best["salary_ratio"] or 0
        if ratio <= 30:
            summary_parts.append(f"✅ نسبة مريحة ({ratio:.0f}% من الراتب)")
        elif ratio <= 40:
            summary_parts.append(f"⚠️ نسبة مقبولة ({ratio:.0f}% من الراتب)")
        else:
            summary_parts.append(f"🔴 نسبة مرتفعة ({ratio:.0f}% من الراتب) — يُنصح بزيادة الدفعة المقدمة")
    
    # فرق بين الأعلى والأقل
    if len(banks) >= 2:
        diff = banks[-1]["monthly_payment"] - banks[0]["monthly_payment"]
        if diff > 0:
            summary_parts.append(f"فرق {diff:,.0f} د.ك/شهر بين الأعلى والأقل")
    
    return {
        "summary": " — ".join(summary_parts),
        "best_code": best_code,
        "best_monthly": best["monthly_payment"],
        "best_rate": best["rate"],
    }


def format_mortgage_result(result: dict) -> str:
    """تنسيق النتيجة للعرض في الواجهة."""
    if "error" in result:
        return result["error"]
    
    lines = [
        f"💰 مقارنة التمويل العقاري — {result['property_value']:,.0f} د.ك",
        f"📊 الدفعة المقدمة: {result['down_payment_amount']:,.0f} د.ك ({result['down_payment_pct']}%)",
        f"🏦 مبلغ القرض: {result['loan_amount']:,.0f} د.ك",
        f"📅 المدة المطلوبة: {result['requested_years']} سنة",
        "",
        "┌─────────────────────────────────────────────┐",
    ]
    
    for bank in result["banks"]:
        flag = "✅" if bank["code"] == result.get("best_bank") else "  "
        lines.append(
            f"{flag} {bank['name']}"
        )
        lines.append(
            f"   القسط: {bank['monthly_payment']:,.0f} د.ك/شهر | "
            f"الفائدة: {bank['rate']}% | "
            f"المدة: {bank['years']} سنة"
        )
        if bank.get("salary_ratio"):
            lines.append(f"   نسبة الراتب: {bank['salary_ratio']:.0f}%")
        lines.append("")
    
    lines.append("└─────────────────────────────────────────────┘")
    
    rec = result.get("recommendation", {})
    if rec.get("summary"):
        lines.append(f"\n🎯 {rec['summary']}")
    
    return "\n".join(lines)
