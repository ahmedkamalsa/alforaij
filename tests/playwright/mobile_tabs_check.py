"""فحص سريع لتبويبات الموقع على شاشة جوال (عرض 390px).

- هل التبويبات الستة ظاهرة وقابلة للنقر؟
- هل كل تبويب يظهر قسمه الصحيح؟
- هل يوجد تجاوز أفقي (horizontal scroll)؟
- حجم أهداف اللمس (ارتفاع الأزرار).

القائمة الحالية: search / opportunities / board / insights / developments / why-free.
"""
from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("ALFORAIJ_MOBILE_BASE", "http://127.0.0.1:8000/")
VIEWPORT = {"width": 390, "height": 844}

errors: list[str] = []

with sync_playwright() as p:
    browser = p.chromium.launch()
    page = browser.new_page(viewport=VIEWPORT)
    page.on("console", lambda msg: errors.append(f"{msg.type}: {msg.text}") if msg.type == "error" else None)
    page.on("pageerror", lambda exc: errors.append(f"pageerror: {exc}"))
    page.goto(BASE, wait_until="load", timeout=60000)
    page.wait_for_selector(".main-tab", timeout=30000)
    page.wait_for_timeout(1500)

    tabs = page.locator(".main-tab")
    count = tabs.count()
    results = {"viewport": page.evaluate("window.innerWidth"), "tabCount": count}

    # 1) أبعاد التبويبات وأهداف اللمس
    box = tabs.nth(0).bounding_box()
    results["firstTabSize"] = {"w": round(box["width"]), "h": round(box["height"])} if box else None

    # 2) لا تجاوز أفقي
    results["horizontalOverflow"] = page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth")

    # 3) التنقل بين التبويبات الستة
    names = ["search", "opportunities", "board", "insights", "developments", "why-free"]
    panels = {}
    for i, name in enumerate(names):
        tabs.nth(i).click()
        page.wait_for_timeout(1200)
        visible = page.evaluate(
            "([...document.querySelectorAll('[data-main-panel].active')] || []).map(p => p.dataset.mainPanel)"
        )
        panels[name] = visible
        active_tab = page.evaluate("([...document.querySelectorAll('.main-tab.active')] || []).map(b => b.dataset.mainTab)")
        results[f"tab_{name}_active"] = active_tab
        results[f"tab_{name}_panels"] = visible

    # 4) لقطة للتبويب النشط (آخر التبويبات — التطورات)
    page.screenshot(path="tests/playwright/mobile_board_tab.png", full_page=False)

    # 5) أهداف اللمس: كل تبويب مرئي وارتفاعه >= 40px
    min_h = 999
    for i in range(count):
        b = tabs.nth(i).bounding_box()
        if b:
            min_h = min(min_h, b["height"])
    results["minTabHeightPx"] = round(min_h)

    # 6) فحص محتوى تبويب الفرص على الجوال (بعد العودة إليه)
    tabs.nth(1).click()
    page.wait_for_timeout(2000)
    results["oppCardsOnMobile"] = page.locator("#oppList article").count()

    browser.close()

results["consoleErrors"] = errors[:8]
print(json.dumps(results, ensure_ascii=False, indent=2))

# تبويب البحث يضم عدة أقسام متراصة تحمل نفس data-main-panel (شريط الأدوات،
# الشات، منطقة النتائج، لوحة النتائج) — نكشّف التكرار ونقارن المجموعة الفريدة.
ok = (
    results["tabCount"] == 6
    and not results["horizontalOverflow"]
    and results["minTabHeightPx"] >= 40
    and not errors
    and all(sorted(set(results[f"tab_{n}_panels"])) == [n] for n in names)
)
sys.exit(0 if ok else 1)
