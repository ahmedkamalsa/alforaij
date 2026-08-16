"""فحص الخريطة التفاعلية Leaflet: التبديل من الشبكة، تحميل المكتبة، العلامات الملونة، النوافذ المنبثقة."""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("ALFORAIJ_MOBILE_BASE", "http://127.0.0.1:8000/")


def main() -> int:
    failures: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 1000})
        console_errors: list[str] = []
        page.on("console", lambda m: console_errors.append(m.text) if m.type == "error" else None)
        # load بدل networkidle: الخادم المحلي يخدم نقاط API ثقيلة (ملخص اللوحة/التحليلات)
        # بالتسلسل، فانتظار استقرار الشبكة قد يتجاوز المهلة — ننتظر عناصر الخريطة صراحة.
        page.goto(BASE, wait_until="load", timeout=90000)
        page.wait_for_timeout(1200)

        # فتح تبويب التحليلات (فيه الخريطة الحرارية)
        page.click('[data-main-tab="insights"]')
        page.wait_for_timeout(1500)
        # شبكة المناطق لا تحتاج بيانات التحليلات الثقيلة لظهور أزرار التبديل
        page.wait_for_function("document.querySelectorAll('.heatmap-view-switch .view-btn').length >= 2", timeout=20000)

        if page.locator(".heatmap-view-switch .view-btn").count() < 2:
            failures.append("أزرار تبديل العرض غير موجودة")

        # الشبكة ظاهرة افتراضيًا والخريطة مخفية
        grid_hidden = page.evaluate("document.querySelector('#insightsHeatmap').hidden")
        if grid_hidden:
            failures.append("شبكة المناطق مخفية افتراضيًا")

        # تفعيل الخريطة التفاعلية
        page.click('.heatmap-view-switch .view-btn[data-heat-view="map"]')
        page.wait_for_timeout(5000)  # تحميل Leaflet من CDN + إنشاء الخريطة + استقرار fitBounds

        container = page.locator("#insightsLeafletMap")
        if not container.is_visible():
            failures.append("حاوية الخريطة غير ظاهرة بعد التبديل")
        # Leaflet يضيف فئة leaflet-container على الحاوية نفسها (ليست سليلًا)
        if not page.evaluate("document.querySelector('#insightsLeafletMap')?.classList.contains('leaflet-container')"):
            failures.append("Leaflet لم يُهيّئ (قد يكون الاتصال بالشبكة غير متاح)")
        else:
            marker_count = page.locator("#insightsLeafletMap path.leaflet-interactive").count()
            if marker_count < 5:
                failures.append(f"عدد العلامات {marker_count} أقل من 5")

        # شريط فلاتر نقاط الإعلانات: ظاهر في وضع الخريطة، وفيه رقائق مصدر/نوع
        if page.evaluate("document.querySelector('#mapListingFilters')?.hidden !== false"):
            failures.append("شريط فلاتر نقاط الإعلانات مخفي في وضع الخريطة")
        chips = page.locator(".map-filter-chip")
        if chips.count() < 4:
            failures.append(f"رقائق الفلترة قليلة جدًا ({chips.count()})")
        else:
            # أهداف لمس ≥ 44px لكل رقاقة (مثل فحص الجوال)
            small_chips = page.evaluate("""() => {
              const out = [];
              for (const el of document.querySelectorAll('.map-filter-chip')) {
                const r = el.getBoundingClientRect();
                if (r.height < 44 || r.width < 44) out.push(el.innerText.trim().slice(0, 12));
              }
              return out.slice(0, 10);
            }""")
            if small_chips:
                failures.append(f"رقائق أصغر من 44px: {small_chips}")

        # عدّاد النقاط: ينتظر اكتمال تحميل سجلات اللوحة (نقاط ظاهرة: X من Y)
        try:
            page.wait_for_function(
                "document.querySelector('#mapListingCount')?.textContent.includes('نقاط ظاهرة')",
                timeout=20000,
            )
        except Exception:
            failures.append("عدّاد نقاط الإعلانات لم يُملأ (فشل جلب سجلات اللوحة)")
        counter_before = page.evaluate("document.querySelector('#mapListingCount').textContent")
        total_shown = int(counter_before.split("من")[0].split(":")[1].strip())
        if total_shown < 5:
            failures.append(f"نقاط الإعلانات الظاهرة قليلة جدًا ({total_shown})")

        # فلترة بالنقر على أول رقاقة مصدر: تنقص النقاط، وتظهر رقاقة نشطة وزر مسح
        first_chip = chips.first
        first_chip_label = first_chip.inner_text().strip()
        first_chip.click()
        page.wait_for_timeout(600)
        counter_after = page.evaluate("document.querySelector('#mapListingCount').textContent")
        after_shown = int(counter_after.split("من")[0].split(":")[1].strip())
        if after_shown >= total_shown:
            failures.append(f"الفلترة لم تقلل النقاط ({total_shown} → {after_shown}) لرقاقة {first_chip_label!r}")
        if not first_chip.evaluate("el => el.classList.contains('active')"):
            failures.append("الرقاقة لم تُفعّل بعد النقر")
        clear_btn = page.locator("#mapFilterClearBtn")
        if clear_btn.is_hidden():
            failures.append("زر مسح الفلاتر مخفي رغم وجود فلتر نشط")

        # مسح الفلاتر يعيد كل النقاط ويخفي زر المسح
        clear_btn.click()
        page.wait_for_timeout(600)
        counter_restored = page.evaluate("document.querySelector('#mapListingCount').textContent")
        restored_shown = int(counter_restored.split("من")[0].split(":")[1].strip())
        if restored_shown != total_shown:
            failures.append(f"مسح الفلاتر لم يستعد النقاط ({after_shown} → {restored_shown})")
        if not clear_btn.is_hidden():
            failures.append("زر مسح الفلاتر ما زال ظاهرًا بعد المسح")

        # نافذة منبثقة عند النقر على علامة (force لتجاوز التقاطع مع طبقة البلاط)
        # قد تفتح نافذة منطقة (زر احجز) أو نافذة إعلان (درجة الفرصة + فتح الإعلان) — كلاهما مقبول
        first_marker = page.locator("#insightsLeafletMap path.leaflet-interactive").first
        if first_marker.count():
            try:
                first_marker.click(force=True, timeout=5000)
                page.wait_for_timeout(700)
                popup = page.locator(".leaflet-popup-content")
                if popup.count() == 0 or len(popup.first.inner_text().strip()) < 5:
                    failures.append("النافذة المنبثقة فارغة/غائبة")
                else:
                    text = popup.first.inner_text()
                    if not ("احجز" in text or "مراق" in text or "درجة الفرصة" in text or "فتح الإعلان" in text):
                        failures.append("النافذة المنبثقة بلا محتوى معروف (حجز/فرصة)")
            except Exception as exc:
                failures.append(f"النقر على العلامة فشل: {exc}")

        # العودة للشبكة: يُخفى شريط الفلاتر
        page.click('.heatmap-view-switch .view-btn[data-heat-view="grid"]')
        page.wait_for_timeout(300)
        if not page.evaluate("!document.querySelector('#insightsHeatmap').hidden"):
            failures.append("العودة للشبكة فشلت")
        if page.evaluate("document.querySelector('#mapListingFilters')?.hidden !== true"):
            failures.append("شريط فلاتر نقاط الإعلانات لم يُخفَ عند العودة للشبكة")

        browser.close()

    if console_errors:
        failures.append(f"أخطاء كونسول: {console_errors[:5]}")
    for f in failures:
        print(f"❌ {f}")
    print(f"{'✅' if not failures else '❌'} الخريطة التفاعلية: {'نجح' if not failures else f'{len(failures)} فشلًا'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
