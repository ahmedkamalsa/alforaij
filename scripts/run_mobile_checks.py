"""تشغيل فحوص الجوال كأمر واحد — للاستخدام المحلي وفي CI.

الاستخدام:
    python scripts/run_mobile_checks.py

السلوك:
- إن كان خادم صحي يعمل على المنفذ 8000 (أو ALFORAIJ_ASSISTANT_PORT) يُعاد
  استخدامه ولا يُوقف عند النهاية.
- وإلا يشغّل «python -m backend.main» على نفس المنفذ، وينتظر جاهزية
  /api/health (حتى 60 ثانية)، ثم يوقفه بعد انتهاء الفحوص.
- يشغّل فحوص Playwright في tests/playwright/:
    mobile_tabs_check.py  — التنقل بين التبويبات وأهداف اللمس
    mobile_full_check.py  — كل الأقسام (بحث/فرص/لوحة/مصادر) بعرض 390px
- يخرج برمز غير صفري عند أي فشل حتى يرتد الخطأ في CI.

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
CHECKS = [
    "tests/playwright/mobile_tabs_check.py",
    "tests/playwright/mobile_full_check.py",
]


def _healthy(timeout: float = 10.0) -> bool:
    """فحص الصحة — المهلة 10 ثوانٍ لأن /api/health يستطلع المصادر الرسمية
    (check_official_reference_sources) فيستغرق عدة ثوانٍ."""
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
        print("[mobile-check] playwright غير مثبت. شغّل:")
        print("    pip install playwright && playwright install chromium")
        return 2

    proc: subprocess.Popen | None = None
    started = False

    # عدة محاولات قبل الاستنتاج بعدم وجود خادم (الفحص بطيء أحيانًا)
    if any(_healthy() for _ in range(3)):
        print(f"[mobile-check] خادم صحي قائم على {BASE} — يُعاد استخدامه (لن يُوقف).")
    else:
        print(f"[mobile-check] لا خادم على {BASE} — أشغّل python -m backend.main …")
        env = dict(os.environ)
        env.setdefault("ALFORAIJ_ASSISTANT_PORT", str(PORT))
        env.setdefault("ALFORAIJ_LOG_LEVEL", "WARNING")
        proc = subprocess.Popen(
            [sys.executable, "-m", "backend.main"],
            cwd=ROOT,
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        started = True
        deadline = time.time() + 60
        while time.time() < deadline:
            if _healthy():
                break
            if proc.poll() is not None:
                print(f"[mobile-check] الخادم توقف مبكرًا برمز {proc.returncode}.")
                return 1
            time.sleep(1)
        else:
            print("[mobile-check] الخادم لم يصل للجاهزية خلال 60 ثانية.")
            proc.terminate()
            return 1
        print("[mobile-check] الخادم جاهز.")

    failures: list[str] = []
    env = dict(os.environ)
    env.setdefault("ALFORAIJ_MOBILE_BASE", BASE)
    for check in CHECKS:
        print(f"\n[mobile-check] تشغيل {check} …")
        res = subprocess.run([sys.executable, check], cwd=ROOT, env=env)
        status = "ناجح ✅" if res.returncode == 0 else f"فشل ❌ (رمز {res.returncode})"
        print(f"[mobile-check] {status}")
        if res.returncode != 0:
            failures.append(check)

    if started and proc is not None:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        print("[mobile-check] أوقفت الخادم الذي شغّلته.")

    if failures:
        print(f"\n[mobile-check] فشل {len(failures)} فحص: {failures}")
        return 1
    print("\n[mobile-check] كل فحوص الجوال ناجحة ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
