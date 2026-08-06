def calculate_mortgage(property_value: float, down_payment_percent: float = 0.30, 
                       interest_rate: float = 0.045, years: int = 15) -> dict[str, float]:
    """
    حساب التمويل العقاري التقريبي في الكويت.
    - الدفعة المقدمة المعتادة: 30% إلى 40% (البنوك تمول حتى 70000 للسكني عادة، ولكن كتمويل عقاري عام نأخذ نسبة)
    - الفائدة المعتادة: ~4.5% سنوياً
    - المدة المعتادة: 15 سنة
    """
    if not property_value or property_value <= 0:
        return {}
        
    down_payment = property_value * down_payment_percent
    loan_amount = property_value - down_payment
    
    # حساب القسط الشهري (قانون القسط الثابت)
    # M = P [ i(1 + i)^n ] / [ (1 + i)^n - 1]
    # P = القرض, i = الفائدة الشهرية, n = عدد الأشهر
    
    monthly_interest = interest_rate / 12
    num_months = years * 12
    
    if monthly_interest > 0:
        monthly_payment = loan_amount * (monthly_interest * (1 + monthly_interest)**num_months) / ((1 + monthly_interest)**num_months - 1)
    else:
        monthly_payment = loan_amount / num_months
        
    total_payment = monthly_payment * num_months
    total_interest = total_payment - loan_amount
    
    return {
        "property_value": property_value,
        "down_payment": down_payment,
        "loan_amount": loan_amount,
        "monthly_payment": round(monthly_payment, 2),
        "total_interest": round(total_interest, 2),
        "interest_rate": interest_rate,
        "years": years
    }
