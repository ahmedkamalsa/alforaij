"""فحص أداء آلي شامل: أول تحميل للصفحة + فتح كل التبويبات الخمسة (بارد/دافئ).

يقيس من منظور المستخدم الحقيقي عبر Playwright:
- زمن أول تحميل للصفحة حتى ظهور مركز البحث
- زمن فتح كل تبويب من الخمسة (البحث/الفرص/اللوحة/التحليلات/التطورات)
  من النقر حتى ظهور المحتوى الفعلي، مرتين: بارد (أول فتح في الجلسة) ودافئ (إعادة فتح)
- أوقات نقاط API الفردية وعدد الطلبات وفحص كاش TTL
- يرفض أي تبويب يتجاوز حدّي: البارد > 8 ثوانٍ أو الدافئ > 2 ثانية

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
PAGE_LOAD_LIMIT_MS = 5000

# كل تبويب ومحدد «المحتوى ظهر فعلًا» (يقبل الحالة الفارغة المشروعة كاكتمال)
TABS = [
    ("search", "#chatInput", "البحث والتقييم"),
    ("opportunities", "#oppList .result-card, #oppList .empty, #oppList > .results > .empty", "أفضل الفرص"),
    ("board", "#boardMatchingLink .matching-nav-card", "لوحة السوق"),
    ("insights", "#insightsRoot .kpi-card, #insightsRoot .empty", "تحليلات السوق"),
    ("developments", "#developmentsRoot .development-card, #developmentsRoot .empty", "التطورات"),
]

results: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append({"name": name, "ok": bool(ok), "detail": detail})
    print(("✅" if ok else "❌"), name, detail)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        errors: list[str] = []
        # نتجاهل أخطاء الشبكة البسيطة (ERR_EMPTY_RESPONSE) التي تحدث لموارد اختيارية
        # مثل service worker أو favicon أثناء التحميل البارد في CI
        def _on_console(m):
            if m.type == "error" and "ERR_EMPTY_RESPONSE" not in m.text:
                errors.append(m.text)
        page.on("console", _on_console)
        page.on("pageerror", lambda e: errors.append(str(e)))

        api_times: dict[str, list[float]] = {}
        api_starts: dict[str, float] = {}

        def on_request(req):
            if "/api/" in req.url:
                api_starts[req.url] = time.perf_counter()

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

        # 1) أول تحميل للصفحة (البحث هو التبويب الافتراضي)
        t0 = time.perf_counter()
        page.goto(BASE, wait_until="domcontentloaded")
        page.wait_for_selector("#chatInput", timeout=PAGE_LOAD_LIMIT_MS)
        page_load_ms = (time.perf_counter() - t0) * 1000
        check(f"أول تحميل للصفحة ({page_load_ms:.0f} ms)", page_load_ms < PAGE_LOAD_LIMIT_MS, f"حد {PAGE_LOAD_LIMIT_MS} ms")

        # 2) فتح كل تبويب مرتين: بارد ثم دافئ
        for tab_name, selector, label in TABS:
            # بارد: أول فتح في هذه الجلسة
            t0 = time.perf_counter()
            page.click(f'button[data-main-tab="{tab_name}"]')
            try:
                page.wait_for_selector(selector, timeout=COLD_LIMIT_MS)
                cold_ms = (time.perf_counter() - t0) * 1000
                check(f"{label} — فتح بارد ({cold_ms:.0f} ms)", cold_ms < COLD_LIMIT_MS, f"حد {COLD_LIMIT_MS} ms")
            except Exception as exc:
                cold_ms = -1
                check(f"{label} — فتح بارد", False, f"انتهت المهلة/خطأ: {str(exc)[:120]}")

            # دافئ: إعادة فتح فورًا بعد أن اكتمل أول مرة
            t0 = time.perf_counter()
            page.click(f'button[data-main-tab="{tab_name}"]')
            try:
                page.wait_for_selector(selector, timeout=WARM_LIMIT_MS)
                warm_ms = (time.perf_counter() - t0) * 1000
                check(f"{label} — إعادة فتح دافئ ({warm_ms:.0f} ms)", warm_ms < WARM_LIMIT_MS, f"حد {WARM_LIMIT_MS} ms")
            except Exception as exc:
                check(f"{label} — إعادة فتح دافئ", False, f"انتهت المهلة/خطأ: {str(exc)[:120]}")

        # 3) أوقات نقاط API الفردية (أسوأ تكرار) + فحص كاش TTL للنقاط المخزنة
        for path, times in sorted(api_times.items()):
            worst = max(times) if times else 0
            check(f"API {path}: أسوأ {worst:.0f} ms (عدد الطلبات {len(times)})", worst < COLD_API_LIMIT_MS, f"حد {COLD_API_LIMIT_MS} ms")
            if path in ("/api/dashboard/summary", "/api/market-insights", "/api/price-trends", "/api/health") and len(times) >= 2:
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
