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
    PageBreak,
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

# شعار الشركة: يُستخدم في الشريط العلوي لكل صفحة + غلاف الصفحة الأولى.
# المسار من مجلد المشروع (الموصل للواجهة) — بلا الاعتماد على مجلد العمل الحالي.
_LOGO_PATH = Path(__file__).resolve().parents[2] / "frontend" / "assets" / "alforaij_logo.png"
# الشعار الرمزي المربع (شعار الموقع الفعلي) — أنيق داخل الإطار المربع للشريط العلوي بلا تشويه.
_SYMBOL_PATH = Path(__file__).resolve().parents[2] / "frontend" / "assets" / "alforaij-official-symbol.png"


def _image_size(path: Path) -> tuple[int, int] | None:
    """أبعاد الصورة (عرض، ارتفاع) عبر ImageReader — بلا الاعتماد على PIL."""
    try:
        from reportlab.lib.utils import ImageReader
        width, height = ImageReader(str(path)).getSize()
        return max(1, width), max(1, height)
    except Exception:
        return None


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


# كل الأرقام في PDF بالإنجليزية: تحويل العربية الهندية (٠-٩) وفواصلها عند التضمين.
_PDF_AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")


def _esc(value: Any) -> str:
    text = str(value if value is not None else "").translate(_PDF_AR_DIGITS)
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


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


def ar_link(label: Any, url: str | None) -> str:
    """رابط مباشر قابل للنقر داخل Paragraph: النص مشكّل عربيًا والرابط يبقى كاملًا في href."""
    text = str(label if label is not None else "فتح الإعلان")
    if not url:
        return ar(text)
    return f'<a href="{_esc(url)}" color="#1457a8">{_shape(_esc(text))}</a>'


def _display_url(url: str, max_len: int = 58) -> str:
    """اختصار عنوان طويل من المنتصف للعرض، مع إبقائه كاملًا في الرابط القابل للنقر."""
    if not url or len(url) <= max_len:
        return url
    head = max_len // 2 - 2
    tail = max_len - head - 1
    return f"{url[:head]}…{url[-tail:]}"


_STATUS_LABELS = {
    "success": ("نجح", "#1a7f37"),
    "fallback": ("مصدر بديل", "#b45309"),
    "failed": ("فشل", "#b91c1c"),
    "no_results": ("لا نتائج", "#5a6472"),
    "no_data": ("لا بيانات", "#5a6472"),
    "page_reachable": ("الصفحة متاحة", "#5a6472"),
}


def _source_status_label(status: str) -> str:
    """تسمية عربية ملونة لحالة المصدر داخل Paragraph (تشكيل + لون)."""
    label, color = _STATUS_LABELS.get(status or "", (status or "غير معروف", "#5a6472"))
    return f'<font color="{color}">{_shape(_esc(label))}</font>'


def _source_evidence_table(sources: list[dict], styles: dict[str, ParagraphStyle]) -> Table:
    """جدول المصادر والأدلة: حالة كل مصدر + آلية الجلب + المدة + المحاولات + النتائج + الدليل."""
    header = [
        Paragraph(ar("#"), styles["cell_head"]),
        Paragraph(ar("المصدر"), styles["cell_head"]),
        Paragraph(ar("الحالة"), styles["cell_head"]),
        Paragraph(ar("آلية الجلب"), styles["cell_head"]),
        Paragraph(ar("المدة"), styles["cell_head"]),
        Paragraph(ar("المحاولات"), styles["cell_head"]),
        Paragraph(ar("النتائج"), styles["cell_head"]),
        Paragraph(ar("الدليل / نقطة النهاية"), styles["cell_head"]),
    ]
    rows = [header]
    for index, src in enumerate(sources, start=1):
        name = str(src.get("name") or "مصدر")
        mech = str(src.get("fetchMethod") or "")
        if not mech:
            mech = "بيانات محلية (لوحة الفريج)" if name == "الفريج" else "—"
        ms = src.get("responseMs")
        duration = f"{ms / 1000:.1f} ث" if isinstance(ms, (int, float)) else "—"
        attempts = src.get("attempts")
        attempts_text = f"{attempts}" if attempts is not None else "—"
        records = src.get("records", 0)
        endpoint = str(src.get("endpoint") or src.get("url") or "")
        if endpoint.startswith("http"):
            evidence = Paragraph(ar_link(_display_url(endpoint, max_len=34), endpoint), styles["cell"])
        elif endpoint:
            evidence = Paragraph(ar(endpoint), styles["cell"])
        else:
            evidence = Paragraph(ar("—"), styles["cell"])
        rows.append([
            Paragraph(ar(str(index)), styles["cell"]),
            Paragraph(ar(name), styles["cell"]),
            Paragraph(_source_status_label(str(src.get("status") or "")), styles["cell"]),
            Paragraph(ar(mech), styles["cell"]),
            Paragraph(ar(duration), styles["cell"]),
            Paragraph(ar(attempts_text), styles["cell"]),
            Paragraph(ar(f"{records}"), styles["cell"]),
            evidence,
        ])
    table = Table(
        rows,
        colWidths=[6 * mm, 24 * mm, 24 * mm, 36 * mm, 17 * mm, 20 * mm, 14 * mm, 41 * mm],
        repeatRows=1,
        hAlign="RIGHT",
    )
    table.setStyle(_data_table_style())
    return table


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
            "company": ParagraphStyle("company", fontName=_FONT_BOLD, fontSize=15, leading=20, textColor=NAVY, alignment=TA_CENTER, spaceBefore=4),
            "company_en": ParagraphStyle("company_en", fontName=_FONT_NAME, fontSize=8.5, leading=12, textColor=GRAY, alignment=TA_CENTER),
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
    # شعار الشركة: الشعار الرمزي المربع داخل الإطار الأبيض المربع (أنيق بلا تشويه)،
    # وإن غاب فالشعار الأفقي يُرسم بنسبته الطبيعية داخل إطار عريض، وإلا مربع «ف» كسقوط آمن.
    logo_size = 17 * mm
    logo_x = w - 16 * mm - logo_size
    logo_y = h - band_h / 2 - logo_size / 2
    frame_pad = 2 * mm

    def _fallback_symbol() -> None:
        canvas_obj.setFillColor(NAVY_LIGHT)
        canvas_obj.roundRect(logo_x, logo_y, logo_size, logo_size, 4, stroke=0, fill=1)
        canvas_obj.setFillColor(GOLD)
        canvas_obj.setFont(_FONT_BOLD, 20)
        canvas_obj.drawCentredString(logo_x + logo_size / 2, logo_y + logo_size / 2 - 7.5, _shape("ف"))

    if _SYMBOL_PATH.exists():
        try:
            canvas_obj.setFillColor(colors.white)
            canvas_obj.roundRect(logo_x - 1 * mm, logo_y - 1 * mm, logo_size + 2 * mm, logo_size + 2 * mm, 3, stroke=0, fill=1)
            canvas_obj.drawImage(
                str(_SYMBOL_PATH),
                logo_x + frame_pad,
                logo_y + frame_pad,
                width=logo_size - 2 * frame_pad,
                height=logo_size - 2 * frame_pad,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
        except Exception:
            _fallback_symbol()
    elif _LOGO_PATH.exists():
        # الشعار الأفقي العريض: إطار أبيض عريض بنسبة الصورة الفعلية (لا مربع يضغطه)
        try:
            size = _image_size(_LOGO_PATH)
            ratio = (size[0] / size[1]) if size else 6.0
            logo_w = 30 * mm
            logo_h = min(logo_w / ratio, 9 * mm)
            wide_x = w - 16 * mm - logo_w
            wide_y = h - band_h / 2 - logo_h / 2
            canvas_obj.setFillColor(colors.white)
            canvas_obj.roundRect(wide_x - 1 * mm, wide_y - 1 * mm, logo_w + 2 * mm, logo_h + 2 * mm, 3, stroke=0, fill=1)
            canvas_obj.drawImage(
                str(_LOGO_PATH),
                wide_x + frame_pad,
                wide_y + frame_pad,
                width=logo_w - 2 * frame_pad,
                height=logo_h - 2 * frame_pad,
                preserveAspectRatio=True,
                anchor="c",
                mask="auto",
            )
        except Exception:
            _fallback_symbol()
    else:
        _fallback_symbol()
    # العناوين يمين الشعار
    canvas_obj.setFillColor(colors.white)
    canvas_obj.setFont(_FONT_BOLD, 16)
    title = getattr(doc, "_report_title", None) or "تقرير التقييم العقاري"
    canvas_obj.drawRightString(w - 16 * mm, h - 13 * mm, _shape(title))
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
    # القيمة التي تبدأ بوسم reportlab (<a …>) تُعتبر ترميزًا جاهزًا (مشكّلًا ومهرّبًا) فلا تُمرَّر عبر ar()
    data = [
        [
            Paragraph(ar(label), styles["box_title"]),
            Paragraph(value if (isinstance(value, str) and value.startswith("<")) else ar(value), styles["cell"]),
        ]
        for label, value in rows
    ]
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


def _data_table_style() -> TableStyle:
    """تنسيق موحد لجداول البيانات (رأس داكن + صفوف متناوبة)."""
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ])


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
def build_pdf(report: dict | None, *, title: str | None = None, client_recommendations: list[str] | None = None) -> bytes:
    """يولّد ملف PDF من تقرير البحث (بنية build_report). يعيد البايتات.

    - title: عنوان عربي مخصص يظهر في رأس كل صفحة بدل العنوان الافتراضي.
    - client_recommendations: قائمة توصيات للعميل تُعرض في صفحة مخصصة في نهاية التقرير.
    """
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
        title=title or "تقرير التقييم العقاري — مساعد الفريج",
        author="مساعد الفريج",
    )
    doc._report_title = title

    story: list = []

    # ---- غلاف الشركة (الصفحة الأولى فقط): شعار + اسم الشركة ----
    if _LOGO_PATH.exists():
        try:
            from reportlab.platypus import Image as FlowImage

            logo_w = 52 * mm
            logo_h = 22 * mm
            letterhead = FlowImage(str(_LOGO_PATH), width=logo_w, height=logo_h, hAlign="CENTER")
            letterhead.preserveAspectRatio = True
            story.append(Spacer(1, 2))
            story.append(letterhead)
        except Exception:
            pass
    story.append(Paragraph(ar("شركة عبدالعزيز سعود الفريج العقارية"), styles["company"]))
    story.append(Paragraph(ar("ABDUL AZIZ SAUD AL-FURAIJ REAL ESTATE COMPANY — KUWAIT"), styles["company_en"]))
    story.append(Spacer(1, 2))
    story.append(HRFlowable(width="100%", thickness=1.2, color=GOLD, spaceBefore=2, spaceAfter=8))

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
            Paragraph(ar("الرابط"), styles["cell_head"]),
        ]
        rows = [header]
        for index, item in enumerate(results[:10], start=1):
            area = item.get("area") or "غير محددة"
            price = item.get("priceText") or money(item.get("price"))
            space = f"{item.get('space'):,.0f} م²" if item.get("space") else "—"
            median = money(item.get("marketMedian")) if item.get("marketMedian") else "—"
            rec = f"{round(item.get('recommendationScore') or 0)}/100"
            conf = f"{round((item.get('confidence') or 0) * 100)}%"
            url = item.get("originalUrl") or ""
            link_cell = Paragraph(ar_link("فتح الإعلان", url), styles["cell"]) if url else Paragraph(ar("—"), styles["cell"])
            rows.append([
                Paragraph(ar(str(index)), styles["cell"]),
                Paragraph(ar(item.get("code") or "—"), styles["cell"]),
                Paragraph(ar(area), styles["cell"]),
                Paragraph(ar(price), styles["cell"]),
                Paragraph(ar(space), styles["cell"]),
                Paragraph(ar(median), styles["cell"]),
                Paragraph(ar(rec), styles["cell"]),
                Paragraph(ar(conf), styles["cell"]),
                link_cell,
            ])
        table = Table(rows, colWidths=[8 * mm, 22 * mm, 24 * mm, 26 * mm, 19 * mm, 28 * mm, 16 * mm, 12 * mm, 27 * mm], repeatRows=1, hAlign="RIGHT")
        table.setStyle(_data_table_style())
        story.append(KeepTogether(table))
    story.append(Spacer(1, 6))

    # ---- تفاصيل أفضل نتيجة ----
    if results:
        top = results[0]
        _detail_top_result(story, top, styles)
        # ---- مقارنة التمويل العقاري ----
        if not top.get("rental"):
            _mortgage_comparison_section(story, top, styles)
        # ---- مؤشر ثقة الإعلان التفصيلي ----
        _trust_score_section(story, top, styles)
        # ---- عوامل التقييم المفصلة ----
        _explanation_factors_section(story, top, styles)
        # ---- تقدير التأمين العقاري ----
        _insurance_section(story, top, styles)

    # ---- مؤشر الطلب: من يبحث عن شراء/إيجار في نفس المنطقة (صفحة مخصصة بجانب ملخص التقييم) ----
    demand = report.get("demandIndicators") or {}
    if demand.get("count"):
        story.append(PageBreak())
        _heading(story, "مؤشر الطلب — من يبحث في نفس المنطقة")
        scope = str(demand.get("scope") or "كل الكويت")
        story.append(
            Paragraph(
                ar_rich(
                    f"طلبات «مطلوب للشراء/للإيجار» المنافسة ضمن نطاق **{scope}** — بجانب ملخص التقييم أعلاه، "
                    "لترى من يبحث في نفس المنطقة التي قُيّم فيها العقار."
                ),
                styles["body"],
            )
        )
        story.append(Spacer(1, 4))
        story.append(
            _info_table(
                [
                    ("نطاق الطلب", scope),
                    ("إجمالي الطلبات المنافسة", f"{demand.get('count') or 0}"),
                    ("طلبات شراء", f"{demand.get('buyRequests') or 0}"),
                    ("طلبات إيجار", f"{demand.get('rentRequests') or 0}"),
                ],
                [60 * mm, 120 * mm],
            )
        )
        story.append(Spacer(1, 6))
        items = demand.get("items") or []
        if items:
            header = [
                Paragraph(ar("#"), styles["cell_head"]),
                Paragraph(ar("الكود"), styles["cell_head"]),
                Paragraph(ar("نوع الطلب"), styles["cell_head"]),
                Paragraph(ar("المنطقة"), styles["cell_head"]),
                Paragraph(ar("المحافظة"), styles["cell_head"]),
                Paragraph(ar("نوع العقار"), styles["cell_head"]),
                Paragraph(ar("تاريخ النشر"), styles["cell_head"]),
            ]
            rows = [header]
            for index, item in enumerate(items, start=1):
                published = str(item.get("publishedDate") or "—")[:10]
                rows.append(
                    [
                        Paragraph(ar(str(index)), styles["cell"]),
                        Paragraph(ar(item.get("code") or "—"), styles["cell"]),
                        Paragraph(ar(item.get("transaction") or "—"), styles["cell"]),
                        Paragraph(ar(item.get("area") or "—"), styles["cell"]),
                        Paragraph(ar(item.get("governorate") or "—"), styles["cell"]),
                        Paragraph(ar(item.get("propertyType") or "—"), styles["cell"]),
                        Paragraph(ar(published), styles["cell"]),
                    ]
                )
            table = Table(
                rows,
                colWidths=[8 * mm, 22 * mm, 34 * mm, 26 * mm, 24 * mm, 30 * mm, 36 * mm],
                repeatRows=1,
                hAlign="RIGHT",
            )
            table.setStyle(_data_table_style())
            story.append(KeepTogether(table))
            story.append(Spacer(1, 5))
            for item in items:
                summary_text = str(item.get("summary") or "").strip()
                if summary_text:
                    story.append(Paragraph(ar(f"• {item.get('code') or 'طلب'}: {summary_text[:120]}"), styles["small"]))
                    story.append(Spacer(1, 1))
        story.append(Spacer(1, 4))

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

    # ---- التأكيد النهائي: الفرق بين الإيجار والبيع والشراء (في نهاية التقرير) ----
    tsum = report.get("transactionSummary") or {}
    if tsum:
        _heading(story, "تأكيد الفرق في الحسابات (الإيجار / البيع / الشراء)")
        bd = tsum.get("breakdown") or {}
        sale = bd.get("sale") or {}
        rent = bd.get("rent") or {}
        _bullet_list(story, [
            f"نوع العملية المكتشف: {tsum.get('detected') or 'غير محدد'}.",
            f"متى يُكتشف: {tsum.get('detectedWhen') or '—'}.",
            f"طريقة الحساب المطبقة: {tsum.get('calculation') or '—'}.",
            f"بيع/شراء ({sale.get('count') or 0} نتيجة): {sale.get('method') or '—'}.",
            f"إيجار ({rent.get('count') or 0} نتيجة): {rent.get('method') or '—'}.",
            f"التأكيد: {tsum.get('confirmation') or '—'}.",
        ])
        story.append(Spacer(1, 4))

    # ---- القيود ----
    if limitations:
        _heading(story, "حدود هذا التقرير")
        _bullet_list(story, limitations)

    # ---- المصادر والأدلة (في نهاية التقرير لتوثيق التسليم) ----
    sources = report.get("sourceStatus") or []
    if sources:
        _heading(story, "المصادر والأدلة")
        ok_count = sum(1 for s in sources if s.get("status") == "success")
        story.append(
            Paragraph(
                ar(f"تشغيل هذا التقرير: {ok_count} مصدرًا ناجحًا من أصل {len(sources)} — كل رقم قابل للتتبع إلى نقطة الجلب والوقت أدناه."),
                styles["body"],
            )
        )
        story.append(Spacer(1, 3))
        story.append(_source_evidence_table(sources, styles))
        story.append(Spacer(1, 3))
        story.append(
            Paragraph(
                ar("الحالة: نجح = جلب فعلي · مصدر بديل = البديل استُخدم بدل منصة تعذر الوصول إليها · لا نتائج/لا بيانات = اكتمل الفحص دون مطابقة · فشل = تعذر الوصول نهائيًا."),
                styles["small"],
            )
        )

    # ---- توصيات العميل (صفحة مخصصة في نهاية التقرير) ----
    if client_recommendations:
        story.append(PageBreak())
        _heading(story, "توصيات العميل — خطة التنفيذ")
        raw_text = request.get("raw_text") or request.get("text") or ""
        if raw_text:
            story.append(Paragraph(ar_rich(f"**طلب العميل:** {raw_text}"), styles["body"]))
            story.append(Spacer(1, 4))
        for index, rec in enumerate(client_recommendations, start=1):
            story.append(Paragraph(f"{index}. {ar(rec)}", styles["body"]))
            story.append(Spacer(1, 2))
        story.append(Spacer(1, 6))

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

    # نطاق الثقة (Confidence Interval)
    ci = item.get("confidenceInterval") or {}
    if ci.get("display"):
        summary_rows.append(("نطاق الثقة", ci["display"]))
    elif ci.get("low") is not None and ci.get("high") is not None:
        summary_rows.append(("نطاق الثقة", f"{ci['low']:,.0f} – {ci['high']:,.0f} د.ك"))

    # مؤشر ثقة الإعلان (Trust Score)
    ts = item.get("trustScore") or {}
    if ts.get("score") is not None:
        ts_score = ts["score"]
        ts_label = ts.get("label") or "متوسط"
        ts_color = ts.get("color") or "#f59e0b"
        summary_rows.append(("ثقة الإعلان", f"{ts_score}/100 — {ts_label}"))
    url = item.get("originalUrl") or ""
    if url:
        summary_rows.append((
            "رابط الإعلان المباشر",
            f"{ar_link('اضغط هنا لفتح الإعلان الأصلي', url)}<br/>{ar(_display_url(url))}",
        ))
    phone = item.get("phone") or ""
    if phone:
        phone_digits = re.sub(r"\D", "", phone)
        summary_rows.append((
            "هاتف المعلن (واتساب)",
            f"{ar_link('اضغط هنا للتواصل عبر واتساب', f'https://wa.me/{phone_digits}')}<br/>{ar(phone)}",
        ))
    # العائد الإيجاري السنوي لعروض البيع المؤجرة («مؤجر ب 1200 شهرياً»)
    sale_yield = item.get("rentalYieldPercent")
    if sale_yield is not None and not item.get("rental"):
        annual = item.get("annualRent")
        verdict = item.get("rentalYieldVerdict") or ""
        price_value = item.get("price") or 0
        yield_text = f"{ar(sale_yield)}% سنويًا"
        if annual:
            yield_text += f" — إيجار سنوي {ar(f'{annual:,.0f}')} د.ك مقابل سعر {ar(f'{price_value:,.0f}')} د.ك"
        if verdict:
            yield_text += f" — حكم استثماري: {ar(verdict)}"
        summary_rows.append(("العائد الإيجاري السنوي", yield_text))
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
            Paragraph(ar("الرابط"), styles["cell_head"]),
        ]
        rows = [header]
        for comp in comparables[:8]:
            price = comp.get("priceText") or money(comp.get("price"))
            space = f"{comp.get('space'):,.0f} م²" if comp.get("space") else "—"
            comp_url = comp.get("url") or ""
            link_cell = Paragraph(ar_link("فتح الإعلان", comp_url), styles["cell"]) if comp_url else Paragraph(ar("—"), styles["cell"])
            rows.append([
                Paragraph(ar(comp.get("code") or "—"), styles["cell"]),
                Paragraph(ar(comp.get("area") or "—"), styles["cell"]),
                Paragraph(ar(price), styles["cell"]),
                Paragraph(ar(space), styles["cell"]),
                Paragraph(ar(comp.get("date") or "—"), styles["cell"]),
                link_cell,
            ])
        comp_table = Table(rows, colWidths=[24 * mm, 28 * mm, 34 * mm, 24 * mm, 24 * mm, 28 * mm], repeatRows=1, hAlign="RIGHT")
        comp_table.setStyle(_data_table_style())
        story.append(Paragraph(ar("المقارنات السعرية الداخلة في التقييم"), styles["box_title"]))
        story.append(Spacer(1, 2))
        story.append(KeepTogether(comp_table))
        story.append(Spacer(1, 6))

    # التقييم الرسمي + سعر المتر (تسميات تختلف بين الإيجار والبيع: قيمة العقار مقابل إيجار المتر)
    official = sources.get("officialValue") or {}
    price_per_sqm = sources.get("pricePerSqm") or {}
    median_per_sqm = sources.get("medianPerSqm") or {}
    if official.get("display") or official.get("value"):
        if item.get("rental"):
            official_rows = [
                ("قيمة العقار التقديرية (أساس العائد)", official.get("display") or money(official.get("value"))),
                ("إيجار المتر (شهريًا)", price_per_sqm.get("display") or "غير محسوب"),
                ("وسيط إيجار المتر (شهريًا)", median_per_sqm.get("display") or "غير محسوب"),
                ("أساس القيمة", official.get("source") or "لا توجد بيانات رسمية موثوقة"),
            ]
            story.append(Paragraph(ar("قيمة العقار التقديرية وإيجار المتر (الإيجار)"), styles["box_title"]))
        else:
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

    # التمويل المتوقع (للبيع/الشراء فقط) — الإيجار له خط حساب مميز (شهري/سنوي/عائد)
    financing = item.get("financing") or {}
    if item.get("rental"):
        rent_rows = [
            ("الإيجار الشهري", money(item.get("monthlyRent")) if item.get("monthlyRent") is not None else "غير معلن"),
            ("الإيجار السنوي", money(item.get("annualRent")) if item.get("annualRent") is not None else "غير محسوب"),
            ("وسيط إيجارات المنطقة (شهري)", money(item.get("marketMedian")) if item.get("marketMedian") else "غير متوفر"),
            ("العائد الإيجاري السنوي", f"{item.get('rentalYieldPercent')}%" if item.get("rentalYieldPercent") is not None else "غير محسوب"),
            ("ملاحظة", "الإيجار شهري ولا يُموَّل بتمويل عقاري؛ العائد = الإيجار السنوي ÷ قيمة العقار التقديرية"),
        ]
        story.append(Paragraph(ar("تحليل عروض الإيجار (خط حساب مميز عن البيع)"), styles["box_title"]))
        story.append(Spacer(1, 2))
        story.append(_info_table(rent_rows, [45 * mm, 135 * mm]))
        story.append(Spacer(1, 6))
    elif financing.get("monthly_payment"):
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
    if item.get("rental"):
        mapping = [
            ("الإيجار الشهري", sources.get("price")),
            ("الإيجار السنوي", sources.get("annualRent")),
            ("المساحة", sources.get("space")),
            ("إيجار المتر (شهريًا)", sources.get("pricePerSqm")),
            ("وسيط إيجارات المنطقة", sources.get("marketMedian")),
            ("وسيط إيجار المتر", sources.get("medianPerSqm")),
            ("قيمة العقار التقديرية", sources.get("officialValue")),
            ("العائد الإيجاري السنوي", sources.get("rentalYield")),
            ("نسبة الإيجار للوسيط", sources.get("priceRatio")),
            ("عدد المقارنات الداخلة", sources.get("comparablesCount")),
            ("الثقة", sources.get("confidence")),
        ]
    else:
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


def _mortgage_comparison_section(story: list, top_item: dict, styles: dict[str, ParagraphStyle]) -> None:
    """قسم مقارنة التمويل العقاري بين بنوك الكويت."""
    price = top_item.get("price")
    if not price or price <= 0:
        return
    try:
        from backend.services.mortgage_calculator import compare_banks, KUWAIT_BANKS
        result = compare_banks(price, 30, 20)  # 30% down, 20 years
        if not result or "banks" not in result:
            return
        story.append(PageBreak())
        _heading(story, "مقارنة التمويل العقاري — بنوك الكويت")
        story.append(Paragraph(
            ar(f"مقارنة أقساط وأسعار فائدة 4 بنوك كويتية لتمويل العقار بقيمة {money(price)} د.ك (30% دفعة مقدمة، 20 سنة)"),
            styles["body"]
        ))
        story.append(Spacer(1, 4))
        # جدول المقارنة
        header = [
            Paragraph(ar("البنك"), styles["cell_head"]),
            Paragraph(ar("الفائدة"), styles["cell_head"]),
            Paragraph(ar("القسط الشهري"), styles["cell_head"]),
            Paragraph(ar("إجمالي الفائدة"), styles["cell_head"]),
            Paragraph(ar("الإجمالي المدفوع"), styles["cell_head"]),
            Paragraph(ar("المدة"), styles["cell_head"]),
        ]
        rows = [header]
        best_code = result.get("best_bank")
        for bank in result.get("banks", []):
            is_best = bank.get("code") == best_code
            prefix = "🏆 " if is_best else ""
            rows.append([
                Paragraph(ar(f"{prefix}{bank.get('name', '')}"), styles["cell"]),
                Paragraph(ar(f"{bank.get('rate', 0)}%"), styles["cell"]),
                Paragraph(ar(money(bank.get("monthly_payment", 0))), styles["cell"]),
                Paragraph(ar(money(bank.get("total_interest", 0))), styles["cell"]),
                Paragraph(ar(money(bank.get("total_paid", 0))), styles["cell"]),
                Paragraph(ar(f"{bank.get('years', 0)} سنة"), styles["cell"]),
            ])
        table = Table(rows, colWidths=[38 * mm, 20 * mm, 28 * mm, 32 * mm, 32 * mm, 22 * mm], repeatRows=1, hAlign="RIGHT")
        table.setStyle(_data_table_style())
        story.append(KeepTogether(table))
        story.append(Spacer(1, 6))
        # التوصية
        rec = result.get("recommendation", {})
        if rec.get("summary"):
            story.append(Paragraph(ar(f"**التوصية:** {rec['summary']}"), styles["body"]))
            story.append(Spacer(1, 4))
        # ملاحظة
        story.append(Paragraph(
            ar("ملاحظة: الفوائد تقريبية وتتغير حسب العميل والتأمين. يُنصح بزيادة الدفعة المقدمة إذا تجاوز القسط 40% من الراتب."),
            styles["small"]
        ))
    except Exception:
        pass


def _trust_score_section(story: list, item: dict, styles: dict[str, ParagraphStyle]) -> None:
    """قسم مؤشر ثقة الإعلان التفصيلي مع العوامل والتنبيهات."""
    ts = item.get("trustScore") or {}
    score = ts.get("score")
    if score is None:
        return
    story.append(PageBreak())
    _heading(story, "مؤشر ثقة الإعلان (Trust Score)")
    grade = ts.get("grade") or "moderate"
    label = ts.get("label") or "متوسط"
    score_rows = [
        ("الدرجة", f"{score} من 100"),
        ("التقييم", label),
        ("المستوى", grade),
    ]
    if ts.get("color"):
        color_name = {
            "#22c55e": "موثق (أخضر)",
            "#f59e0b": "متوسط (أصفر)",
            "#ef4444": "مشبوه (أحمر)",
        }.get(ts["color"], ts["color"])
        score_rows.append(("اللون", color_name))
    story.append(_info_table(score_rows, [40 * mm, 140 * mm]))
    story.append(Spacer(1, 6))

    # عوامل الثقة
    factors = ts.get("factors") or []
    if factors:
        story.append(Paragraph(ar("عوامل التقييم:"), styles["box_title"]))
        story.append(Spacer(1, 2))
        header = [
            Paragraph(ar("العامل"), styles["cell_head"]),
            Paragraph(ar("الوزن"), styles["cell_head"]),
            Paragraph(ar("النتيجة"), styles["cell_head"]),
            Paragraph(ar("الشرح"), styles["cell_head"]),
        ]
        rows = [header]
        for f in factors:
            rows.append([
                Paragraph(ar(f.get("name") or "—"), styles["cell"]),
                Paragraph(ar(str(f.get("weight") or "—")), styles["cell"]),
                Paragraph(ar(str(f.get("value") or "—")), styles["cell"]),
                Paragraph(ar(f.get("reason") or "—"), styles["cell"]),
            ])
        table = Table(rows, colWidths=[38 * mm, 18 * mm, 28 * mm, 96 * mm], repeatRows=1, hAlign="RIGHT")
        table.setStyle(_data_table_style())
        story.append(KeepTogether(table))
        story.append(Spacer(1, 6))

    # تنبيهات الثقة
    alerts = ts.get("alerts") or []
    if alerts:
        story.append(Paragraph(ar("تنبيهات:"), styles["box_title"]))
        story.append(Spacer(1, 2))
        for alert in alerts:
            icon = alert.get("icon") or "⚠️"
            text = alert.get("text") or alert.get("message") or "—"
            story.append(Paragraph(ar(f"{icon} {text}"), styles["body"]))
            story.append(Spacer(1, 1))


def _explanation_factors_section(story: list, item: dict, styles: dict[str, ParagraphStyle]) -> None:
    """قسم عوامل التقييم المفصلة (Explanation Factors)."""
    factors = item.get("explanationFactors") or []
    if not factors:
        return
    story.append(PageBreak())
    _heading(story, "عوامل التقييم المفصلة")
    story.append(Paragraph(
        ar("العوامل التي أثرت على تقييم هذا العقار — كل عامل مع درجته ونسبة تأثيره."),
        styles["body"]
    ))
    story.append(Spacer(1, 4))
    header = [
        Paragraph(ar("#"), styles["cell_head"]),
        Paragraph(ar("العامل"), styles["cell_head"]),
        Paragraph(ar("النوع"), styles["cell_head"]),
        Paragraph(ar("التفاصيل"), styles["cell_head"]),
    ]
    rows = [header]
    for index, f in enumerate(factors, start=1):
        icon = f.get("icon") or ""
        label = f.get("label") or f.get("text") or "—"
        ftype = f.get("type") or "info"
        detail = f.get("detail") or f.get("value") or "—"
        type_label = {"positive": "إيجابي", "negative": "سلبي", "neutral": "محايد", "info": "معلومات"}.get(ftype, ftype)
        rows.append([
            Paragraph(ar(str(index)), styles["cell"]),
            Paragraph(ar(f"{icon} {label}"), styles["cell"]),
            Paragraph(ar(type_label), styles["cell"]),
            Paragraph(ar(str(detail)), styles["cell"]),
        ])
    table = Table(rows, colWidths=[10 * mm, 50 * mm, 24 * mm, 96 * mm], repeatRows=1, hAlign="RIGHT")
    table.setStyle(_data_table_style())
    story.append(KeepTogether(table))


def _insurance_section(story: list, item: dict, styles: dict[str, ParagraphStyle]) -> None:
    """قسم تقدير التأمين العقاري."""
    price = item.get("price")
    if not price or price <= 0:
        return
    try:
        from backend.services.insurance_calculator import calculate_insurance
        result = calculate_insurance(price, contents_value=50000, building_age=5, years=1)
        if not result:
            return
        story.append(PageBreak())
        _heading(story, "تقدير التأمين العقاري")
        story.append(Paragraph(
            ar(f"تقدير تكاليف التأمين للعقار بقيمة {money(price)} د.ك (عمر البناء 5 سنوات، محتويات 50,000 د.ك)"),
            styles["body"]
        ))
        story.append(Spacer(1, 4))
        header = [
            Paragraph(ar("نوع التأمين"), styles["cell_head"]),
            Paragraph(ar("القسط السنوي"), styles["cell_head"]),
            Paragraph(ar("القسط الشهري"), styles["cell_head"]),
            Paragraph(ar("الوصف"), styles["cell_head"]),
        ]
        rows = [header]
        for ins in result.get("types", []):
            rows.append([
                Paragraph(ar(ins.get("name") or "—"), styles["cell"]),
                Paragraph(ar(money(ins.get("annual", 0))), styles["cell"]),
                Paragraph(ar(money(ins.get("monthly", 0))), styles["cell"]),
                Paragraph(ar(ins.get("description") or "—"), styles["cell"]),
            ])
        table = Table(rows, colWidths=[40 * mm, 28 * mm, 28 * mm, 84 * mm], repeatRows=1, hAlign="RIGHT")
        table.setStyle(_data_table_style())
        story.append(KeepTogether(table))
        story.append(Spacer(1, 6))
        # الخصومات
        discounts = result.get("discounts") or []
        if discounts:
            story.append(Paragraph(ar("الخصومات المتاحة:"), styles["box_title"]))
            story.append(Spacer(1, 2))
            for d in discounts:
                story.append(Paragraph(ar(f"• {d.get('name') or ''}: خصم {d.get('percent', 0)}%"), styles["body"]))
                story.append(Spacer(1, 1))
        # ملاحظة
        story.append(Spacer(1, 4))
        story.append(Paragraph(
            ar("ملاحظة: التقدير تقريبي. التأمين الفعلي يعتمد على الموقع والتشطيب وسقف البناء."),
            styles["small"]
        ))
    except Exception:
        pass
