"""فحص حي لنقاط API بأسلوب TestSprint: الحالة، البنية، البيانات الفعلية.

يستدعي كل نقطة GET/POST ويتبين:
- رمز الحالة 200.
- استجابة JSON صالحة.
- حقول أساسية غير فارغة (عند توقعها).
- سرعة استجابة معقولة.

الخروج: 0 عند النجاح، 1 عند وجود أخطاء.
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
CHECKS: list[dict] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    CHECKS.append({"name": name, "ok": ok, "detail": detail})
    print(f"{'✅' if ok else '❌'} {name}" + (f" — {detail}" if detail else ""))


def get(path: str, timeout: float = 40.0):
    t0 = time.time()
    req = urllib.request.Request(BASE + path, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
        return resp.status, json.loads(body) if body.strip() else {}, time.time() - t0


def post(path: str, payload: dict, timeout: float = 40.0):
    t0 = time.time()
    req = urllib.request.Request(
        BASE + path, data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", "replace")
        return resp.status, json.loads(body) if body.strip() else {}, time.time() - t0


def main() -> int:
    # GET endpoints
    g = [
        ("/api/health", lambda d: d.get("status") in ("ok", "healthy") or "ok" in str(d)),
        ("/api/sources", lambda d: isinstance(d, dict) and len(d.get("sources", [])) >= 3),
        ("/api/search-options", lambda d: isinstance(d, dict) and len(d) >= 1),
        ("/api/market-analytics", lambda d: isinstance(d, dict) and len(d) >= 1),
        ("/api/market-insights", lambda d: isinstance(d, dict) and len(d) >= 1),
        ("/api/dashboard/summary", lambda d: d.get("count", 0) > 0 and len(d.get("records", [])) > 0),
        ("/api/developments", lambda d: isinstance(d, dict) and len(d.get("developments", [])) >= 1),
        ("/api/daily-agent/status", lambda d: isinstance(d, dict) and "status" in d and d.get("status") in ("success", "error", "running", "never")),
        ("/api/official-reference-sources", lambda d: isinstance(d, dict) and len(d.get("sources", [])) >= 4),
        ("/api/opportunities", lambda d: isinstance(d, dict) and bool(d.get("tiers"))),
        ("/api/price-trends", lambda d: isinstance(d, dict) or isinstance(d, list)),
    ]
    for path, validator in g:
        try:
            status, data, dur = get(path)
            ok = status == 200 and validator(data)
            check(f"GET {path}", ok, f"{status} في {dur:.1f}s" + ("" if ok else f" — {str(data)[:80]}"))
        except Exception as e:  # noqa: BLE001
            check(f"GET {path}", False, str(e)[:120])

    # POST /api/parse — فهم طلب نص حر
    try:
        status, data, dur = post("/api/parse", {"text": "بيت للبيع في الفردوس 300 متر"})
        req = data.get("request", {})
        ok = (status == 200 and isinstance(req, dict)
              and req.get("transaction") == "للبيع"
              and req.get("property_type") == "بيت"
              and "الفردوس" in req.get("areas", [])
              and req.get("min_area") == 300.0)
        check("POST /api/parse (فهم الطلب كاملًا)", ok, f"{status} في {dur:.1f}s — {json.dumps(req, ensure_ascii=False)[:100]}")
    except Exception as e:  # noqa: BLE001
        check("POST /api/parse", False, str(e)[:120])

    # POST /api/analyze — التحليل الكامل (قد يستغرق وقتًا)
    try:
        status, data, dur = post("/api/analyze", {"query": "بيت للبيع في الفردوس 300 متر", "source": "all"}, timeout=90)
        results = data.get("results", data.get("rankedResults", []))
        ok = status == 200 and isinstance(data, dict) and len(results) > 0
        check("POST /api/analyze (تحليل كامل)", ok, f"{status} في {dur:.0f}s — {len(results)} نتيجة")
    except Exception as e:  # noqa: BLE001
        check("POST /api/analyze", False, str(e)[:120])

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
