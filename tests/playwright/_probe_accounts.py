"""فحص تدفق الحساب المجاني: تسجيل → حفظ بحث → نجاة reload → محفظة → جرس → حذف.

يعمل على الخادم المحلي (افتراضي) أو الموقع المنشور (عبر ALFORAIJ_MOBILE_BASE).
صفر أخطاء كونسول شرط النجاح (درس فحص الجوال).
"""
from __future__ import annotations

import json
import os
import random
import sys

from playwright.sync_api import sync_playwright

BASE = os.getenv("ALFORAIJ_MOBILE_BASE", "http://127.0.0.1:8000/")


def _service_role() -> tuple[str, str]:
    """قراءة (url, service_role) من .env المحلي — لإدراج تنبيه تجريبي للجرس."""
    env = {}
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    for line in open(os.path.join(root, ".env"), encoding="utf-8"):
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env.get("SUPABASE_URL", "").rstrip("/"), env.get("SUPABASE_SERVICE_ROLE_KEY", "")


def _sr_request(method: str, path: str, payload: dict | None = None) -> None:
    """نداء service role (إدراج/حذف) — يُبتلع أي فشل."""
    import urllib.request

    url, key = _service_role()
    if not url or not key:
        return
    req = urllib.request.Request(
        f"{url}/rest/v1{path}",
        method=method,
        data=json.dumps(payload).encode() if payload else None,
        headers={
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            r.read()
    except Exception:
        pass


def _insert_test_alert(secret: str) -> None:
    """إدراج تنبيه تجريبي في user_alerts عبر service role (لاختبار الجرس)."""
    _sr_request(
        "POST",
        "/user_alerts?on_conflict=user_secret,opportunity_code",
        [
            {
                "user_secret": secret,
                "opportunity_code": "TEST-ALERT-1",
                "area": "السالمية",
                "price": 280000,
                "change": "new",
                "message": "فرصة جديدة مطابقة لبحثك المحفوظ: بيت في السالمية بسعر 280,000 د.ك.",
                "url": "https://example.com/TEST-ALERT-1",
            }
        ],
    )


def _cleanup_test_user(secret: str) -> None:
    """حذف بيانات المستخدم التجريبي (تنبيهات/أبحاث/محفظة/مستخدم) بعد انتهاء الفحص."""
    if not secret:
        return
    _sr_request("DELETE", f"/user_alerts?user_secret=eq.{secret}")
    _sr_request("DELETE", f"/saved_searches?user_secret=eq.{secret}")
    _sr_request("DELETE", f"/portfolios?user_secret=eq.{secret}")
    _sr_request("DELETE", f"/users?secret=eq.{secret}")
# رقم اختبار عشوائي كل تشغيل: التسجيل محدد بنافذة 15 دقيقة بين إعادة الإرسال،
# والرقم المتكرر يُرجع 400 rate_limited (سلوك صحيح لكنه يلوّث الكونسول)
PHONE = os.getenv("ACCOUNT_TEST_PHONE", "5" + "".join(random.choices("0123456789", k=7)))


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

        # 1) زر الحفظ بلا حساب يفتح نافذة «حسابي»
        page.click("#saveSearchBtn")
        page.wait_for_timeout(300)
        if not page.locator("#accountModal").is_visible():
            failures.append("نافذة الحساب لم تُفتح عند حفظ البحث بلا حساب")

        # 2) إرسال الرمز — مع انتظار دوري (استجابة RPC قد تتأخر أحيانًا)
        page.fill("#accountPhone", PHONE)
        page.click("#accountSendOtp")
        code = ""
        for _ in range(30):
            page.wait_for_timeout(300)
            otp_note = page.locator("#accountOtpNote").inner_text()
            for part in otp_note.split():
                if part.isdigit() and len(part) == 6:
                    code = part
                    break
            if code:
                break
        if not code:
            failures.append(f"لم يظهر رمز من 6 أرقام في الملاحظة: {otp_note[:80]}")
            page.screenshot(path="tests/playwright/_account_debug.png")
            browser.close()
            print(json.dumps({"failures": failures, "console": console_errors[:3]}, ensure_ascii=False, indent=2))
            return 1

        # 3) التحقق
        page.fill("#accountOtpCode", code)
        page.click("#accountVerifyBtn")
        page.wait_for_timeout(800)
        status = page.locator("#accountStatus").inner_text()
        if "مسجّل" not in status:
            failures.append(f"حالة التسجيل غير متوقعة: {status[:80]}")
        # النافذة تبقى مفتوحة لعرض حالة التسجيل — يُغلقها المستخدم يدويًا
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)
        if page.locator("#accountModal").is_visible():
            failures.append("النافذة لم تُغلق بزر Escape")

        # 4) حفظ بحث (بعد كتابة نص بحث في الشات)
        page.fill("#chatInput", "بيت 400م في السالمية ميزانية 300 ألف")
        page.click("#saveSearchBtn")
        page.wait_for_timeout(800)
        msg = page.locator("#saveSearchMsg").inner_text()
        if "تم الحفظ" not in msg:
            failures.append(f"رسالة الحفظ غير متوقعة: {msg[:80]}")

        # 5) قائمة الأبحاث المحفوظة
        page.click("#savedSearchesToggle")
        page.wait_for_timeout(500)
        box = page.locator("#savedSearchesBox")
        if box.is_visible() and "السالمية" not in box.inner_text():
            failures.append("البحث المحفوظ غير ظاهر في القائمة")

        # 6) نجاة من reload: المستخدم + البحث باقيان
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(400)
        page.click("#savedSearchesToggle")
        page.wait_for_timeout(500)
        if not page.locator("#savedSearchesBox").is_visible():
            failures.append("صندوق الأبحاث غير ظاهر بعد reload")
        elif "السالمية" not in page.locator("#savedSearchesBox").inner_text():
            failures.append("البحث المحفوظ لم ينجُ من reload")

        # 7) تبديل التنبيه ثم حذف (تنظيف)
        page.locator("#savedSearchesBox input[data-alert]").first.check()
        page.wait_for_timeout(500)
        page.locator("#savedSearchesBox button[data-del]").first.click()
        page.wait_for_timeout(600)
        box_text = page.locator("#savedSearchesBox").inner_text()
        if "لا أبحاث محفوظة" not in box_text:
            failures.append(f"الحذف لم ينعكس في القائمة: {box_text[:80]}")

        # 8) المحفظة: إضافة عقار → بطاقة بالقيمة التقديرية → حذف (تنظيف)
        page.click("#accountBtn")
        page.wait_for_timeout(400)
        if not page.locator("#portfolioWrap").is_visible():
            failures.append("قسم المحفظة غير ظاهر للمستخدم المسجّل")
        page.fill("#pfArea", "السالمية")
        page.select_option("#pfType", "شقة")
        page.fill("#pfSpace", "200")
        page.fill("#pfPrice", "200000")
        page.fill("#pfRent", "900")
        page.fill("#pfDate", "2026-01")
        page.click("#portfolioForm button[type='submit']")
        # انتظار دوري: تقييم المحفظة يجلب price-trends/التوقعات
        portfolio_ok = False
        for _ in range(25):
            page.wait_for_timeout(300)
            pf_list = page.locator("#portfolioList")
            if pf_list.is_visible() and "السالمية" in pf_list.inner_text() and "القيمة التقديرية الحالية" in pf_list.inner_text():
                portfolio_ok = True
                break
        if not portfolio_ok:
            failures.append("بطاقة المحفظة لم تُعرض بالقيمة التقديرية")
        # حذف العقار من المحفظة (تنظيف)
        page.locator("#portfolioList button[data-pf-del]").first.click()
        page.wait_for_timeout(700)
        pf_text = page.locator("#portfolioList").inner_text()
        if "لا عقارات بعد" not in pf_text:
            failures.append(f"حذف المحفظة لم ينعكس: {pf_text[:80]}")
        page.keyboard.press("Escape")
        page.wait_for_timeout(200)

        # 9) الجرس: تنبيه تجريبي (service role) → عدّاد → قائمة → «تم»
        secret = page.evaluate("localStorage.getItem('alforaij_secret') || ''")
        if not secret:
            failures.append("لا يوجد سرّ مستخدم في localStorage بعد التسجيل")
        else:
            _insert_test_alert(secret)
            page.reload(wait_until="networkidle")
            page.wait_for_timeout(700)
            count_text = page.locator("#bellCount").inner_text()
            if count_text != "1":
                failures.append(f"عدّاد الجرس غير متوقع: {count_text!r}")
            page.click("#bellToggle")
            page.wait_for_timeout(400)
            if "بيت في السالمية" not in page.locator("#bellDropdown").inner_text():
                failures.append("التنبيه غير ظاهر في قائمة الجرس")
            page.click("#bellMarkAll")
            page.wait_for_timeout(500)
            if not page.locator("#bellCount").is_hidden():
                failures.append("عدّاد الجرس لم يختفِ بعد «تم»")

        # 10) تسجيل الخروج (تنظيف): فتح النافذة عبر زر «حسابي» (منظر المستخدم المسجّل)
        page.click("#accountBtn")
        page.wait_for_timeout(300)
        page.click("#accountLogoutBtn")
        page.wait_for_timeout(200)
        # حذف المستخدم التجريبي من القاعدة (منع تراكم أرقام الاختبار)
        secret = page.evaluate("localStorage.getItem('alforaij_secret') || ''")
        _cleanup_test_user(secret)

        # جوال 390px: النافذة بلا تجاوز أفقي
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(200)
        overflow = page.evaluate(
            "document.documentElement.scrollWidth > document.documentElement.clientWidth"
        )
        if overflow:
            failures.append("تجاوز أفقي على 390px")

        browser.close()

    if console_errors:
        failures.append(f"أخطاء كونسول: {console_errors[:3]}")
    if failed_requests:
        failures.append(f"طلبات فاشلة: {failed_requests[:3]}")

    print(json.dumps({"failures": failures}, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
