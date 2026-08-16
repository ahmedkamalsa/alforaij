"""فحص صفحة «لماذا مجاني وأدق»: التبويب، صفوف المقارنة، المصادر، الأزرار، الجوال."""
import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("ALFORAIJ_MOBILE_BASE", "http://127.0.0.1:8000/")


def main() -> int:
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        console_errors = []
        failed_requests = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        page.on("requestfailed", lambda r: failed_requests.append(r.url))
        page.goto(BASE, wait_until="networkidle")

        # التبويب موجود
        tab = page.locator('.main-tab[data-main-tab="why-free"]')
        if tab.count() == 0:
            failures.append("التبويب why-free غير موجود")
        else:
            tab.first.click()
            page.wait_for_timeout(300)

        # اللوحة ظاهرة
        panel = page.locator('.whyfree-panel[data-main-panel="why-free"]')
        if not panel.is_visible():
            failures.append("لوحة why-free غير ظاهرة")

        # عدد صفوف المقارنة (1 رأس + 9 مقارنات)
        rows = panel.locator(".whyfree-row")
        if rows.count() != 10:
            failures.append(f"عدد الصفوف {rows.count()} بدل 10")

        # جدول «بداية التغطية لكل منصة»: رأس + صفوف، ومحتوى موثق
        coverage = page.locator("#platformDatesWrap")
        if coverage.count() == 0:
            failures.append("جدول بداية التغطية غير موجود")
        else:
            coverage_rows = coverage.locator(".coverage-row")
            if coverage_rows.count() < 9:
                failures.append(f"صفوف التغطية {coverage_rows.count()} بدل >= 9 (رأس + منصات)")
            cov_text = coverage.inner_text()
            for phrase in ["المنصة", "إعلانات", "أول جلب", "أقدم تاريخ نشر", "OpenSooq", "4Sale"]:
                if phrase not in cov_text:
                    failures.append(f"عبارة التغطية مفقودة: {phrase}")
            if "2026/08" not in cov_text:
                failures.append(f"تاريخ أول جلب غير ظاهر بالصيغة المتوقعة: {cov_text[:120]}")

        # روابط المصادر الخارجية
        links = panel.locator(".whyfree-src a, .whyfree-sources a")
        if links.count() < 5:
            failures.append(f"روابط المصادر {links.count()} بدل >= 5")

        # العبارة الجوهرية
        text = panel.inner_text()
        for phrase in [
            "الترتيب بالمصلحة، لا بالدفع",
            "10 أيام فقط",
            "1,000 درهم",
            "أفضل صفقة أولًا",
            "2% من سعر البيع",
            "5% من الإيجار السنوي",
            "4% من قيمة العقار",
            "500–2,000+ درهم لكل إعلان",
            "رسوم نقل الملكية (DLD)",
            "باقات الوكلاء السنوية",
            "إغلاق الصفقة — عمولة الوسيط",
        ]:
            if phrase not in text:
                failures.append(f"العبارة مفقودة: {phrase}")

        # زر CTA الأول يقفز للبحث
        cta = panel.locator(".whyfree-cta[data-go='search']")
        cta.first.click()
        page.wait_for_timeout(300)
        search_tab = page.locator('.main-tab[data-main-tab="search"]')
        if not search_tab.first.evaluate("el => el.classList.contains('active')"):
            failures.append("زر CTA لم يعُد للبحث")
        # العودة
        tab.first.click()
        page.wait_for_timeout(300)

        # زر المشاركة: يبني رابط واتساب بنص المقارنة الموجز (اعتراض window.open
        # لأن wa.me تعيد التوجيه إلى api.whatsapp.com وتغيّر ترميز الرابط)
        share_url = page.evaluate(
            """() => {
              let url = '';
              const orig = window.open;
              window.open = (u) => { url = u; return null; };
              shareWhyFreePage();
              window.open = orig;
              return url;
            }"""
        )
        if not share_url.startswith("https://wa.me/?text="):
            failures.append(f"رابط المشاركة غير متوقع: {share_url[:60]}")
        else:
            import urllib.parse

            message = urllib.parse.unquote(share_url.split("text=", 1)[1])
            for phrase in ["لماذا مجاني وأدق", "4Sale", "1,000 درهم", "رسوم DLD", "المصلحة لا بالدفع", "منصة الفريج"]:
                if phrase not in message:
                    failures.append(f"عبارة المشاركة مفقودة: {phrase}")
            if "\ufffd" in message:
                failures.append("الرسالة تحتوي حرف استبدال (ترميز مكسور)")

        # جوال 390px: لا تجاوز أفقي
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(300)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        if overflow:
            failures.append("تجاوز أفقي على 390px")
        # التبويب القصير ظاهر
        short_visible = page.locator(".main-tab[data-main-tab='why-free'] .tab-short").first.is_visible()
        if not short_visible:
            failures.append("الاسم القصير للتبويب غير ظاهر على الجوال")

        page.screenshot(path="tests/playwright/_whyfree.png", full_page=False)
        browser.close()

    if console_errors:
        failures.append(f"أخطاء كونسول: {console_errors[:3]}")
    if failed_requests:
        failures.append(f"طلبات فاشلة: {failed_requests[:3]}")

    print(json.dumps({"failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
