"""فحص سجل سعر العقار: خط زمني للسعر عند كل ظهور في بطاقة التحليل.

يعترض نداء Supabase listing_price_observations (نمط shareCountsBase) ويعيد خطًا
زمنيًا اصطناعيًا — يتحقق من ظهور الكتلة، ملاحظة الانخفاض، طيّ التكرار، أسهم
الانخفاض، والإخفاء في الوضع المبسّط. صفر أخطاء كونسول.
"""
from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("ALFORAIJ_MOBILE_BASE", "http://127.0.0.1:8000/")

HISTORY_ROWS = [
    {"price": 280000, "seen_at": "2026-07-10T00:00:00+00:00"},
    {"price": 280000, "seen_at": "2026-07-11T00:00:00+00:00"},
    {"price": 280000, "seen_at": "2026-07-12T00:00:00+00:00"},
    {"price": 265000, "seen_at": "2026-07-15T00:00:00+00:00"},
    {"price": 265000, "seen_at": "2026-07-16T00:00:00+00:00"},
    {"price": 255000, "seen_at": "2026-07-20T00:00:00+00:00"},
]

REPORT = {
    "summary": "تقرير اختبار",
    "analysisMethod": "local",
    "persistence": {"label": "جلسة"},
    "searchScope": None,
    "extractedFilters": [],
    "sourceStatus": [],
    "transactionSummary": None,
    "rankingMethod": None,
    "profitOpportunities": {},
    "similarExternal": {},
    "results": [
        {
            "code": "PH-1",
            "area": "السالمية",
            "governorate": "حولي",
            "propertyType": "بيت",
            "transaction": "للبيع",
            "price": 255000,
            "priceText": "255,000 د.ك",
            "source": "4Sale",
            "publishedDate": "2026-07-20",
            "recommendationScore": 80,
            "valuationLabel": "فرصة قوية",
        },
    ],
}


def main() -> int:
    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        console_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: console_errors.append(str(e)))

        def handle_history(route) -> None:
            route.fulfill(status=200, content_type="application/json", body=json.dumps(HISTORY_ROWS))

        page.route("**/rest/v1/listing_price_observations**", handle_history)

        page.goto(BASE, wait_until="load", timeout=90000)
        page.wait_for_selector("#mainTabs", timeout=30000)
        page.wait_for_timeout(1500)

        page.evaluate(f"renderReport({json.dumps(REPORT, ensure_ascii=False)})")
        page.wait_for_timeout(700)

        # 1) الكتلة تظهر بعد الجلب المحروس من القاعدة الحية
        block = page.locator("#results .result-card .price-history")
        if block.count() == 0:
            failures.append("كتلة سجل السعر غير موجودة في البطاقة")
        elif not block.is_visible():
            failures.append("كتلة سجل السعر مخفية رغم توفر البيانات")

        # 2) ملاحظة الانخفاض: من 280,000 إلى 255,000
        meta = block.locator(".price-history-meta").inner_text() if block.count() else ""
        if "انخفض" not in meta or "255,000" not in meta:
            failures.append(f"ملاحظة الانخفاض خاطئة: {meta}")

        # 3) المقاطع الثلاثة مع طيّ التكرار (280K شوهد 3 مرات)
        rows = block.locator(".ph-row")
        if rows.count() != 3:
            failures.append(f"عدد مقاطع السعر {rows.count()} بدل 3")
        first_row = rows.nth(0).inner_text() if rows.count() else ""
        if "شوهد 3 مرات" not in first_row:
            failures.append(f"طيّ التكرار غائب: {first_row}")

        # 4) أسهم الانخفاض على المقاطع اللاحقة
        if rows.count() >= 3:
            second_delta = rows.nth(1).locator(".ph-delta").inner_text()
            third_delta = rows.nth(2).locator(".ph-delta").inner_text()
            if "📉" not in second_delta or "📉" not in third_delta:
                failures.append(f"أسهم الانخفاض ناقصة: {second_delta} / {third_delta}")

        # 5) الإخفاء في الوضع المبسّط (لا جداول تحليلية)
        toggle = page.locator("#simpleModeToggle")
        if toggle.count():
            toggle.first.click()
            page.wait_for_timeout(200)
            hidden = page.evaluate(
                "getComputedStyle(document.querySelector('#results .result-card .price-history')).display"
            )
            if hidden != "none":
                failures.append(f"سجل السعر ظاهر في الوضع المبسّط ({hidden})")

        browser.close()

    if console_errors:
        failures.append(f"أخطاء كونسول: {console_errors[:5]}")
    for f in failures:
        print(f"❌ {f}")
    print(f"{'✅' if not failures else '❌'} سجل سعر العقار: {'نجح' if not failures else f'{len(failures)} فشلًا'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
