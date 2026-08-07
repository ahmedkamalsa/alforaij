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
                    "comparables": [
                        {"code": "AF-310", "area": "النهضة", "price": 360000, "space": 400, "date": "2026-07-01"},
                        {"code": "AF-311", "area": "النهضة", "price": 350000, "space": 400, "date": "2026-06-20"},
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


if __name__ == "__main__":
    unittest.main()
