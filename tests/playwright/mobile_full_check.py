"""فحص جوال شامل (390px) لأقسام المنصة الخمسة.

يجرّب بحثًا حقيقيًا (نتائج + بطاقات)، وبطاقات الفرص، وجدول المحافظات في اللوحة،
وتحليلات السوق، وقسم المصادر — ويتحقق في كل قسم من: عدم تجاوز الصفحة أفقيًا،
ظهور المحتوى، وعدم وجود عناصر خارجة عن الشاشة خارج حاويات التمرير الداخلية.
"""
from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("ALFORAIJ_MOBILE_BASE", "http://127.0.0.1:8000/")
VIEWPORT = {"width": 390, "height": 844}
errors: list[str] = []


def page_overflow(page) -> bool:
    return page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")


def offenders(page) -> list[dict]:
    """عناصر تمتد خارج الشاشة وليست داخل حاوية تمرير داخلية."""
    return page.evaluate("""
      () => {
        const out = [];
        for (const el of document.querySelectorAll('body *')) {
          const r = el.getBoundingClientRect();
          if (r.right > document.documentElement.clientWidth + 1 || r.left < -1) {
            const scrollable = el.closest('.table-scroll, .results, .board-stats, .hist-chart, [style*="overflow"]');
            if (scrollable) continue;
            const tag = el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + (el.className && typeof el.className === 'string' ? '.' + el.className.split(' ').slice(0, 2).join('.') : '');
            out.push({ el: tag.slice(0, 60), left: Math.round(r.left), right: Math.round(r.right), w: Math.round(r.width) });
          }
        }
        return out.slice(0, 10);
      }
    """)


def tab_click(page, index):
    page.locator(".main-tab").nth(index).click()
    page.wait_for_timeout(1500)


def touch_audit(page) -> list:
    """أهداف لمس < 44px على الشاشة الحالية.

    يُستثنى الرابط النصي السطري (display:inline داخل جملة) وفق استثناء
    WCAG 2.5.8 — أما الأزرار وروابط الأزرار والشرائح ورؤوس الطي فتُفحص كلها.
    """
    return page.evaluate("""() => {
      const MIN = 44;
      const out = [];
      for (const el of document.querySelectorAll('button, a[href], summary, [role="button"], [role="tab"]')) {
        const cs = getComputedStyle(el);
        if (cs.display === 'none' || cs.visibility === 'hidden') continue;
        const r = el.getBoundingClientRect();
        if (r.width === 0 || r.height === 0) continue;
        if (el.tagName === 'A' && cs.display === 'inline') continue;
        if (r.height < MIN || r.width < MIN) {
          const cls = typeof el.className === 'string' ? '.' + el.className.split(' ').slice(0, 2).join('.') : '';
          out.push({el: el.tagName.toLowerCase() + (el.id ? '#' + el.id : '') + cls, w: Math.round(r.width), h: Math.round(r.height), t: (el.innerText || '').trim().slice(0, 12)});
        }
      }
      return out.slice(0, 40);
    }""")


def opp_subtab_check(page, tier: str) -> dict:
    """فتح تبويب فرعي للفرص والانتظار حتى يكتمل تحميله ثم فحص التجاوز."""
    page.locator(f".opp-tab[data-tier=\"{tier}\"]").click()
    # يبدأ كل تبويب فرعي بـ «جاري التحميل...» ثم يُملأ من API — ننتظر انتهاء التحميل
    page.wait_for_function(
        "!document.querySelector('#oppList').innerText.includes('جاري التحميل')",
        timeout=60000,
    )
    page.wait_for_timeout(600)
    return {
        "overflow": page_overflow(page),
        "widestInList": page.evaluate(
            "Math.round(Math.max(0, ...[...document.querySelectorAll('#oppList *')].map(el => el.getBoundingClientRect().right)))"
        ),
        "contentLen": page.evaluate("document.querySelector('#oppList').innerText.trim().length"),
        "offenders": offenders(page),
    }


with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport=VIEWPORT)
    page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.goto(BASE, wait_until="networkidle", timeout=90000)
    results: dict = {"viewport": page.evaluate("window.innerWidth")}

    # ── 1) البحث: إرسال استعلام حقيقي وفحص النتائج ──
    page.fill("#chatInput", "بيع بيت في صباح الناصر")
    page.click("#sendChatBtn")
    # «#resultCount» يبدأ بالنص «0» فلا يصلح للانتظار — ننتظر ظهور بطاقات النتائج فعلًا
    page.wait_for_selector("#results .result-card", timeout=90000)
    page.wait_for_timeout(2000)
    results["search"] = {
        "overflow": page_overflow(page),
        "resultCards": page.locator("#results .result-card").count(),
        "countText": page.locator("#resultCount").inner_text(),
        "offenders": offenders(page),
        "touch": touch_audit(page),
    }
    page.screenshot(path="tests/playwright/mobile_search_results.png")

    # ── 2) الفرص: بطاقات الفرص + التبويبات الفرعية (العملاء/العرض والطلب/الجديد والمحذوف/الأداء الزمني) ──
    tab_click(page, 1)
    page.wait_for_timeout(2500)
    cards = page.locator("#oppList article")
    results["opportunities"] = {
        "overflow": page_overflow(page),
        "cards": cards.count(),
        "wideCards": sum(1 for i in range(cards.count()) if (cards.nth(i).bounding_box() or {"width": 0})["width"] > 390),
        "offenders": offenders(page),
        "touch": touch_audit(page),
        "subTabs": {},
    }
    page.screenshot(path="tests/playwright/mobile_opportunities.png")

    for tier in ("clients", "matching", "delta", "history"):
        results["opportunities"]["subTabs"][tier] = opp_subtab_check(page, tier)
        results["opportunities"]["subTabs"][tier]["touch"] = touch_audit(page)
    # العودة لتبويب «الأفضل» لبقية الفحص
    page.locator(".opp-tab[data-tier=\"best\"]").click()
    page.wait_for_timeout(1500)

    # ── 3) لوحة السوق: الجداول وبطاقات الأرقام ──
    tab_click(page, 2)
    page.wait_for_timeout(2000)
    results["board"] = {
        "overflow": page_overflow(page),
        "metricCards": page.locator("#boardMetricCards .board-metric-card").count(),
        "govRows": page.locator("#governorateTableBody tr").count(),
        "tableScrollsInternally": page.evaluate("!!document.querySelector('.table-scroll') && document.querySelector('.table-scroll').scrollWidth > document.querySelector('.table-scroll').clientWidth"),
        "companionAds": page.locator("#boardCompanionAds article").count(),
        "offenders": offenders(page),
        "touch": touch_audit(page),
    }
    page.screenshot(path="tests/playwright/mobile_board.png")

    # ── 4) تحليلات السوق ──
    tab_click(page, 3)
    page.wait_for_timeout(2000)
    results["insights"] = {
        "overflow": page_overflow(page),
        "insightCards": page.locator(".insight-card").count(),
        "govChips": page.locator(".insights-govs .filter-chip").count(),
        # بدون بيانات (CI بلا Supabase) تعرض الواجهة الحالة الفارغة بدل «جاري التحميل»
        "panelLoaded": page.evaluate("!document.querySelector('#insightsRoot').innerText.includes('جاري التحميل')"),
        "offenders": offenders(page),
        "touch": touch_audit(page),
    }
    page.screenshot(path="tests/playwright/mobile_insights.png")

    # ── 5) التطورات (وكيل الاكتشاف اليومي) ──
    tab_click(page, 4)
    page.wait_for_timeout(2000)
    results["developments"] = {
        "overflow": page_overflow(page),
        "cards": page.locator(".development-card").count(),
        "agentStateShown": page.locator("#developmentsAgentState").count(),
        "offenders": offenders(page),
        "touch": touch_audit(page),
    }
    page.screenshot(path="tests/playwright/mobile_developments.png")

    # ── 6) المصادر والتشغيل ──
    tab_click(page, 5)
    page.wait_for_timeout(2000)
    results["sources"] = {
        "overflow": page_overflow(page),
        "opsCards": page.locator(".ops-card").count(),
        "sourceStatusShown": page.locator("#sourceSummaryBar, #dailyAgentStateInline").count(),
        "offenders": offenders(page),
        "touch": touch_audit(page),
    }
    page.screenshot(path="tests/playwright/mobile_sources.png")

    browser.close()

results["consoleErrors"] = errors[:10]
print(json.dumps(results, ensure_ascii=False, indent=2))

sub = results["opportunities"]["subTabs"]
failed = (
    any(results[s]["overflow"] or results[s]["offenders"] or results[s]["touch"] for s in ("search", "opportunities", "board", "insights", "developments", "sources"))
    or any(sub[t]["overflow"] or sub[t]["offenders"] or sub[t]["contentLen"] == 0 or sub[t]["touch"] for t in sub)
    or results["search"]["resultCards"] == 0
    or results["opportunities"]["cards"] == 0
    or not results["insights"]["panelLoaded"]
    or errors
)
sys.exit(1 if failed else 0)
