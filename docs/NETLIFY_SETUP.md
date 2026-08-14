# تفعيل نشر Netlify لمنصة الفريج — دليل خطوة بخطوة

## ماذا سيُنشر؟

عند اكتمال الإعداد، كل دفع إلى `main` في مستودع البحث يرفع **الواجهة الحقيقية** (`frontend/`) تلقائيًا إلى:

```
https://alforaijboard.netlify.app/
```

- نفس المحتوى الثابت الموجود على GitHub Pages واللوحة — مطابق تمامًا.
- النشر يتم عبر عمل `deploy-static.yml` (خطوة `netlify`) ويشمل **فحصًا آليًا**: بعد الرفع يتحقق أن الرابط الحي يعيد HTTP 200.
- جدول يومي (04:00 UTC) يحدّث اللقطة تلقائيًا بعد حصاد البيانات.

> ⚠️ **لا تربط Netlify بمستودع `alforaijboard`** — نسخته القديمة (`site/`) غير حية وتتعارض مع الواجهة الحقيقية. النشر الصحيح يكون من **مستودع البحث** عبر GitHub Actions.

---

## خطوة 1 — إنشاء موقع Netlify (مرة واحدة)

1. ادخل إلى [app.netlify.com](https://app.netlify.com) بحسابك.
2. **Add new site** ← **Deploy manually** (موقع فارغ — لا تربط مستودعًا؛ GitHub Actions سيرفع الملفات مباشرة).
3. عيّن اسم الموقع: `alforaijboard` (حتى يصبح الرابط `alforaijboard.netlify.app`).
4. لا تحتاج لملفات الآن — الإعداد يكتمل من الخطوة التالية.

بديل عبر CLI:
```bash
npx netlify-cli sites:create --name alforaijboard
```

---

## خطوة 2 — الحصول على `NETLIFY_AUTH_TOKEN`

1. [app.netlify.com](https://app.netlify.com) ← أيقونة الملف الشخصي ← **User settings**.
2. **Applications** ← **Personal access tokens** ← **New access token**.
3. سمّه بوضوح (مثل: `alforaij-gh-actions`) واختر نطاقه المناسب.
4. **انسخ القيمة فورًا** (تظهر مرة واحدة فقط وتبدأ بـ `nf_`).

---

## خطوة 3 — الحصول على `NETLIFY_SITE_ID`

من الموقع الذي أنشأته في خطوة 1:

- **Site configuration** ← **Site details** ← **API ID** (معرّف طويل).

أو عبر CLI:
```bash
npx netlify-cli sites:list
```
(عمود **Site ID** — وليس اسم الموقع.)

---

## خطوة 4 — إضافة الأسرار في إعدادات GitHub

1. افتح [github.com/ahmedkamalsa/alforaij](https://github.com/ahmedkamalsa/alforaij).
2. **Settings** ← **Secrets and variables** ← **Actions** ← **New repository secret**.
3. أضف سرّين بالاسمين **الحرفيين** التاليين:

| اسم السر | القيمة |
|---|---|
| `NETLIFY_AUTH_TOKEN` | التوكن من خطوة 2 |
| `NETLIFY_SITE_ID` | المعرف من خطوة 3 |

---

## خطوة 5 — التحقق (اختبار تلقائي)

1. ادفع أي تغيير إلى `main` — أو من تبويب **Actions** شغّل `deploy-static.yml` يدويًا.
2. افتح تشغيل العمل ← خطوة **Deploy to Netlify (with live verification)**.
3. النجاح يظهر هكذا:
   ```
   Netlify live at: https://alforaijboard.netlify.app/
   Verification HTTP: 200
   ✅ Netlify deploy verified (HTTP 200)
   ```
4. افتح الرابط وتأكد أن المنصة تعمل.

> النتيجة: من الآن كل دفع وكل حصاد يومي يرفع اللوحة إلى Netlify تلقائيًا مع فحص سلامة، دون أي خطوة يدوية.

---

## استكشاف الأخطاء

| الرسالة في الخطوة | السبب | الحل |
|---|---|---|
| `Netlify deploy is not configured` | الأسرار غير مضافة أو الاسم غير مطابق | أعد خطوة 4 بحذف/إعادة إضافة السرين |
| `Invalid token` | التوكن خاطئ/منتهي | أنشئ توكنًا جديدًا في خطوة 2 |
| `Site not found` | `NETLIFY_SITE_ID` غير صحيح | أعد نسخه من خطوة 3 |
| `Verification HTTP: <غير 200>` | الموقع لم يكتمل بعد | انتظر دقيقة وأعد تشغيل العمل، أو راجع إعدادات الموقع |

## ملاحظات أمان

- الأسرار **لا توضع أبدًا** في ملفات داخل المشروع.
- `frontend/config.js` يُضبط تلقائيًا أثناء النشر — لا تعدّله يدويًا بأسرار.
- الواجهة الثابتة تعمل من لقطة بيانات؛ لتشغيلها بالبيانات الحية عدّل المتغير `ALFORAIJ_API_BASE` (Settings ← Secrets and variables ← Actions ← Variables).
