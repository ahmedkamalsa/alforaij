from __future__ import annotations

import unittest


class TestPdfReport(unittest.TestCase):
    """اختبارات مولّد تقارير PDF العربية."""

    def _sample_report(self) -> dict:
        return {
            "request": {
                "raw_text": "بيع بيت في النهضة 400م جديد",
                "transaction": "بيع",
                "property_type": "بيت",
                "areas": ["النهضة"],
                "budget": 450000,
            },
            "searchScope": {"areas": ["النهضة"], "note": "تم حصر البحث والتقييم في المناطق المطلوبة فقط: النهضة"},
            "aiInsights": {
                "suggestions": "التحقق من الصفقات الرسمية الأحدث؛ معاينة العقار فعليًا؛ التفاوض على السعر",
                "missing_data": "صفقات وزارة العدل الرسمية؛ سعر المتر الرسمي",
            },
            "summary": "أفضل نتيجة مبدئية هي AF-307 في النهضة بسعر 350 ألف د.ك، وحكم السعر: سعر عادل.",
            "limitations": ["التقييم استرشادي وليس تقييمًا رسميًا."],
            "results": [
                {
                    "code": "AF-307",
                    "area": "النهضة",
                    "price": 350000,
                    "priceText": "350 ألف د.ك",
                    "space": 400,
                    "marketMedian": 355000,
                    "recommendationScore": 56,
                    "confidence": 0.45,
                    "valuationLabel": "تقييم استرشادي ببيانات محدودة",
                    "valuationReason": "يوجد 2 مقارنة سعرية فقط في النهضة.",
                    "originalUrl": "https://front.alforaij.com/Listing/Detail/278",
                    "comparables": [
                        {"code": "AF-310", "area": "النهضة", "price": 360000, "space": 400, "date": "2026-07-01", "url": "https://front.alforaij.com/Listing/Detail/310"},
                        {"code": "AF-311", "area": "النهضة", "price": 350000, "space": 400, "date": "2026-06-20", "url": "https://front.alforaij.com/Listing/Detail/311"},
                    ],
                    "financing": {"down_payment": 105000, "monthly_payment": 1874.23, "interest_rate_percent": 4.5, "years": 15},
                    "numberSources": {
                        "price": {"display": "350 ألف د.ك", "source": "حقل السعر في بيانات الفريج"},
                        "pricePerSqm": {"display": "875 د.ك/م²", "source": "سعر المطلوب ÷ مساحة الإعلان"},
                        "marketMedian": {"display": "355,000 د.ك", "source": "وسيط أسعار المقارنات"},
                        "officialValue": {"display": "غير متوفر", "source": "لا توجد بيانات رسمية موثوقة"},
                        "comparablesCount": {"value": 2, "source": "عدد المقارنات السعرية الداخلة"},
                    },
                    "warnings": ["عدد المقارنات أقل من الحد المفضل"],
                }
            ],
        }

    def test_build_pdf_returns_pdf_bytes(self) -> None:
        from backend.services.pdf_report import build_pdf

        pdf = build_pdf(self._sample_report())
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 5000)
        self.assertIn(b"/Type /Page", pdf)

    def test_build_pdf_handles_empty_report(self) -> None:
        from backend.services.pdf_report import build_pdf

        pdf = build_pdf({})
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 1000)

    def test_build_pdf_handles_none(self) -> None:
        from backend.services.pdf_report import build_pdf

        pdf = build_pdf(None)
        self.assertTrue(pdf.startswith(b"%PDF"))

    def test_build_pdf_includes_clickable_ad_links(self) -> None:
        """كل إعلان يحمل رابطًا مباشرًا قابلاً للنقر (URI annotation) في جدول النتائج والمقارنات."""
        import io

        from pypdf import PdfReader

        from backend.services.pdf_report import build_pdf

        pdf = build_pdf(self._sample_report())
        self.assertIn(b"https://front.alforaij.com/Listing/Detail/278", pdf)
        self.assertIn(b"https://front.alforaij.com/Listing/Detail/310", pdf)
        reader = PdfReader(io.BytesIO(pdf))
        uris: list[str] = []
        for page in reader.pages:
            for annot_ref in page.get("/Annots") or []:
                annot = annot_ref.get_object()
                uri = (annot.get("/A") or {}).get("/URI")
                if uri:
                    uris.append(str(uri))
        self.assertIn("https://front.alforaij.com/Listing/Detail/278", uris)
        self.assertIn("https://front.alforaij.com/Listing/Detail/310", uris)

    def test_build_pdf_skips_missing_links_gracefully(self) -> None:
        """إعلان بلا رابط لا يكسر التقرير ويُعرض بشرطة."""
        from backend.services.pdf_report import build_pdf

        report = self._sample_report()
        report["results"][0]["originalUrl"] = ""
        report["results"][0]["comparables"][0]["url"] = None
        pdf = build_pdf(report)
        self.assertTrue(pdf.startswith(b"%PDF"))
        self.assertGreater(len(pdf), 5000)

    def test_build_pdf_includes_sources_evidence_table(self) -> None:
        """جدول «المصادر والأدلة» يظهر في نهاية التقرير بكل الحقول وآلية الجلب والروابط."""
        import io

        from pypdf import PdfReader

        from backend.services.pdf_report import build_pdf

        report = self._sample_report()
        report["sourceStatus"] = [
            {
                "name": "الفريج",
                "status": "success",
                "records": 12,
                "note": "بيانات محلية.",
            },
            {
                "name": "OpenSooq",
                "status": "success",
                "records": 20,
                "candidates": 20,
                "responseMs": 4696,
                "attempts": 1,
                "fetchMethod": "حمولة JSON مضمّنة (__NEXT_DATA__)",
                "endpoint": "https://kw.opensooq.com/en/find?term=office",
                "note": "تم البحث واستخراج النتائج.",
            },
            {
                "name": "4Sale",
                "status": "fallback",
                "records": 0,
                "responseMs": 6883,
                "attempts": 4,
                "fetchMethod": "فحص HTML",
                "endpoint": "https://kw.opensooq.com/",
                "note": "تعذر الوصول — استُخدم المصدر البديل.",
            },
        ]
        pdf = build_pdf(report)
        self.assertIn(b"https://kw.opensooq.com/en/find?term=office", pdf)
        reader = PdfReader(io.BytesIO(pdf))
        text = "".join(page.extract_text() or "" for page in reader.pages)
        # رأس الجدول وأسماء المصادر ظاهرة في نص المستند
        self.assertIn("OpenSooq", text)
        self.assertIn("4Sale", text)

    def test_build_pdf_accepts_arabic_title(self) -> None:
        """عنوان عربي مخصص يظهر في رأس المستند بدل العنوان الافتراضي."""
        from backend.services.pdf_report import build_pdf

        pdf = build_pdf(self._sample_report(), title="تقرير تقييم إيجار المكاتب — حولي والعاصمة")
        self.assertTrue(pdf.startswith(b"%PDF"))
        # العنوان يُشكَّل ويُطبع في محتوى الصفحة الأولى (يظهر في بيانات البايتات بعد التشكيل)
        self.assertGreater(len(pdf), 5000)

    def test_build_pdf_adds_client_recommendations_page(self) -> None:
        """صفحة توصيات العميل تُضاف في نهاية التقرير عند تمرير قائمة توصيات."""
        import io

        from pypdf import PdfReader

        from backend.services.pdf_report import build_pdf

        import unicodedata

        recs = ["الإعلان OS-285406788 في حولي — 240 د.ك.", "تواصل فورًا قبل انتهاء العرض."]
        base = build_pdf(self._sample_report())
        with_recs = build_pdf(self._sample_report(), client_recommendations=recs)
        self.assertGreater(len(with_recs), len(base))
        reader = PdfReader(io.BytesIO(with_recs))
        # pypdf يستخرج العربية بأشكال العرض (presentation forms) — نحوّلها NFKC للمقارنة
        text = unicodedata.normalize("NFKC", "".join(page.extract_text() or "" for page in reader.pages))
        self.assertGreater(len(reader.pages), 2)  # صفحة إضافية للتوصيات
        self.assertIn("توصيات العميل", text)


if __name__ == "__main__":
    unittest.main()
