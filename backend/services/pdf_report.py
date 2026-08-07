"""توليد تقرير تقييم عقاري احترافي بالعربية بصيغة PDF باستخدام reportlab.

- تشكيل واتجاه النص العربي عبر arabic_reshaper + python-bidi.
- خط Tahoma (يدعم العربية) من خطوط النظام، مع بديل DejaVu على لينكس.
- شعار مرسوم برمجيًا (لا يعتمد على ملف صورة)، رأس ترحيبي، جداول، وتذييل صفحات.
"""
from __future__ import annotations

import io
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import arabic_reshaper
from bidi.algorithm import get_display
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

NAVY = colors.HexColor("#0f2a4a")
NAVY_LIGHT = colors.HexColor("#1c4168")
GOLD = colors.HexColor("#c9a227")
LIGHT = colors.HexColor("#f4f6f8")
GRAY = colors.HexColor("#5a6472")
BORDER = colors.HexColor("#d7dce2")

_FONT_NAME = "Tahoma"
_FONT_BOLD = "Tahoma-Bold"
_STYLE_CACHE: dict[str, ParagraphStyle] | None = None


def _register_fonts() -> None:
    """تسجيل خط يدعم العربية. يحاول Tahoma (ويندوز) ثم DejaVu (لينكس)، ويسقط لخط مدمج عند الفشل."""
    global _FONT_NAME, _FONT_BOLD
    if _FONT_NAME in pdfmetrics.getRegisteredFontNames():
        return
    candidates = [
        (Path("C:/Windows/Fonts/tahoma.ttf"), Path("C:/Windows/Fonts/tahomabd.ttf")),
        (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
        (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
        (Path("/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"), Path("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")),
    ]
    for regular, bold in candidates:
        if regular.exists():
            try:
                pdfmetrics.registerFont(TTFont("Tahoma", str(regular)))
                pdfmetrics.registerFont(TTFont("Tahoma-Bold", str(bold if bold.exists() else regular)))
                _FONT_NAME = "Tahoma"
                _FONT_BOLD = "Tahoma-Bold"
                return
            except Exception:
                continue
    # سقوط آمن: خط مدمج (لن يُشكَّل العربي بشكل صحيح لكن الملف يُولَّد)
    _FONT_NAME = "Helvetica"
    _FONT_BOLD = "Helvetica-Bold"


def _shape(text: str) -> str:
    """تشكيل النص العربي وضبط اتجاهه للعرض في PDF."""
    reshaped = arabic_reshaper.reshape(text)
    return get_display(reshaped)


def _esc(value: Any) -> str:
    return str(value if value is not None else "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def ar(text: Any) -> str:
    """نص عربي آمن للتضمين في Paragraph."""
    return _shape(_esc(text))


def ar_rich(text: Any) -> str:
    """نص يدعم ترميز **عريض** مع تشكيل عربي آمن (بدون مخاطرة بكسر وسوم reportlab)."""
    escaped = _esc(text)
    parts = re.split(r"(\*\*[^*]+\*\*)", escaped)
    out: list[str] = []
    for part in parts:
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            out.append(f"<b>{_shape(part[2:-2])}</b>")
        else:
            out.append(_shape(part))
    return "".join(out)


def money(value: Any) -> str:
    try:
        num = float(value)
        return f"{num:,.0f} د.ك"
    except (TypeError, ValueError):
        return "غير معلن"


# ---------------------------------------------------------------------------
# أنماط
# ---------------------------------------------------------------------------
def _styles() -> dict[str, ParagraphStyle]:
    """بناء الأنماط مرة واحدة فقط بعد تسجيل الخطوط."""
    global _STYLE_CACHE
    if _STYLE_CACHE is None:
        _register_fonts()
        _STYLE_CACHE = {
            "h1": ParagraphStyle("h1", fontName=_FONT_BOLD, fontSize=19, leading=24, textColor=colors.white, alignment=TA_RIGHT),
            "subtitle": ParagraphStyle("subtitle", fontName=_FONT_NAME, fontSize=9.5, leading=13, textColor=GOLD, alignment=TA_RIGHT),
            "section": ParagraphStyle("section", fontName=_FONT_BOLD, fontSize=13, leading=17, textColor=NAVY, alignment=TA_RIGHT, spaceBefore=10, spaceAfter=2),
            "body": ParagraphStyle("body", fontName=_FONT_NAME, fontSize=9.5, leading=15, textColor=colors.HexColor("#232a33"), alignment=TA_RIGHT),
            "small": ParagraphStyle("small", fontName=_FONT_NAME, fontSize=8, leading=11, textColor=GRAY, alignment=TA_RIGHT),
            "cell": ParagraphStyle("cell", fontName=_FONT_NAME, fontSize=8.5, leading=12, textColor=colors.HexColor("#232a33"), alignment=TA_RIGHT),
            "cell_head": ParagraphStyle("cell_head", fontName=_FONT_BOLD, fontSize=8.5, leading=12, textColor=colors.white, alignment=TA_CENTER),
            "monogram": ParagraphStyle("monogram", fontName=_FONT_BOLD, fontSize=24, leading=28, textColor=GOLD, alignment=TA_CENTER),
            "box_title": ParagraphStyle("box_title", fontName=_FONT_BOLD, fontSize=9.5, leading=13, textColor=NAVY, alignment=TA_RIGHT),
        }
    return _STYLE_CACHE


# ---------------------------------------------------------------------------
# رسم الرأس والتذييل على كل صفحة
# ---------------------------------------------------------------------------
def _draw_header(canvas_obj: Any, doc: Any) -> None:
    w, h = A4
    band_h = 32 * mm
    canvas_obj.saveState()
    # شريط علوي
    canvas_obj.setFillColor(NAVY)
    canvas_obj.rect(0, h - band_h, w, band_h, stroke=0, fill=1)
    canvas_obj.setFillColor(GOLD)
    canvas_obj.rect(0, h - band_h, w, 2.2, stroke=0, fill=1)
    # شعار: مربع دائري الزوايا بحرف "ف"
    logo_size = 17 * mm
    logo_x = w - 16 * mm - logo_size
    logo_y = h - band_h / 2 - logo_size / 2
    canvas_obj.setFillColor(NAVY_LIGHT)
    canvas_obj.roundRect(logo_x, logo_y, logo_size, logo_size, 4, stroke=0, fill=1)
    canvas_obj.setFillColor(GOLD)
    canvas_obj.setFont(_FONT_BOLD, 20)
    canvas_obj.drawCentredString(logo_x + logo_size / 2, logo_y + logo_size / 2 - 7.5, _shape("ف"))
    # العناوين يمين الشعار
    canvas_obj.setFillColor(colors.white)
    canvas_obj.setFont(_FONT_BOLD, 16)
    canvas_obj.drawRightString(w - 16 * mm, h - 13 * mm, _shape("تقرير التقييم العقاري"))
    canvas_obj.setFont(_FONT_NAME, 9)
    canvas_obj.setFillColor(GOLD)
    canvas_obj.drawRightString(w - 16 * mm, h - 21.5 * mm, _shape("مساعد الفريج للبحث والتقييم العقاري — دولة الكويت"))
    canvas_obj.setFont(_FONT_NAME, 8)
    canvas_obj.setFillColor(colors.HexColor("#aab6c4"))
    canvas_obj.drawRightString(w - 16 * mm, h - 28 * mm, _shape(f"تاريخ الإصدار: {datetime.now():%Y-%m-%d %H:%M}"))
    canvas_obj.restoreState()


def _draw_footer(canvas_obj: Any, doc: Any) -> None:
    w, _ = A4
    canvas_obj.saveState()
    canvas_obj.setFont(_FONT_NAME, 7.5)
    canvas_obj.setFillColor(GRAY)
    canvas_obj.drawCentredString(w / 2, 9 * mm, _shape("مساعد الفريج — تقرير تقييم استرشادي وليس تقييمًا رسميًا"))
    canvas_obj.drawRightString(w - 14 * mm, 9 * mm, f"صفحة {doc.page}")
    canvas_obj.restoreState()


def _draw_header_footer(canvas_obj: Any, doc: Any) -> None:
    """رسم الرأس والتذييل معًا للصفحات اللاحقة."""
    _draw_header(canvas_obj, doc)
    _draw_footer(canvas_obj, doc)


# ---------------------------------------------------------------------------
# عناصر مساعدة
# ---------------------------------------------------------------------------
def _heading(story: list, text: str) -> None:
    styles = _styles()
    story.append(Paragraph(ar(text), styles["section"]))
    story.append(HRFlowable(width="100%", thickness=1.1, color=GOLD, spaceBefore=1, spaceAfter=6))


def _info_table(rows: list[tuple[str, str]], widths: list[float]) -> Table:
    styles = _styles()
    data = [[Paragraph(ar(label), styles["box_title"]), Paragraph(ar(value), styles["cell"])] for label, value in rows]
    table = Table(data, colWidths=widths, hAlign="RIGHT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), LIGHT),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    return table


def _bullet_list(story: list, items: list[str]) -> None:
    styles = _styles()
    for item in items:
        line = str(item).strip()
        if not line:
            continue
        # ar() يهرب الوسوم أولًا ثم يشكّل، فيمنع حقن وسوم reportlab من محتوى AI
        story.append(Paragraph(f"• {ar(line)}", styles["body"]))


# ---------------------------------------------------------------------------
# بناء التقرير
# ---------------------------------------------------------------------------
def build_pdf(report: dict | None) -> bytes:
    """يولّد ملف PDF من تقرير البحث (بنية build_report). يعيد البايتات."""
    _register_fonts()
    styles = _styles()
    report = report or {}
    request = report.get("request") or {}
    results = report.get("results") or []
    search_scope = report.get("searchScope") or {}
    summary = report.get("summary") or "لا توجد خلاصة متاحة."
    limitations = report.get("limitations") or []
    ai = report.get("aiInsights") or {}

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=40 * mm,
        bottomMargin=18 * mm,
        title="تقرير التقييم العقاري — مساعد الفريج",
        author="مساعد الفريج",
    )

    story: list = []

    # ---- طلب العميل ----
    _heading(story, "طلب العميل")
    raw_text = request.get("raw_text") or request.get("text") or "—"
    story.append(Paragraph(ar_rich(f"**{raw_text}**"), styles["body"]))
    story.append(Spacer(1, 3))
    request_rows: list[tuple[str, str]] = []
    if request.get("transaction"):
        request_rows.append(("نوع العملية", request["transaction"]))
    if request.get("property_type"):
        request_rows.append(("نوع العقار", request["property_type"]))
    if request.get("areas"):
        request_rows.append(("المناطق", "، ".join(request["areas"])))
    if request.get("min_area") is not None or request.get("max_area") is not None:
        low = f"{request['min_area']:,.0f}" if request.get("min_area") else "—"
        high = f"{request['max_area']:,.0f}" if request.get("max_area") else "—"
        request_rows.append(("المساحة المطلوبة", f"{low} - {high} م²"))
    if request.get("budget"):
        request_rows.append(("ميزانية البيع", money(request["budget"])))
    if request.get("rent_budget"):
        request_rows.append(("ميزانية الإيجار", money(request["rent_budget"])))
    if request.get("bedrooms"):
        request_rows.append(("عدد الغرف", f"{request['bedrooms']}"))
    if request_rows:
        story.append(_info_table(request_rows, [45 * mm, 135 * mm]))
    story.append(Spacer(1, 4))

    # ---- نطاق البحث ----
    if search_scope.get("note"):
        story.append(Paragraph(ar(f"**نطاق البحث:** {search_scope['note']}"), styles["body"]))
        story.append(Spacer(1, 4))

    # ---- الخلاصة التنفيذية ----
    _heading(story, "الخلاصة التنفيذية")
    story.append(Paragraph(ar_rich(summary), styles["body"]))
    story.append(Spacer(1, 4))

    # ---- جدول النتائج المرتبة ----
    _heading(story, "النتائج المرتبة حسب درجة التوصية")
    if not results:
        story.append(Paragraph(ar("لا توجد نتائج كافية حسب الفلاتر الحالية."), styles["body"]))
    else:
        header = [
            Paragraph(ar("#"), styles["cell_head"]),
            Paragraph(ar("الإعلان"), styles["cell_head"]),
            Paragraph(ar("المنطقة"), styles["cell_head"]),
            Paragraph(ar("السعر"), styles["cell_head"]),
            Paragraph(ar("المساحة"), styles["cell_head"]),
            Paragraph(ar("وسيط المقارنات"), styles["cell_head"]),
            Paragraph(ar("التوصية"), styles["cell_head"]),
            Paragraph(ar("الثقة"), styles["cell_head"]),
        ]
        rows = [header]
        for index, item in enumerate(results[:10], start=1):
            area = item.get("area") or "غير محددة"
            price = item.get("priceText") or money(item.get("price"))
            space = f"{item.get('space'):,.0f} م²" if item.get("space") else "—"
            median = money(item.get("marketMedian")) if item.get("marketMedian") else "—"
            rec = f"{round(item.get('recommendationScore') or 0)}/100"
            conf = f"{round((item.get('confidence') or 0) * 100)}%"
            rows.append([
                Paragraph(ar(str(index)), styles["cell"]),
                Paragraph(ar(item.get("code") or "—"), styles["cell"]),
                Paragraph(ar(area), styles["cell"]),
                Paragraph(ar(price), styles["cell"]),
                Paragraph(ar(space), styles["cell"]),
                Paragraph(ar(median), styles["cell"]),
                Paragraph(ar(rec), styles["cell"]),
                Paragraph(ar(conf), styles["cell"]),
            ])
        table = Table(rows, colWidths=[9 * mm, 26 * mm, 26 * mm, 30 * mm, 24 * mm, 30 * mm, 20 * mm, 17 * mm], repeatRows=1, hAlign="RIGHT")
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(KeepTogether(table))
    story.append(Spacer(1, 6))

    # ---- تفاصيل أفضل نتيجة ----
    if results:
        top = results[0]
        _detail_top_result(story, top, styles)

    # ---- توصيات العميل ----
    suggestions = ai.get("suggestions") or ""
    if suggestions:
        _heading(story, "توصيات للعميل")
        _bullet_list(story, re.split(r"[؛\n]", suggestions))
        story.append(Spacer(1, 4))

    missing = ai.get("missing_data") or ""
    if missing:
        _heading(story, "بيانات مقترحة لتأكيد التقييم")
        _bullet_list(story, re.split(r"[؛\n]", missing))
        story.append(Spacer(1, 4))

    # ---- القيود ----
    if limitations:
        _heading(story, "حدود هذا التقرير")
        _bullet_list(story, limitations)

    doc.build(story, onFirstPage=_draw_header, onLaterPages=_draw_header_footer)
    return buf.getvalue()


def _detail_top_result(story: list, item: dict, styles: dict[str, ParagraphStyle]) -> None:
    """قسم التحليل التفصيلي لأفضل نتيجة: المقارنات، التقييم الرسمي، التمويل، ومصدر كل رقم."""
    code = item.get("code") or "—"
    area = item.get("area") or "غير محددة"
    sources = item.get("numberSources") or {}

    _heading(story, f"التفاصيل التحليلية لأفضل نتيجة: {code} — {area}")

    # بطاقة التقييم الأساسية
    verdict = item.get("valuationLabel") or "بدون حكم"
    reason = item.get("valuationReason") or "لا يوجد سبب تقييم كاف."
    rec = round(item.get("recommendationScore") or 0)
    conf = round((item.get("confidence") or 0) * 100)
    summary_rows = [
        ("حكم السعر", verdict),
        ("درجة التوصية", f"{rec} من 100"),
        ("الثقة", f"{conf}%"),
        ("السبب", reason),
    ]
    story.append(_info_table(summary_rows, [40 * mm, 140 * mm]))
    story.append(Spacer(1, 6))

    # جدول المقارنات
    comparables = item.get("comparables") or []
    if comparables:
        header = [
            Paragraph(ar("الكود"), styles["cell_head"]),
            Paragraph(ar("المنطقة"), styles["cell_head"]),
            Paragraph(ar("السعر"), styles["cell_head"]),
            Paragraph(ar("المساحة"), styles["cell_head"]),
            Paragraph(ar("التاريخ"), styles["cell_head"]),
        ]
        rows = [header]
        for comp in comparables[:8]:
            price = comp.get("priceText") or money(comp.get("price"))
            space = f"{comp.get('space'):,.0f} م²" if comp.get("space") else "—"
            rows.append([
                Paragraph(ar(comp.get("code") or "—"), styles["cell"]),
                Paragraph(ar(comp.get("area") or "—"), styles["cell"]),
                Paragraph(ar(price), styles["cell"]),
                Paragraph(ar(space), styles["cell"]),
                Paragraph(ar(comp.get("date") or "—"), styles["cell"]),
            ])
        comp_table = Table(rows, colWidths=[30 * mm, 30 * mm, 40 * mm, 26 * mm, 26 * mm], repeatRows=1, hAlign="RIGHT")
        comp_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), NAVY),
            ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]))
        story.append(Paragraph(ar("المقارنات السعرية الداخلة في التقييم"), styles["box_title"]))
        story.append(Spacer(1, 2))
        story.append(KeepTogether(comp_table))
        story.append(Spacer(1, 6))

    # التقييم الرسمي + سعر المتر
    official = sources.get("officialValue") or {}
    price_per_sqm = sources.get("pricePerSqm") or {}
    median_per_sqm = sources.get("medianPerSqm") or {}
    if official.get("display") or official.get("value"):
        official_rows = [
            ("التقييم الرسمي للمنطقة", official.get("display") or money(official.get("value"))),
            ("سعر المتر المطلوب", price_per_sqm.get("display") or "غير محسوب"),
            ("وسيط سعر المتر", median_per_sqm.get("display") or "غير محسوب"),
            ("أساس التقييم", official.get("source") or "لا توجد بيانات رسمية موثوقة"),
        ]
        story.append(Paragraph(ar("التقييم الرسمي وسعر المتر"), styles["box_title"]))
        story.append(Spacer(1, 2))
        story.append(_info_table(official_rows, [40 * mm, 140 * mm]))
        story.append(Spacer(1, 6))

    # التمويل المتوقع
    financing = item.get("financing") or {}
    if financing.get("monthly_payment"):
        finance_rows = [
            ("الدفعة المقدمة", money(financing.get("down_payment"))),
            ("القسط الشهري المتوقع", money(financing.get("monthly_payment"))),
            ("نسبة الفائدة", f"{financing.get('interest_rate_percent')}%" if financing.get("interest_rate_percent") is not None else "—"),
            ("مدة القرض", f"{financing.get('years')} سنة" if financing.get("years") else "—"),
        ]
        story.append(Paragraph(ar("التمويل العقاري المتوقع"), styles["box_title"]))
        story.append(Spacer(1, 2))
        story.append(_info_table(finance_rows, [40 * mm, 140 * mm]))
        story.append(Spacer(1, 6))

    # مصدر كل رقم (الشفافية)
    source_rows: list[tuple[str, str]] = []
    mapping = [
        ("السعر المطلوب", sources.get("price")),
        ("المساحة", sources.get("space")),
        ("سعر المتر المطلوب", sources.get("pricePerSqm")),
        ("وسيط المقارنات", sources.get("marketMedian")),
        ("وسيط سعر المتر", sources.get("medianPerSqm")),
        ("التقييم الرسمي", sources.get("officialValue")),
        ("نسبة السعر للوسيط", sources.get("priceRatio")),
        ("عدد المقارنات الداخلة", sources.get("comparablesCount")),
        ("الثقة", sources.get("confidence")),
    ]
    for label, entry in mapping:
        if not isinstance(entry, dict):
            continue
        display = entry.get("display")
        if display is None and entry.get("value") is not None:
            if label in ("السعر المطلوب", "وسيط المقارنات", "التقييم الرسمي"):
                display = money(entry["value"])
            elif label == "نسبة السعر للوسيط":
                try:
                    display = f"{round(float(entry['value']) * 100)}%"
                except (TypeError, ValueError):
                    display = str(entry["value"])
            elif label == "المساحة":
                try:
                    display = f"{float(entry['value']):,.0f} م²"
                except (TypeError, ValueError):
                    display = str(entry["value"])
            else:
                display = str(entry["value"])
        if display is None:
            display = "—"
        src = entry.get("source") or ""
        source_rows.append((label, f"{display} — {src}" if src else str(display)))
    if source_rows:
        story.append(Paragraph(ar("مصدر كل رقم وطريقة الحساب (الشفافية)"), styles["box_title"]))
        story.append(Spacer(1, 2))
        story.append(_info_table(source_rows, [45 * mm, 135 * mm]))

    # التحذيرات
    warnings = item.get("warnings") or []
    if warnings:
        story.append(Spacer(1, 4))
        _bullet_list(story, [f"تحذير: {w}" for w in warnings])
