"""الصفقات الرسمية / التسجيل العقاري: أقوى مصدر لتقييم السعر عند توفره.

المصدر ينفّذ وعود «الخطة المستقبلية للمصادر»:
- قراءة الصفقات من جدول official_transactions في Supabase (إن مضبوط) ثم ملف
  data/official_transactions.json المحلي كاحتياط دائم.
- توفير وسيط سعر المتر لكل منطقة من الصفقات الفعلية (أعلى مصداقية من الإعلانات)
  ليدخل في التقييم كمرجع مرجّح أعلى من الإعلانات.
- إعادة الصفقات كـ Listing عادية تدخل في البحث والمطابقة مع وسم المصدر.

التصميم متسامح تمامًا: غياب البيانات أو فشل الشبكة لا يكسر التحليل أبدًا.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import threading
import time
from statistics import median
from typing import Any

from backend.models import Listing, PropertyRequest
from backend.services.request_parser import normalize_text

DATA_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "official_transactions.json")

# ذاكرة مؤقتة قصيرة (3 دقائق): (وقت التحميل، الصفوف المدمجة، فهرس المناطق المبني مسبقًا)
# الفهرس يُبنى مرة واحدة مع كل تحميل فيُستخدم للوسيط مباشرة بدل مسح كل الصفقات لكل إعلان
# ودون الحاجة لمتغيرات منفصلة أو حيلة هوية الكائن (id(rows)) القديمة.
_TRANSACTIONS_CACHE: tuple[float, list[dict[str, Any]], dict[str, list[tuple[float, str]]]] | None = None
_TRANSACTIONS_LOCK = threading.Lock()
_CACHE_TTL = 180
_RECENT_MONTHS = 24  # نافذة «الحديثة» للترجيح الزمني
_MIN_RECENT = 3  # الحد الأدنى من الصفقات الحديثة لقبول نافذة الترجيح الزمني


def _load_local_file() -> list[dict[str, Any]]:
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return []
    return data if isinstance(data, list) else []


def _load_from_supabase() -> list[dict[str, Any]]:
    try:
        from backend.services.supabase_store import fetch_official_transactions

        return fetch_official_transactions()
    except Exception:
        return []


_ARABIC_TO_LATIN = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def _to_float(value: Any) -> float | None:
    """تحويل قيمة إلى رقم حقيقي متسامح: يقبل فواصل الآلاف والمسافات والأرقام النصية
    والعربية الهندية (٢٢٠٠٠٠) — شائعة في ملفات CSV كويتية محلية الصنع."""
    if value in (None, ""):
        return None
    try:
        cleaned = (
            str(value)
            .translate(_ARABIC_TO_LATIN)
            .replace("٫", ".")  # الفاصلة العشرية العربية (U+066B)
            .replace(",", "")
            .replace(" ", "")
            .strip()
        )
        return float(cleaned)
    except (TypeError, ValueError):
        return None


def _merge_rows(supabase_rows: list[dict[str, Any]], local_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """دمج الصفقات بلا تكرار: سكربت الاستيراد يحفظ نفس الصفقة في Supabase وفي الملف
    المحلي معًا، فالجمع المباشر كان يضاعفها (يُتضخم العدد والوسيط). المرجع هو الأولوية
    فيبقى صف Supabase (الأحدث)، ويتحول المحلي احتياطًا فقط لما لا يوجد في Supabase."""
    merged: dict[str, dict[str, Any]] = {}
    for row in supabase_rows + local_rows:
        reference = str(row.get("reference") or row.get("رقم الصفقة") or "")
        if reference:
            merged.setdefault(reference, row)
        else:
            # بلا مرجع: نحتفظ بها كسجل مستقل (لا نملك مفتاحًا للمقارنة)
            merged[f"__no_ref_{id(row)}"] = row
    return list(merged.values())


def _load_cached(force: bool = False) -> tuple[list[dict[str, Any]], dict[str, list[tuple[float, str]]]]:
    """تحميل (الصفوف، فهرس المناطق) معًا في كيان واحد بكاش قصير.

    الدمج بلا تكرار: صفقة واحدة تُحفظ في Supabase وفي الملف معًا، فيُحتسب المرجع
    مرة واحدة فقط (الأولوية لنسخة Supabase الأحدث). الفهرس يُبنى في نفس لحظة
    التحميل فيبقى متزامنًا دائمًا مع الصفوف بلا حيلة إبطال منفصلة.
    """
    global _TRANSACTIONS_CACHE
    now = time.time()
    if not force and _TRANSACTIONS_CACHE is not None and now - _TRANSACTIONS_CACHE[0] < _CACHE_TTL:
        return _TRANSACTIONS_CACHE[1], _TRANSACTIONS_CACHE[2]
    with _TRANSACTIONS_LOCK:
        if not force and _TRANSACTIONS_CACHE is not None and now - _TRANSACTIONS_CACHE[0] < _CACHE_TTL:
            return _TRANSACTIONS_CACHE[1], _TRANSACTIONS_CACHE[2]
        merged = _merge_rows(_load_from_supabase(), _load_local_file())
        index = _build_area_index(merged)
        _TRANSACTIONS_CACHE = (now, merged, index)
        return merged, index


def load_transactions(force: bool = False) -> list[dict[str, Any]]:
    """قراءة الصفقات الرسمية: Supabase أولًا (الأحدث)، ثم الملف المحلي. مع كاش قصير."""
    rows, _ = _load_cached(force)
    return rows


def _row_rate(row: dict[str, Any]) -> float | None:
    """سعر المتر من الصفقة: السعر ÷ المساحة."""
    price = _to_float(row.get("price"))
    space = _to_float(row.get("space"))
    if not price or not space or price <= 0 or space <= 0:
        return None
    return price / space


def _parse_date(value: Any) -> _dt.date | None:
    """تحويل تاريخ النص إلى date (يدعم ISO وشرطة/مائلة وقيم نصية) — None عند الغموض."""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"):
        try:
            return _dt.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _build_area_index(rows: list[dict[str, Any]]) -> dict[str, list[tuple[float, str]]]:
    """فهرس مناطق: منطقة → [(سعر المتر، تاريخ الصفقة)] — يُبنى مرة مع كل تحميل."""
    index: dict[str, list[tuple[float, str]]] = {}
    for row in rows:
        rate = _row_rate(row)
        if rate is None:
            continue
        date_text = str(row.get("date") or row.get("التاريخ") or "")
        index.setdefault(normalize_text(str(row.get("area") or "")), []).append((rate, date_text))
    return index


def get_official_transaction_rate(area_name: str) -> tuple[float | None, int, str]:
    """وسيط سعر المتر من الصفقات الرسمية الفعلية للمنطقة (مرجع مرجّح أعلى من الإعلانات).

    ترجيح زمني حتمي: يستخدم الصفقات الحديثة (آخر 24 شهرًا) عندما يتوفر عدد كافٍ (≥3)،
    وإلا يسقط لوسيط كامل السجل مع الإفصاح عن النافذة المستخدمة.
    يعيد (سعر المتر الوسيط، عدد الصفقات المستخدمة، وصف النافذة الزمنية).
    """
    if not area_name:
        return None, 0, ""
    _, index = _load_cached()
    entries = index.get(normalize_text(area_name)) or []
    if not entries:
        return None, 0, ""
    # حدّ «آخر 24 شهرًا» بالشهور التقويمية الفعلية (لا أيام تقريبية 720)
    today = _dt.date.today()
    year, month = today.year, today.month - _RECENT_MONTHS
    while month <= 0:
        month += 12
        year -= 1
    cutoff = _dt.date(year, month, 1)
    recent = [
        (rate, date_text)
        for rate, date_text in entries
        if (parsed := _parse_date(date_text)) and parsed >= cutoff
    ]
    if len(recent) >= _MIN_RECENT:
        rates = [rate for rate, _ in recent]
        return round(median(rates), 2), len(rates), f"آخر {_RECENT_MONTHS} شهرًا"
    rates = [rate for rate, _ in entries]
    return round(median(rates), 2), len(rates), "كامل السجل المتاح"


def _transaction_listing(row: dict[str, Any], index: int) -> Listing:
    area = str(row.get("area") or "غير محددة")
    price_value = _to_float(row.get("price"))
    space_value = _to_float(row.get("space"))
    property_type = str(row.get("property_type") or "عقارات")
    date_value = str(row.get("date") or row.get("التاريخ") or "")
    reference = str(row.get("reference") or row.get("رقم الصفقة") or f"OFF-{index}")
    return Listing(
        code=f"OFF-{reference}",
        transaction=str(row.get("transaction_type") or "للبيع"),
        governorate="",
        area=area,
        property_type=property_type,
        detail_class="صفقة رسمية مسجلة",
        price=price_value,
        price_text=f"{price_value:,.0f} د.ك" if price_value else "غير معلن",
        space=space_value,
        listing_mode="رسمي",
        summary=f"صفقة رسمية مسجلة في {area} ({property_type})" + (f" بتاريخ {date_value}" if date_value else ""),
        features=f"صفقة رسمية {property_type} في {area}",
        published_date=date_value,
        original_url=str(row.get("original_url") or row.get("url") or ""),
        source="الصفقات الرسمية",
        listing_type="رسمي",
        raw={
            "official": True,
            "reference": reference,
            "priceSource": "سجل صفقات رسمي (تسجيل عقاري)",
        },
    )


def search(request: PropertyRequest) -> tuple[list[Listing], dict[str, Any]]:
    """إرجاع الصفقات الرسمية المطابقة للمنطقة المطلوبة (أو كلها إن لم تُحدد)."""
    rows = load_transactions()
    transactions: list[Listing] = []
    for index, row in enumerate(rows):
        area = str(row.get("area") or "")
        # عند تحديد مناطق: صفقة بلا منطقة أو خارجها لا تدخل (سابقًا كانت الصفقة
        # بلا منطقة تتسرب إلى أي طلب لأن شرط area الصريح كان يمر عليها)
        if request.areas and not any(
            area and normalize_text(area) == normalize_text(requested) for requested in request.areas
        ):
            continue
        listing = _transaction_listing(row, index)
        if request.property_type and request.property_type != "عقارات":
            if request.property_type not in (listing.property_type + " " + listing.detail_class):
                continue
        transactions.append(listing)

    if rows:
        note = f"تمت قراءة {len(rows)} صفقة رسمية"
        if request.areas:
            note += f"؛ منها {len(transactions)} في المناطق المطلوبة"
        note += ". تُستخدم كمرجع سوق مرجّح أعلى من الإعلانات عند توفر صفقات بنفس المنطقة."
    else:
        note = (
            "لا توجد صفقات رسمية مستوردة بعد. أضف صفقات عبر scripts/import_official_transactions.py "
            "أو املأ data/official_transactions.json ليُستخدم هذا المصدر كمرجع تقييم مرجّح."
        )
    return transactions, {
        "name": "الصفقات الرسمية",
        "status": "success" if transactions else "no_data",
        "records": len(transactions),
        "candidates": len(rows),
        "responseMs": 0,
        "url": "",
        "note": note,
    }
