"""تشغيل فحص الأداء كأمر واحد — للاستخدام المحلي وفي CI.

الاستخدام:
    python scripts/run_performance_checks.py

السلوك:
- إن كان خادم صحي يعمل على المنفذ 8000 (أو ALFORAIJ_ASSISTANT_PORT) يُعاد
  استخدامه ولا يُوقف عند النهاية.
- وإلا يشغّل «python -m backend.main» على نفس المنفذ، وينتظر جاهزية
  /api/health (حتى 90 ثانية)، ثم يوقفه بعد انتهاء الفحوص.
- يشغّل فاحص الأداء tests/playwright/performance_audit.py الذي يفتح تبويبي
  «لوحة السوق» و«تحليلات السوق» بالبارد والدافئ ويقيس زمن كل نقطة API وفحص
  كاش TTL. الحدود: بارد ≤8 ثوانٍ، دافئ ≤2 ثانية.
- يخرج برمز غير صفري عند أي فشل حتى يرتد الخطأ في CI.

ملاحظة CI: بدون مفاتيح Supabase يعمل الخادم في وضع السقوط (لا بيانات خارجية)،
فيبقى الفحص حارسًا هيكليًا للواجهة والكاش؛ مع مفاتيح Supabase يقيس الأزمنة
الحقيقية للجلب البارد — التشغيل الفعلي الكامل عبر workflow_dispatch.

متطلبات: playwright مثبت + متصفح chromium منصّب
    pip install playwright && playwright install chromium
"""
from __future__ import annotations

import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PORT = int(os.getenv("ALFORAIJ_ASSISTANT_PORT", "8000"))
BASE = f"http://127.0.0.1:{PORT}/"
CHECKS = ["tests/playwright/performance_audit.py"]


def _healthy(timeout: float = 15.0) -> bool:
    """فحص الصحة — مهلة 15 ثانية لاستيعاب أول فحص للقاعدة (كاش health بعدها)."""
    try:
        with urllib.request.urlopen(f"{BASE}api/health", timeout=timeout) as resp:
            return resp.status == 200
    except Exception:
        return False


def main() -> int:
    os.chdir(ROOT)

    try:
        import playwright  # noqa: F401
    except ImportError:
        print("[perf-check] playwright غير مثبت. شغّل:")
        print("    pip install playwright && playwright install chromium")
        return 2

    proc: subprocess.Popen | None = None
    started = False

    # عدة محاولات قبل الاستنتاج بعدم وجود خادم (الفحص الأول للقاعدة بطيء)
    for attempt in range(4):
        if _healthy(timeout=25):
            print("[perf-check] خادم موجود على المنفذ — أُعيد استخدامه (لن يُوقف).")
            break
        if attempt == 3:
            print("[perf-check] لا خادم — أشغّل خادمًا مؤقتًا...")
            env = dict(os.environ)
            env.setdefault("PYTHONIOENCODING", "utf-8")
            proc = subprocess.Popen(
                [sys.executable, "-m", "backend.main"],
                cwd=ROOT,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            started = True
            deadline = time.time() + 90
            while time.time() < deadline:
                if _healthy(timeout=5):
                    break
                time.sleep(1)
            if not _healthy(timeout=5):
                print("[perf-check] الخادم المؤقت لم يجهز خلال 90 ثانية — أتوقف.")
                proc.terminate()
                return 3
            print("[perf-check] الخادم المؤقت جاهز.")
            break
        time.sleep(2)

    exit_code = 0
    try:
        for check in CHECKS:
            print(f"[perf-check] أشغّل {check} ...")
            result = subprocess.run(
                [sys.executable, check],
                cwd=ROOT,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            if result.returncode != 0:
                exit_code = result.returncode
    finally:
        if started and proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()

    print("[perf-check] النتيجة:", "ناجحة" if exit_code == 0 else f"فشل (رمز {exit_code})")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
