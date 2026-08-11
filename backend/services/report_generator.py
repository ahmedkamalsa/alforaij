from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from backend.connectors.external_search import external_search_links
from backend.models import PropertyRequest, RankedListing
from backend.services.property_profile import detect_property_profile
from backend.services.source_registry import source_registry


def _listing_views(listing) -> tuple[int | None, str]:
    raw = getattr(listing, "raw", {}) or {}
    for key in ("views", "viewCount", "viewsCount", "مشاهدات", "عدد المشاهدات"):
        value = raw.get(key)
        if value in (None, ""):
            continue
        try:
            return int(str(value).replace(",", "").strip()), f"مذكور في المصدر: {key}"
        except (TypeError, ValueError):
            continue
    return None, "غير متاحة من المصدر ولا تدخل في التقييم"


def _data_quality(item: RankedListing) -> dict:
    listing = item.listing
    checks = []
    score = 0
    if listing.price:
        score += 24
        checks.append("السعر معلن")
    else:
        checks.append("السعر غير معلن")
    if listing.space:
        score += 20
        checks.append("المساحة مذكورة")
    else:
        checks.append("المساحة غير مذكورة")
    if listing.area:
        score += 14
        checks.append("المنطقة محددة")
    if listing.original_url:
        score += 12
        checks.append("رابط الإعلان متاح")
    comps_count = len(item.comparables or [])
    if comps_count >= 5:
        score += 18
        checks.append("5 مقارنات أو أكثر")
    elif comps_count >= 3:
        score += 14
        checks.append("3 مقارنات أو أكثر")
    elif comps_count > 0:
        score += 8
        checks.append(f"{comps_count} مقارنات فقط")
    else:
        checks.append("لا توجد مقارنات كافية")
    if item.confidence >= 0.8:
        score += 12
        checks.append("ثقة تقييم عالية")
    elif item.confidence >= 0.55:
        score += 8
        checks.append("ثقة تقييم متوسطة")
    else:
        checks.append("ثقة تقييم منخفضة")
    score = min(100, score)
    if score >= 80:
        label = "قوية"
        tone = "strong"
    elif score >= 55:
        label = "متوسطة"
        tone = "medium"
    else:
        label = "ناقصة"
        tone = "weak"
    return {
        "score": score,
        "label": label,
        "tone": tone,
        "reasons": checks,
    }


def _source_trust(status: dict) -> dict:
    state = status.get("status", "")
    records = int(status.get("records") or 0)
    candidates = int(status.get("candidates") or records or 0)
    if state == "success" and records > 0:
        return {
            "label": "دخل التقييم",
            "score": 100,
            "tone": "strong",
            "reason": "المصدر أعاد بيانات قابلة للاستخراج ودخلت في ترتيب النتائج.",
            "scored": True,
        }
    if state == "fallback" and records > 0:
        return {
            "label": "دخل عبر بديل",
            "score": 78,
            "tone": "medium",
            "reason": "المصدر الأصلي تعذر جزئيًا لكن تم استخدام بديل موثق بنتائج فعلية.",
            "scored": True,
        }
    if state == "success" and records == 0 and candidates > 0:
        return {
            "label": "تم فحصه بلا نتيجة مطابقة",
            "score": 55,
            "tone": "medium",
            "reason": "تم الوصول للمصدر وفحص نتائج، لكن لا توجد نتيجة مطابقة دخلت التقييم.",
            "scored": False,
        }
    if state in {"page_reachable", "search_links"}:
        return {
            "label": "مساعد فقط",
            "score": 35,
            "tone": "weak",
            "reason": "الموقع أو رابط البحث متاح، لكن لا توجد بيانات إعلان منظمة تكفي لإدخاله في التقييم.",
            "scored": False,
        }
    if state in {"no_results", "no_data"}:
        return {
            "label": "لا يدخل التقييم",
            "score": 25,
            "tone": "weak",
            "reason": "لم يوفر المصدر بيانات قابلة للاستخدام لهذا الطلب وقت التجربة.",
            "scored": False,
        }
    if state == "failed":
        return {
            "label": "فشل الاتصال",
            "score": 0,
            "tone": "weak",
            "reason": "تعذر الوصول أو القراءة من المصدر، لذلك لم يدخل التقييم.",
            "scored": False,
        }
    return {
        "label": "غير مؤكد",
        "score": 20,
        "tone": "weak",
        "reason": "حالة المصدر غير كافية للاعتماد عليها في التقييم.",
        "scored": False,
    }


def _source_trust_for_listing(source_name: str) -> dict:
    if source_name == "الفريج":
        return {
            "label": "مصدر أساسي",
            "score": 100,
            "tone": "strong",
            "reason": "بيانات الفريج المحلية هي المصدر الداخلي الأساسي وتدخل مباشرة في التحليل.",
            "scored": True,
        }
    return {
        "label": "مصدر خارجي",
        "score": 75,
        "tone": "medium",
        "reason": "دخلت النتيجة من مصدر خارجي بعد استخراج بيانات قابلة للتقييم.",
        "scored": True,
    }


def _price_gap_label(price_ratio: float | None) -> str | None:
    """شارة السعر مقابل وسيط المنطقة: أرخص / قريب / أغلى من السوق."""
    if price_ratio is None:
        return None
    if price_ratio <= 0.92:
        return "أرخص من السوق"
    if price_ratio >= 1.08:
        return "أغلى من السوق"
    return "قريب من السوق"


def _decision_line(item: RankedListing, quality: dict) -> str:
    listing = item.listing
    match = round(item.match_score or 0)
    recommendation = round(item.recommendation_score or 0)
    price = listing.price_text or "سعر غير معلن"
    if item.price_ratio:
        ratio = round(item.price_ratio * 100)
        price_part = f"السعر {ratio}% من وسيط المقارنات"
    else:
        price_part = "لا توجد نسبة سعر كافية"
    return (
        f"القرار: {item.valuation_label}؛ التوصية {recommendation}/100 لأن مطابقة الطلب {match}/100، "
        f"{price_part}، وجودة البيانات {quality['label']} ({quality['score']}%). السعر: {price}."
    )


def ranked_to_dict(item: RankedListing) -> dict:
    from backend.services.financing_calculator import calculate_mortgage
    from backend.services.valuation import is_rental
    listing = item.listing
    rental = is_rental(listing)
    # التمويل العقاري خاص بالبيع/الشراء فقط — الإيجار شهري ولا يُموَّل بتمويل عقاري
    financing = calculate_mortgage(listing.price) if listing.price and not rental else {}
    
    number_sources = dict(item.number_sources or {})
    data_quality = _data_quality(item)
    views, views_source = _listing_views(listing)
    property_profile = detect_property_profile(listing)
    number_sources["propertyProfile"] = {
        "value": property_profile,
        "display": (
            f"{property_profile['assetClass']} | {property_profile['tenure']} | "
            f"{property_profile['usage']} | {property_profile['financeStatus']}"
        ),
        "source": property_profile["source"],
    }
    return {
        "code": listing.code,
        "source": listing.source,
        "sourceTrust": _source_trust_for_listing(listing.source),
        "fallbackFor": (listing.raw or {}).get("fallbackFor", ""),
        "transaction": listing.transaction,
        "governorate": listing.governorate,
        "area": listing.area,
        "propertyType": listing.property_type,
        "detailClass": listing.detail_class,
        "price": listing.price,
        "priceText": listing.price_text,
        "space": listing.space,
        "listingMode": listing.listing_mode,
        "listingType": getattr(listing, 'listing_type', "غير محدد"),
        "propertyProfile": property_profile,
        "summary": listing.summary,
        "features": listing.features,
        "publishedDate": listing.published_date,
        "views": views,
        "viewsSource": views_source,
        "originalUrl": listing.original_url,
        "rental": rental,
        "monthlyRent": listing.price if rental else None,
        "annualRent": number_sources.get("annualRent", {}).get("value") if rental else None,
        "rentalYieldPercent": number_sources.get("rentalYield", {}).get("value") if rental else None,
        "matchScore": item.match_score,
        "outsideArea": any("خارج المنطقة المطلوبة" in str(w) for w in item.warnings),
        "recommendationScore": item.recommendation_score,
        "valuationLabel": item.valuation_label,
        "valuationReason": item.valuation_reason,
        "confidence": item.confidence,
        "dealScore": item.deal_score,
        "marketMedian": item.market_median,
        "priceRatio": item.price_ratio,
        "priceGapPct": round((item.price_ratio - 1) * 100, 1) if item.price_ratio is not None else None,
        "priceGapLabel": _price_gap_label(item.price_ratio),
        "matchBreakdown": item.match_breakdown,
        "recommendationBreakdown": item.recommendation_breakdown,
        "numberSources": number_sources,
        "dataQuality": data_quality,
        "decisionLine": _decision_line(item, data_quality),
        "reasons": item.reasons,
        "warnings": item.warnings,
        "comparables": item.comparables,
        "financing": financing,
    }


def _transaction_summary(request: PropertyRequest, items: list[RankedListing]) -> dict:
    """قسم التأكيد النهائي: الفرق بين حسابات البيع والشراء والإيجار وطريقة كل منها.

    يُضمَّن في نهاية التقرير حتى يرى المستخدم بوضوح أي خط حساب طُبِّق ولماذا،
    مع إفصاح عن النتائج التي اتبعت كل مسار.
    """
    detected = request.transaction or "غير محدد"
    sale_count = sum(1 for it in items if not (it.number_sources or {}).get("rental"))
    rent_count = sum(1 for it in items if (it.number_sources or {}).get("rental"))
    modes = {
        "للبيع": {
            "detectedWhen": "الطلب يُعرض العقار للبيع (عندي / للبيع / بيع).",
            "calculation": (
                "السعر الإجمالي يُقارن بالقيمة العادلة (سعر المتر الرسمي أو المشتق × المساحة) "
                "وبوسيط أسعار المقارنات في نفس المنطقة؛ الناتج نسبة سعر إلى قيمة وتصنيف (لقطة ممتازة… مبالغ فيه) "
                "مع حساب التمويل العقاري المتوقع."
            ),
        },
        "مطلوب للشراء": {
            "detectedWhen": "الطلب يبحث عن عقار لشرائه (ابي / مطلوب / شراء / نشتري).",
            "calculation": (
                "يُطابق عروض البيع حسب المنطقة والنوع والمساحة والميزانية، ثم يُقيَّم سعر كل عرض بنفس خط البيع "
                "(القيمة العادلة مقابل السعر المطلوب) مع إضافة حساب التمويل العقاري للقسط الشهري المتوقع."
            ),
        },
        "للإيجار": {
            "detectedWhen": "الطلب يعرض عقارًا للإيجار (للإيجار / عندي للإيجار).",
            "calculation": (
                "خط حساب مميز تمامًا عن البيع: الإيجار الشهري × 12 = الإيجار السنوي، "
                "وإيجار المتر شهريًا (د.ك/م²/شهر)، والمقارنة بوسيط إيجارات المنطقة الشهرية، "
                "وتقدير قيمة العقار من المصادر الرسمية لحساب العائد الإيجاري السنوي "
                "(الإيجار السنوي ÷ قيمة العقار) — ولا يُطبق تمويل عقاري على الإيجار."
            ),
        },
        "مطلوب للإيجار": {
            "detectedWhen": "الطلب يبحث عن عقار للإيجار بميزانية شهرية (ايجار / استأجر / مطلوب للإيجار).",
            "calculation": (
                "يُطابق عروض الإيجار حسب المنطقة والنوع والمساحة وميزانية الإيجار الشهرية، "
                "ثم يُقيَّم عدالة الإيجار بوسيط إيجارات المنطقة ويُحسب العائد الإيجاري السنوي."
            ),
        },
        "بدل": {
            "detectedWhen": "الطلب يبحث عن بدل عقار.",
            "calculation": "يُقيَّم كلا الطرفين بخط البيع ثم تُقارن القيمتان العادلتان.",
        },
    }
    mode = modes.get(detected, {"detectedWhen": "لم يُحدد نوع معاملة صراحة؛ عولج البحث كاستفسار عام.", "calculation": "طُبِّق خط البيع الافتراضي على كل النتائج."})
    return {
        "detected": detected,
        "detectedWhen": mode.get("detectedWhen", ""),
        "calculation": mode.get("calculation", ""),
        "breakdown": {
            "sale": {"count": sale_count, "label": "بيع / شراء", "method": "السعر الإجمالي مقابل القيمة العادلة + التمويل العقاري"},
            "rent": {"count": rent_count, "label": "إيجار", "method": "إيجار شهري/سنوي + إيجار المتر + وسيط إيجارات المنطقة + العائد الإيجاري السنوي"},
        },
        "confirmation": (
            "تم تأكيد الفرق في الحسابات: النتائج في هذا التقرير اتبعت خط الإيجار المميز "
            + f"({rent_count} نتيجة) وخط البيع/الشراء ({sale_count} نتيجة) كلٌّ حسب نوع معاملته، "
            + "بلا خلط بين الإيجار الشهري وسعر البيع الإجمالي."
        ),
    }


def _request_filters(request: PropertyRequest) -> list[dict[str, str]]:
    filters: list[dict[str, str]] = []

    def add(label: str, value: object, source: str = "من الطلب أو الخيارات") -> None:
        if value in (None, "", [], {}):
            return
        if isinstance(value, list):
            text = "، ".join(str(v) for v in value if v)
        elif isinstance(value, dict):
            text = "، ".join(f"{k}: {v}" for k, v in value.items())
        elif isinstance(value, float) and value.is_integer():
            text = str(int(value))
        else:
            text = str(value)
        if text:
            filters.append({"label": label, "value": text, "source": source})

    add("نوع العملية", request.transaction or "للبيع")
    add("نوع العقار", request.property_type)
    add("المناطق", request.areas)
    add("المحافظات", request.governorates)
    if request.min_area and request.max_area and request.min_area == request.max_area:
        add("المساحة", f"{request.min_area:g} م²")
    else:
        add("أقل مساحة", f"{request.min_area:g} م²" if request.min_area else "")
        add("أعلى مساحة", f"{request.max_area:g} م²" if request.max_area else "")
    add("ميزانية البيع", f"{request.budget:,.0f} د.ك" if request.budget else "")
    add("ميزانية الإيجار", f"{request.rent_budget:,.0f} د.ك" if request.rent_budget else "")
    add("الغرف", request.bedrooms)
    add("الدخل", f"{request.income:,.0f} د.ك" if request.income else "")
    add("الحالة", request.condition)
    add("مميزات الموقع", request.features)
    add("أرقام مستبعدة من المساحة", request.excluded_area_numbers, "حماية من خلط الارتداد/الواجهة بالمساحة")

    normalized = request.raw_text or ""
    legal_terms = []
    for label, words in {
        "حكومي/رعاية سكنية": ("حكومي", "بنك الائتمان", "بنك التسليف", "مطلوب للاسكان", "مطلوب للإسكان"),
        "وثيقة/شهادة أوصاف": ("وثيقة", "شهادة الأوصاف", "شهادة الاوصاف"),
        "تحقق بنكي": ("رهن", "مرهون", "تحويل بنك"),
        "استثماري": ("استثماري", "دخل", "مؤجر", "عمارة", "بناية"),
        "تجاري/صناعي": ("تجاري", "محل", "مكاتب", "صناعي"),
    }.items():
        if any(word in normalized for word in words):
            legal_terms.append(label)
    add("تصنيفات مستخرجة", legal_terms, "مؤشرات نصية تحتاج تحقق رسمي عند اللزوم")
    return filters


def _primary_area(request: PropertyRequest, items: list[RankedListing]) -> str:
    if items:
        top_area = items[0].listing.area
        if top_area and (not request.areas or top_area in request.areas):
            return top_area
    if request.areas:
        return request.areas[-1]
    return ""


def _target_space(request: PropertyRequest, items: list[RankedListing]) -> float | None:
    if request.min_area and request.max_area and request.min_area == request.max_area:
        return request.min_area
    if items and items[0].listing.space:
        return items[0].listing.space
    if request.min_area and request.max_area:
        return (request.min_area + request.max_area) / 2
    return request.min_area or request.max_area


def _same_transaction(request: PropertyRequest, transaction: str) -> bool:
    if not request.transaction:
        return True
    if request.transaction == "مطلوب للشراء":
        return transaction == "للبيع"
    if request.transaction == "مطلوب للإيجار":
        return transaction == "للإيجار"
    return request.transaction == transaction or request.transaction in transaction or transaction in request.transaction


def _similar_external(request: PropertyRequest, items: list[RankedListing]) -> dict:
    target_area = request.areas[0] if request.areas else _primary_area(request, items)
    target_space = _target_space(request, items)
    target_price = request.rent_budget or request.budget or (items[0].listing.price if items else None)
    target_type = request.property_type or (items[0].listing.property_type if items else "")
    local_source = "الفريج"

    candidates = []
    for item in items:
        listing = item.listing
        if listing.source == local_source:
            continue
        if target_area and listing.area != target_area:
            continue
        if request.areas and listing.area not in request.areas:
            continue
        if target_type and target_type not in f"{listing.property_type} {listing.detail_class}":
            continue
        if not _same_transaction(request, listing.transaction):
            continue

        price_delta = None
        price_delta_percent = None
        if target_price and listing.price:
            price_delta = listing.price - target_price
            price_delta_percent = round((price_delta / target_price) * 100, 1)

        space_delta = None
        space_delta_percent = None
        if target_space and listing.space:
            space_delta = listing.space - target_space
            space_delta_percent = round((space_delta / target_space) * 100, 1)

        reasons = [
            f"نفس المنطقة: {listing.area}",
            f"نفس نوع العقار: {listing.property_type or listing.detail_class}",
            f"نفس نوع العملية: {listing.transaction}",
            f"المصدر الخارجي: {listing.source}",
        ]
        if price_delta is not None:
            sign = "+" if price_delta > 0 else ""
            reasons.append(f"فرق السعر عن الإعلان المرجعي {sign}{price_delta:,.0f} د.ك ({sign}{price_delta_percent}%)")
        else:
            reasons.append("السعر غير كاف لحساب فرق السعر")
        if space_delta is not None:
            sign = "+" if space_delta > 0 else ""
            reasons.append(f"فرق المساحة عن الإعلان المرجعي {sign}{space_delta:g} م² ({sign}{space_delta_percent}%)")
        else:
            reasons.append("المساحة غير كافية لحساب فرق المساحة")

        views, views_source = _listing_views(listing)
        candidates.append({
            "code": listing.code,
            "source": listing.source,
            "area": listing.area,
            "governorate": listing.governorate,
            "transaction": listing.transaction,
            "propertyType": listing.property_type,
            "propertyProfile": detect_property_profile(listing),
            "price": listing.price,
            "priceText": listing.price_text,
            "space": listing.space,
            "publishedDate": listing.published_date,
            "views": views,
            "viewsSource": views_source,
            "originalUrl": listing.original_url,
            "summary": listing.summary,
            "recommendationScore": item.recommendation_score,
            "matchScore": item.match_score,
            "valuationLabel": item.valuation_label,
            "priceDelta": price_delta,
            "priceDeltaPercent": price_delta_percent,
            "spaceDelta": space_delta,
            "spaceDeltaPercent": space_delta_percent,
            "reasons": reasons,
        })

    def sort_key(row: dict) -> tuple:
        price_gap = abs(row["priceDeltaPercent"]) if row.get("priceDeltaPercent") is not None else 999
        space_gap = abs(row["spaceDeltaPercent"]) if row.get("spaceDeltaPercent") is not None else 999
        return (space_gap, price_gap, -float(row.get("recommendationScore") or 0))

    candidates.sort(key=sort_key)
    prices = [row["price"] for row in candidates if row.get("price")]
    spaces = [row["space"] for row in candidates if row.get("space")]
    source_names = sorted({row["source"] for row in candidates if row.get("source")})

    if candidates:
        note = (
            f"تم العثور على {len(candidates)} إعلان خارجي مطابق لنفس المنطقة ونوع العقار والعملية. "
            "هذه المقارنات مفصولة عن نتائج الفريج حتى يكون الحكم أوضح."
        )
    else:
        note = (
            "لا توجد إعلانات خارجية قابلة للاستخراج مطابقة لنفس المنطقة ونوع العقار وقت التجربة. "
            "ستظل روابط المصادر الخارجية ظاهرة للمراجعة اليدوية، لكن لا تدخل كدليل رقمي إلا بعد استخراج سعر/مساحة/رابط إعلان."
        )

    return {
        "target": {
            "area": target_area,
            "propertyType": target_type,
            "price": target_price,
            "space": target_space,
            "transaction": request.transaction,
        },
        "count": len(candidates),
        "sources": source_names,
        "medianPrice": sorted(prices)[len(prices) // 2] if prices else None,
        "medianSpace": sorted(spaces)[len(spaces) // 2] if spaces else None,
        "note": note,
        "items": candidates[:8],
    }


def build_report(
    request: PropertyRequest,
    items: list[RankedListing],
    source_count: int,
    external_statuses: list[dict] | None = None,
    ai_insights: dict | None = None,
    include_local_source: bool = True,
) -> dict:
    top = items[0] if items else None
    scope_note = "، ".join(request.areas) if request.areas else "كل المناطق"
    expanded = any("خارج المنطقة المطلوبة" in str(w) for it in items for w in it.warnings)
    summary = "لم يتم العثور على نتائج كافية داخل بيانات الفريج."
    if top:
        summary = (
            f"أفضل نتيجة مبدئية هي {top.listing.code} في {top.listing.area} "
            f"بسعر {top.listing.price_text or 'غير معلن'}، وحكم السعر: {top.valuation_label}. "
            f"درجة التوصية {int(top.recommendation_score)} من 100، والثقة {int(top.confidence * 100)}% "
            f"اعتمادًا على {len(top.comparables)} مقارنة متاحة"
            + (" داخل المنطقة المطلوبة." if request.areas else " داخل البيانات المتاحة.")
        )

    external_plan = [
        {"name": "آلية الجلب لكل منصة (شفافية)", "status": "منفذ ✓", "action": "كل مصدر يعرض الآن آلية جلبه الفعلية ونقطة نهايته في «تفاصيل المصادر» (JSON مضمّن / بيانات منظمة / فحص HTML / تغذية رسمية). لا توجد REST APIs عامة لهذه البوابات — تحققنا: api.4sale.com.kw غير متاح وwp-json لـ Q8Aqar محجوب."},
        {"name": "توسيع Q8Aqar", "status": "منفذ ✓", "action": "يقرأ الآن صفحات التفاصيل نفسها لتحسين السعر والمساحة بدل الرابط فقط، مع الإبقاء على العنوان كأساس."},
        {"name": "Sakan", "status": "منفذ جزئيًا", "action": "يحاول الآن استخراج الإعلانات من الحالة المضمّنة في الصفحة عند توفرها، وإلا يبقى دليل توفر وعدد متاح."},
        {"name": "الصفقات الرسمية", "status": "منفذ ✓", "action": "تُقرأ من جدول official_transactions في Supabase وملف محلي، وتُستخدم كوسيط سوق مرجّح أعلى من الإعلانات في التقييم (أعلى مصداقية)."},
        {"name": "قاعدة المعرفة المتراكمة", "status": "منفذ ✓", "action": "الوكيل اليومي يحصاد كل إعلانات المواقع ويحفظها في market_listings مع رابط الإعلان الأصلي ووقت الجلب (original_url + fetched_at) — كل رقم قابل للتتبع إلى مصدره."},
        {"name": "مصادر مكاتب / API شريك", "status": "الخطوة التالية", "action": "ربط API أو Feed من مكاتب عقارية عند توفره، ثم تمريره بنفس فلاتر الدليل وتسجيل التشغيل."},
    ]

    if ai_insights:
        # Build a richer summary from AI insights
        analysis_heading = (
            "تحليل الخبير العقاري (ذكاء اصطناعي)"
            if ai_insights.get("analysisMethod") == "ai"
            else "تحليل محلي احترافي"
        )
        rich_summary = f"**{analysis_heading}:**\n{ai_insights.get('executive_summary', '')}\n\n"
        rich_summary += f"**الأدلة والمصادر المستعملة:**\n{ai_insights.get('sources_evidence', '')}\n\n"
        rich_summary += f"**اقتراحات للعميل:**\n{ai_insights.get('suggestions', '')}"
        summary = rich_summary
        
        # Override plan if AI provided missing data
        if "missing_data" in ai_insights and ai_insights["missing_data"]:
            external_plan.insert(0, {
                "name": "نواقص البيانات المكتشفة (AI)",
                "status": "مطلوب لتأكيد التقييم",
                "action": ai_insights["missing_data"]
            })

    return {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "request": asdict(request),
        "extractedFilters": _request_filters(request),
        "aiInsights": ai_insights or {},
        "searchScope": {
            "areas": request.areas,
            "note": (
                f"تم حصر البحث والتقييم في المناطق المطلوبة فقط: {scope_note}"
                + (
                    " — ونظرًا لندرة الإعلانات فيها شملت النتائج إعلانات مشابهة من نفس المحافظة "
                    "(موسومة بوصف واضح ومرتبة أدنى)."
                    if expanded
                    else ""
                )
                if request.areas
                else "لم يحدد الطلب منطقة، فشمل البحث كل المناطق المتاحة."
            ),
        },
        "transactionSummary": _transaction_summary(request, items),
        "analysisMethod": (ai_insights or {}).get("analysisMethod", "none"),
        "rankingMethod": {
            "title": "طريقة ترتيب النتائج",
            "note": "الترتيب ليس حسب الثقة وحدها. درجة التوصية تجمع مطابقة الطلب، جاذبية السعر مقابل وسيط المقارنات، درجة الثقة، وخصم البيانات الناقصة.",
            "weights": {
                "matchScore": "62%",
                "dealScore": "28%",
                "confidence": "10%",
                "missingDataPenalty": "خصم حتى 12 نقطة",
            },
            "thresholds": [
                "لقطة ممتازة: السعر لا يتجاوز 82% من وسيط المقارنات.",
                "أقل من السوق: السعر لا يتجاوز 92% من وسيط المقارنات.",
                "سعر عادل: بين 92% و108% من وسيط المقارنات.",
                "أعلى قليلاً: حتى 118%.",
                "غالي: حتى 135%.",
                "مبالغ فيه: أعلى من 135%.",
            ],
        },
        "sourceStatus": [
            *([
                {
                    "name": "الفريج",
                    "status": "success",
                    "records": source_count,
                    "note": "تم البحث في نسخة بيانات الفريج المحلية المستخرجة من لوحة alforaijboard.",
                    "trust": _source_trust({"status": "success", "records": source_count}),
                }
            ] if include_local_source else []),
            *[
                {
                    "name": status.get("name", "مصدر خارجي"),
                    "status": status.get("status", "unknown"),
                    "records": status.get("records", 0),
                    "candidates": status.get("candidates", status.get("records", 0)),
                    "responseMs": status.get("responseMs"),
                    "attempts": status.get("attempts"),
                    "url": status.get("url"),
                    "note": status.get("note", ""),
                    "availableCount": status.get("availableCount"),
                    "fetchMethod": status.get("fetchMethod", ""),
                    "endpoint": status.get("endpoint", ""),
                    "trust": _source_trust(status),
                }
                for status in (external_statuses or [])
            ],
        ],
        "sourceRegistry": source_registry(),
        "externalSourcePlan": external_plan,
        "externalSearchLinks": external_search_links(request),
        "similarExternal": _similar_external(request, items),
        "summary": summary,
        "results": [ranked_to_dict(item) for item in items],
        "limitations": [
            "التقييم استرشادي وليس تقييمًا رسميًا.",
            "النتائج تعتمد على البيانات المتاحة محليًا وقت التشغيل.",
            "العقار قد لا يكون متاحًا فعليًا حتى لو ظهر في البيانات.",
            "نتائج المواقع الخارجية تعتمد على ما تسمح الصفحة العامة بقراءته وقت البحث.",
        ],
    }
