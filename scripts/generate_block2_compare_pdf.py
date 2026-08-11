"""صفحة مقارنة سريعة من صفحة واحدة لبيت 300م في قطعة 2 الصليبيخات.

القديم (220-260 ألف) مقابل المجدد (350 ألف) — للمدير.

    python scripts/generate_block2_compare_pdf.py

يولّد في reports/: مقارنة-بيت-300م-قطعة2.pdf
"""
import io
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    HRFlowable,
    Image as FlowImage,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.services.pdf_report import (
    _LOGO_PATH,
    _register_fonts,
    _FONT_NAME,
    _FONT_BOLD,
    ar,
    ar_rich,
    NAVY,
    GOLD,
    LIGHT,
    GRAY,
    BORDER,
)

GREEN = colors.HexColor("#1e7d4f")
RED = colors.HexColor("#b3392b")


def _style(name: str, **kw) -> ParagraphStyle:
    base = dict(fontName=_FONT_NAME, fontSize=9.5, leading=14, textColor=colors.HexColor("#232a33"), alignment=TA_RIGHT)
    base.update(kw)
    return ParagraphStyle(name, **base)


def main() -> None:
    _register_fonts()
    styles = {
        "company": _style("c1", fontName=_FONT_BOLD, fontSize=15, leading=20, textColor=NAVY, alignment=TA_CENTER),
        "company_en": _style("c2", fontSize=8, leading=11, textColor=GRAY, alignment=TA_CENTER),
        "title": _style("t1", fontName=_FONT_BOLD, fontSize=13, leading=17, textColor=NAVY, alignment=TA_CENTER, spaceBefore=2),
        "sub": _style("t2", fontSize=9, leading=13, textColor=GRAY, alignment=TA_CENTER),
        "body": _style("b1", fontSize=9.5, leading=15),
        "note": _style("n1", fontSize=8, leading=12, textColor=GRAY),
        "cell": _style("cl", fontSize=9, leading=13, alignment=TA_RIGHT),
        "cell_head": _style("ch", fontName=_FONT_BOLD, fontSize=9.5, leading=13, textColor=colors.white, alignment=TA_CENTER),
        "good": _style("g1", fontName=_FONT_BOLD, fontSize=10.5, leading=15, textColor=GREEN, alignment=TA_CENTER),
        "bad": _style("bd", fontName=_FONT_BOLD, fontSize=10.5, leading=15, textColor=RED, alignment=TA_CENTER),
        "big": _style("bg", fontName=_FONT_BOLD, fontSize=12, leading=16, alignment=TA_CENTER),
    }

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        rightMargin=14 * mm,
        leftMargin=14 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
        title="مقارنة سريعة — بيت 300م قطعة 2 الصليبيخات",
        author="مساعد الفريج",
    )
    story: list = []

    # ---- الترويسة: شعار + اسم الشركة ----
    if _LOGO_PATH.exists():
        logo = FlowImage(str(_LOGO_PATH), width=46 * mm, height=20 * mm, hAlign="CENTER")
        logo.preserveAspectRatio = True
        story.append(logo)
    story.append(Paragraph(ar("شركة عبدالعزيز سعود الفريج العقارية"), styles["company"]))
    story.append(Paragraph(ar("ABDUL AZIZ SAUD AL-FURAIJ REAL ESTATE COMPANY — KUWAIT"), styles["company_en"]))
    story.append(Spacer(1, 3))
    story.append(HRFlowable(width="100%", thickness=1.2, color=GOLD, spaceAfter=6))

    # ---- العنوان ----
    story.append(Paragraph(ar("مقارنة سريعة — بيت 300 م² · قطعة 2 · الصليبيخات"), styles["title"]))
    story.append(Paragraph(ar("القديم (يحتاج ترميم) مقابل المجدّد — مرجع سريع لاتخاذ القرار · استرشادي وليس تقييمًا رسميًا"), styles["sub"]))
    story.append(Spacer(1, 8))

    # ---- جدول المقارنة ----
    head = [Paragraph(ar("وجه المقارنة"), styles["cell_head"]), Paragraph(ar("البيت القديم"), styles["cell_head"]), Paragraph(ar("البيت المجدّد"), styles["cell_head"])]
    rows = [
        [ar("النطاق السعري (300 م²)"), Paragraph(ar_rich("**220,000 – 260,000 د.ك**"), styles["cell"]), Paragraph(ar_rich("**≈ 350,000 د.ك**"), styles["cell"])],
        [ar("سعر المتر"), Paragraph(ar("733 – 867 د.ك/م²"), styles["cell"]), Paragraph(ar("≈ 1,167 د.ك/م²"), styles["cell"])],
        [ar("حالة البناء"), Paragraph(ar("قديم — يحتاج ترميم/إعادة تأهيل"), styles["cell"]), Paragraph(ar("جاهز للسكن فورًا"), styles["cell"])],
        [ar("الفرق السعري"), Paragraph(ar("—"), styles["cell"]), Paragraph(ar("أغلى بـ 90,000 – 130,000 د.ك (+35% – 55%)"), styles["cell"])],
        [ar("تكلفة الترميم المتوقعة"), Paragraph(ar("تُخصم من السعر (هدم جزئي/كامل أو تجديد)"), styles["cell"]), Paragraph(ar("لا تكلفة إضافية متوقعة"), styles["cell"])],
        [ar("مناسب لـ"), Paragraph(ar("مشتري يبحث عن سعر منخفض وقادر على الترميم"), styles["cell"]), Paragraph(ar("مشتري يريد بيتًا جاهزًا بلا تعب"), styles["cell"])],
    ]
    table = Table([head] + rows, colWidths=[52 * mm, 66 * mm, 66 * mm], hAlign="CENTER")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, LIGHT]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(table)
    story.append(Spacer(1, 10))

    # ---- ملخص المقارنة ----
    story.append(Paragraph(ar("القراءة السريعة"), _style("s1", fontName=_FONT_BOLD, fontSize=11, leading=15, textColor=NAVY)))
    story.append(HRFlowable(width="100%", thickness=0.8, color=GOLD, spaceBefore=1, spaceAfter=5))
    story.append(Paragraph(
        ar_rich("• الفرق بين القديم والمجدّد في قطعة 2 يقارب **90-130 ألف د.ك** — أي أن تكلفة الترميم الحقيقية هي المعيار الفاصل: لو أصلح القديم بأقل من 90 ألفًا فهو الصفقة الأفضل.\n"
           "• البيت المعني (قديم · 300 م · ملاصق للمسجد · شارع واحد) مطلوب بـ **160-180 ألف** — أي **أقل حتى من وسيط القديم** (220-260 ألف) بفارق 40-100 ألف، وهذا يجعله فرصة سعرية قوية إذا كان قابلاً للترميم دون هدم كامل.\n"
           "• المطلوب 160 ألف ≈ **533 د.ك/م²** — أُسفل سعر المتر في المنطقة بأكملها."),
        styles["body"]))
    story.append(Spacer(1, 8))

    # ---- خلاصة للمدير ----
    summary = Table(
        [[Paragraph(ar("الخلاصة"), styles["cell_head"]), Paragraph(ar("القديم 220-260 ألف جيد للمرمّم؛ المجدّد 350 ألف للمستعجل؛ والبيت المعني 160-180 ألف فرصة ممتازة لو تأكّدت الوثيقة وإمكانية الترميم."), styles["cell"])]],
        colWidths=[30 * mm, 154 * mm], hAlign="CENTER",
    )
    summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), GOLD),
        ("GRID", (0, 0), (-1, -1), 0.5, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
    ]))
    story.append(summary)
    story.append(Spacer(1, 10))

    story.append(Paragraph(
        ar("المصادر: إعلانات السوق الحيـة للصليبيخات قطعة 2 (q8aqar / drwazaq8 / bu3qar) + تقييم مساعد الفريج مع المؤشر الرسمي (600 د.ك/م²). الأرقام استرشادية مبنية على العروض المتاحة وقت الإعداد."),
        styles["note"]))

    doc.build(story)
    out_dir = os.path.join(os.path.dirname(__file__), "..", "reports")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, "مقارنة-بيت-300م-قطعة2.pdf")
    try:
        with open(out_path, "wb") as f:
            f.write(buf.getvalue())
    except PermissionError:
        alt = os.path.join(out_dir, "مقارنة-بيت-300م-قطعة2-جديد.pdf")
        with open(alt, "wb") as f:
            f.write(buf.getvalue())
        out_path = alt
        print("الملف مقفول — حُفظ بالاسم البديل بدلًا منه", flush=True)
    print(f"PDF saved: {out_path} ({os.path.getsize(out_path)} bytes)", flush=True)


if __name__ == "__main__":
    main()
