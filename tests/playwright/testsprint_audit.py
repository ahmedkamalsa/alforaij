"""فحص شامل بأسلوب TestSprint: الواجهة + التفاعلات + الأخطاء.

يغطي:
- تحميل الصفحة: أخطاء كونسول، أخطاء صفحات، طلبات فاشلة.
- التبويبات الستة تفتح وتمتلئ فعليًا.
- بحث حقيقي: نتائج، شريط مصادر، نسخ الروابط، مؤشر الثقة، تلميح التمرير.
- اللوحة: توحيد المحافظات، نقر البطاقة يفتح درج التفاصيل، إغلاقه بـ Esc.
- الفرص: شريط المنصات والفلترة بالنقر.
- الجوال: تجاوز أفقي، أهداف لمس، عناصر بلا أسماء (مع احترام label).
- إمكانية الوصول: أسماء تفاعلية صحيحة.

الخروج: 0 عند النجاح، 1 عند وجود أخطاء.
"""
from __future__ import annotations

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("ALFORAIJ_MOBILE_BASE", "http://127.0.0.1:8000/")
CONSOLE_ERRORS: list[str] = []
PAGE_ERRORS: list[str] = []
FAILED_REQUESTS: list[str] = []
CHECKS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append({"name": name, "ok": ok, "detail": detail})
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))


def attach(page) -> None:
    page.on("console", lambda m: CONSOLE_ERRORS.append(m.text) if m.type == "error" else None)
    page.on("pageerror", lambda e: PAGE_ERRORS.append(str(e)))
    page.on("requestfailed", lambda r: FAILED_REQUESTS.append(f"{r.method} {r.url}"))


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        attach(page)
        page.goto(BASE, wait_until="networkidle", timeout=90000)
        page.wait_for_timeout(1500)

        # 1) التحميل الأساسي
        check("تحميل الصفحة الرئيسية", "البحث والتقييم" in page.locator("body").inner_text())
        check("عنوان الصفحة غير فارغ", bool(page.title()), page.title()[:60])

        # 2) كل تبويب يفتح ويمتلئ
        tabs = ["search", "opportunities", "board", "insights", "developments", "sources"]
        tab_names = {"search": "البحث والتقييم", "opportunities": "أفضل الفرص", "board": "لوحة السوق",
                     "insights": "تحليلات السوق", "developments": "التطورات", "sources": "المصادر والتشغيل"}
        for t in tabs:
            page.click(f"[data-main-tab='{t}']")
            page.wait_for_timeout(4000)  # insights والتطورات تحتاج تحميل بيانات
            visible = page.locator(f"[data-main-panel='{t}']").first.is_visible()
            check(f"تبويب «{tab_names[t]}» يفتح", visible, t)
            text = page.locator(f"[data-main-panel='{t}']").first.inner_text()
            ok = len(text.strip()) > 100 and "جاري التحميل" not in text[:200]
            check(f"محتوى «{tab_names[t]}» محمّل فعليًا", ok, f"{len(text.strip())} حرف")

        # 3) بحث حقيقي
        page.click("[data-main-tab='search']")
        page.wait_for_timeout(600)
        chat = page.locator("#chatInput")
        chat.fill("بيت للبيع في الفردوس 300 متر")
        page.keyboard.press("Enter")
        page.wait_for_timeout(3000)
        page.wait_for_timeout(30000)  # انتظار نتائج التحليل
        results = page.locator(".results-panel")
        cards = results.locator("[class*='result-card'], .opp-card, .result-item").count()
        check("نتائج البحث تظهر", cards >= 1, f"{cards} بطاقة")

        # شريط مصادر النتائج
        src_bar = page.locator("#resultsSources")
        if src_bar.count() > 0 and src_bar.first.is_visible():
            chips = src_bar.locator(".results-source-chip")
            check("شريط مصادر النتائج يظهر", True)
            check("شريحة مصدر واحدة على الأقل", chips.count() >= 1, f"{chips.count()} شرائح")
            # مؤشر الثقة داخل الشريحة
            dots = src_bar.locator(".results-source-dot")
            check("مؤشر الثقة داخل الشرائح", dots.count() >= 1, f"{dots.count()} نقاط")
            # زر نسخ الروابط
            copy_btn = src_bar.locator("button:has-text('نسخ')")
            check("زر نسخ روابط المصادر موجود", copy_btn.count() >= 1)
            if copy_btn.count() > 0:
                page.evaluate("navigator.clipboard.writeText = (t) => { window.__copied = t; return Promise.resolve(); }")
                copy_btn.first.click()
                page.wait_for_timeout(600)
                copied = page.evaluate("window.__copied || ''")
                has_links = "http" in copied.lower()
                has_names = any(n in copied for n in ["الفريج", "Mourjan", "Q8Aqar", "OpenSooq"])
                check("النسخ يلتقط المحتوى", has_links and has_names, f"{len(copied)} حرف")
        else:
            check("شريط مصادر النتائج يظهر", False, "غير موجود/مخفي بعد البحث")

        # 4) اللوحة: توحيد المحافظات + درج التفاصيل
        page.click("[data-main-tab='board']")
        page.wait_for_timeout(3000)
        gov_text = page.locator(".governorate-board").first.inner_text() if page.locator(".governorate-board").count() else ""
        if "محافظة الأحمدي" in gov_text:
            hamza = gov_text.count("محافظة الأحمدي")
            plain = gov_text.count("محافظة الاحمدي")
            check("توحيد محافظة الأحمدي (لا تكرار بالهمزة)", plain == 0, f"الأحمدي×{hamza} الاحمدي×{plain}")
        metric = page.locator("button.board-metric-card").first
        if metric.count() > 0:
            metric.click()
            page.wait_for_timeout(1200)
            drawer = page.locator(".drill-drawer, .drill-panel, [class*='drill-drawer']")
            opened = drawer.count() > 0 and drawer.first.is_visible()
            check("النقر على رقم يفتح درج التفاصيل", opened)
            if opened:
                dtext = drawer.first.inner_text()
                check("الدرج يعرض إعلانات فعلية", "فتح على" in dtext or "إعلان" in dtext or "كود" in dtext,
                      f"{len(dtext)} حرف")
                page.keyboard.press("Escape")
                page.wait_for_timeout(700)
                closed = page.evaluate("""() => {
                  return [...document.querySelectorAll('.drill-drawer, .drill-panel, [class*="drill-drawer"]')]
                    .every(e => e.offsetParent === null || getComputedStyle(e).display === 'none');
                }""")
                check("الدرج يُغلق بـ Escape", closed)
        else:
            check("بطاقات الأرقام القابلة للنقر موجودة", False, "لا توجد .board-metric-card")

        # 5) الفرص: شريط المنصات والفلترة
        page.click("[data-main-tab='opportunities']")
        page.wait_for_timeout(3500)
        opp_bar = page.locator("#oppSourcesBar")
        if opp_bar.count() > 0 and opp_bar.first.is_visible():
            chips = opp_bar.locator("button.opp-platform-chip")
            check("شريط منصات الفرص يظهر", True)
            check("شرائح منصات قابلة للنقر", chips.count() >= 2, f"{chips.count()} شرائح")
            if chips.count() >= 2:
                # نقر شريحة ثانية (غير «الكل») — الفلترة
                target = chips.nth(1)
                target.click()
                page.wait_for_timeout(1200)
                active = page.evaluate("""() => {
                  const el = document.querySelector('#oppSourcesBar .opp-platform-chip.active');
                  return el ? el.getAttribute('data-opp-platform') : null;
                }""")
                check("النقر على منصة يفلتر الفرص", active is not None, f"النشط: {active}")
                # زر الكل يعيد العرض
                page.locator("#oppSourcesBar button[data-opp-platform='']").click()
                page.wait_for_timeout(800)
                all_chips = page.locator("#oppSourcesBar .opp-platform-chip").count()
                check("زر «الكل» يعيد العرض", all_chips >= 2, f"{all_chips} شرائح")
        else:
            check("شريط منصات الفرص يظهر", False, "غير موجود")

        # 6) المصادر
        page.click("[data-main-tab='sources']")
        page.wait_for_timeout(2500)
        src_text = page.locator("[data-main-panel='sources']").first.inner_text()
        check("تبويب المصادر يعرض محتوى", "مصدر" in src_text or "تشغيل" in src_text, f"{len(src_text)} حرف")

        # 7) لا أخطاء كونسول/صفحات/طلبات
        check("لا أخطاء كونسول", len(CONSOLE_ERRORS) == 0, "; ".join(CONSOLE_ERRORS[:3]))
        check("لا أخطاء صفحات JS", len(PAGE_ERRORS) == 0, "; ".join(PAGE_ERRORS[:3]))
        check("لا طلبات شبكة فاشلة", len(FAILED_REQUESTS) == 0, "; ".join(FAILED_REQUESTS[:3]))

        # 8) الجوال
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(1500)
        overflow = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
        check("لا تجاوز أفقي على الجوال (390px)", not overflow)
        small = page.evaluate("""() => {
          const out = [];
          for (const el of document.querySelectorAll('button, [role="button"], .source-chip, .platform-chip, .opp-platform-chip')) {
            const r = el.getBoundingClientRect();
            if (r.width > 0 && r.height > 0 && r.height < 44 && r.top >= 0 && r.top < window.innerHeight) {
              const cls = (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0,2).join('.') : el.tagName;
              out.push(cls + ':' + Math.round(r.height));
            }
          }
          return out.slice(0, 8);
        }""")
        check("أهداف اللمس ≥ 44px", len(small) == 0, "; ".join(small))

        # 9) إمكانية الوصول: عناصر تفاعلية بلا اسم (مع احترام label المحيط)
        aria = page.evaluate("""() => {
          const out = [];
          for (const el of document.querySelectorAll('button, a[href], input, select, textarea')) {
            const r = el.getBoundingClientRect();
            if (r.width === 0 || r.height === 0) continue;
            const hasLabelWrap = el.closest('label') !== null;
            const label = el.getAttribute('aria-label') || (el.textContent || '').trim() ||
                          el.getAttribute('placeholder') || el.getAttribute('title') ||
                          (el.id && document.querySelector('label[for="' + el.id + '"]') ? 'x' : '');
            if (!label && !hasLabelWrap) {
              const cls = (el.className && typeof el.className === 'string') ? el.className.split(' ').slice(0,2).join('.') : el.tagName;
              out.push(el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + '.' + cls);
            }
          }
          return out.slice(0, 8);
        }""")
        check("العناصر التفاعلية لها أسماء صحيحة", len(aria) == 0, "; ".join(aria))

        # 10) تنقل التبويبات على الجوال
        for t in ["board", "opportunities", "insights"]:
            page.click(f"[data-main-tab='{t}']")
            page.wait_for_timeout(1200)
            ov = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")
            if ov:
                check(f"جوال: تبويب {t} بلا تجاوز", False)
        check("جوال: التبويبات الرئيسية بلا تجاوز", True, "board/opportunities/insights")

        browser.close()

    total = len(CHECKS)
    passed = sum(1 for c in CHECKS if c["ok"])
    print("\n" + "=" * 60)
    print(f"النتيجة: {passed}/{total} نجحت")
    print("=" * 60)
    if passed < total:
        for c in CHECKS:
            if not c["ok"]:
                print(f"  ❌ {c['name']}" + (f" — {c['detail']}" if c["detail"] else ""))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
