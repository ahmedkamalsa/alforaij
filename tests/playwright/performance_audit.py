"""فحص أداء آلي لتبويبي «لوحة السوق» و«تحليلات السوق».

يقيس من منظور المستخدم الحقيقي عبر Playwright:
- زمن فتح كل تبويب (من النقر حتى اكتمال المحتوى الفعلي)
- المرة الأولى (بارد — يملأ كاش الخادم) مقابل الثانية (دافئ — من الكاش)
- أوقات نقاط API الفردية وعدد الطلبات
- يرفض أي تبويب يتجاوز حدّي: الفتح البارد > 8 ثوانٍ أو الدافئ > 2 ثانية

الاستخدام (والخادم يعمل على 8000):
    PYTHONIOENCODING=utf-8 python tests/playwright/performance_audit.py
"""
import json
import sys
import time

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000/"
COLD_LIMIT_MS = 8000
WARM_LIMIT_MS = 2000
COLD_API_LIMIT_MS = 6000

results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"name": name, "ok": bool(ok), "detail": detail})
    print(("✅" if ok else "❌"), name, detail)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))

        api_times: dict[str, list[float]] = {}
        api_starts: dict[str, float] = {}

        def on_request(req):
            url = req.url
            if "/api/" not in url:
                return
            api_starts[url] = time.perf_counter()

        def on_response(resp):
            url = resp.url
            if "/api/" not in url:
                return
            started = api_starts.pop(url, None)
            if started is None:
                return
            path = "/" + url.split("?")[0].replace(BASE, "").lstrip("/")
            api_times.setdefault(path, []).append((time.perf_counter() - started) * 1000)

        page.on("request", on_request)
        page.on("response", on_response)

        # 1) تحميل الصفحة الأول
        t0 = time.perf_counter()
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector("#chatInput", timeout=15000)
        page_load_ms = (time.perf_counter() - t0) * 1000
        check(f"تحميل الصفحة الأولي ({page_load_ms:.0f} ms)", page_load_ms < 5000, "حد 5 ثوانٍ")

        # 2) فتح اللوحة — بارد (يملأ كاش الخادم)
        t0 = time.perf_counter()
        page.click('button[data-main-tab="board"]')
        page.wait_for_selector("#boardMatchingLink .matching-nav-card", timeout=COLD_LIMIT_MS)
        page.wait_for_function(
            "document.querySelectorAll('#boardStats .board-stat').length > 0 || document.querySelector('#governorateTableBody tr')",
            timeout=COLD_LIMIT_MS,
        )
        board_cold_ms = (time.perf_counter() - t0) * 1000
        check(f"لوحة السوق — فتح بارد ({board_cold_ms:.0f} ms)", board_cold_ms < COLD_LIMIT_MS, f"حد {COLD_LIMIT_MS} ms")

        # 3) فتح التحليلات — بارد
        t0 = time.perf_counter()
        page.click('button[data-main-tab="insights"]')
        page.wait_for_selector("#insightsRoot .kpi-card", timeout=COLD_LIMIT_MS)
        insights_cold_ms = (time.perf_counter() - t0) * 1000
        check(f"تحليلات السوق — فتح بارد ({insights_cold_ms:.0f} ms)", insights_cold_ms < COLD_LIMIT_MS, f"حد {COLD_LIMIT_MS} ms")

        # 4) إعادة فتح اللوحة — دافئ (من كاش الخادم)
        page.click('button[data-main-tab="board"]')
        t0 = time.perf_counter()
        page.wait_for_selector("#boardMatchingLink .matching-nav-card", timeout=WARM_LIMIT_MS)
        board_warm_ms = (time.perf_counter() - t0) * 1000
        check(f"لوحة السوق — إعادة فتح دافئ ({board_warm_ms:.0f} ms)", board_warm_ms < WARM_LIMIT_MS, f"حد {WARM_LIMIT_MS} ms")

        # 5) إعادة فتح التحليلات — دافئ
        page.click('button[data-main-tab="insights"]')
        t0 = time.perf_counter()
        page.wait_for_selector("#insightsRoot .kpi-card", timeout=WARM_LIMIT_MS)
        insights_warm_ms = (time.perf_counter() - t0) * 1000
        check(f"تحليلات السوق — إعادة فتح دافئ ({insights_warm_ms:.0f} ms)", insights_warm_ms < WARM_LIMIT_MS, f"حد {WARM_LIMIT_MS} ms")

        # 6) أوقات نقاط API الفردية (أسوأ تكرار)
        slow_api = []
        for path, times in sorted(api_times.items()):
            worst = max(times) if times else 0
            label = f"API {path}: أسوأ {worst:.0f} ms (عدد الطلبات {len(times)})"
            ok = worst < COLD_API_LIMIT_MS
            check(label, ok, f"حد {COLD_API_LIMIT_MS} ms")
            if not ok:
                slow_api.append(path)
            # فقط النقاط التي عليها كاش TTL يُفترض أن يصبح طلبها الثاني أسرع بكثير
            if path in ("/api/dashboard/summary", "/api/market-insights", "/api/price-trends") and len(times) >= 2:
                first, second = times[0], times[1]
                improved = second < first * 0.5
                check(f"كاش {path}: {first:.0f}→{second:.0f} ms", improved, "الطلب الثاني يجب أن يكون أسرع من نصف الأول")

        check("لا أخطاء كونسول", len(errors) == 0, f"errors={errors[:3]}")
        browser.close()

    fails = [r for r in results if not r["ok"]]
    print(json.dumps({"total": len(results), "passed": len(results) - len(fails), "failed": len(fails)}, ensure_ascii=False))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
