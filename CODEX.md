# CODEX.md — دليل شامل لمراجعة منصة الفريج العقارية

## 📋 نظرة عامة

منصة **الفريج** هي نظام متكامل للبحث والتقييم العقاري في الكويت، يعمل على:
- **Python 3.11** (Backend) — خادم HTTP مدمج بدون Flask/Django
- **Vanilla JS** (Frontend) — واجهة واحدة متكاملة (8800+ سطر)
- **Supabase** (Database) — PostgreSQL كخدمة
- **6 مصادر بيانات** — 3000+ إعلان عقاري

---

## 🗂️ هيكل المشروع

```
alforaij-research-assistant/
├── backend/
│   ├── main.py                 # نقطة الدخول — HTTP handler (2141 سطر)
│   ├── config.py               # إعدادات الخادم + Supabase
│   ├── models.py               # نماذج البيانات (Listing, PropertyRequest, RankedListing)
│   ├── connectors/             # جامعات البيانات من المصادر الخارجية
│   │   ├── alforaij.py         # بيانات الفريج المحلية
│   │   ├── live_sources.py     # OpenSooq, Mourjan, 4Sale, Q8Aqar (2726 سطر)
│   │   ├── official_data.py    # بيانات وزارة العدل الرسمية
│   │   ├── market_ads.py       # إعلانات السوق المباشرة
│   │   └── official_indicators.py  # المؤشرات الرسمية
│   └── services/               # خدمات العمل (40 ملف)
│       ├── request_parser.py   # تحليل الطلبات العربية
│       ├── matching.py         # مطابقة الإعلانات بالطلب
│       ├── valuation.py        # تقييم الأسعار المقارن (843 سطر)
│       ├── opportunities.py    # حساب فرص المكسب
│       ├── report_generator.py # بناء التقارير (704 سطر)
│       ├── ai_evaluator.py     # التحليل بالذكاء الاصطناعي
│       ├── ai_router.py        # توجيه الطلبات الذكية
│       ├── ai_rag.py           # RAG-powered search
│       ├── supabase_store.py   # قاعدة البيانات (1231 سطر)
│       ├── smart_alerts.py     # تنبيهات ذكية للسعر والفرص
│       ├── trust_score.py      # مؤشر ثقة الإعلان
│       ├── mortgage_calculator.py # حاسبة الرهن العقاري
│       ├── valuation.py        # التقييم المقارن + Confidence Intervals
│       ├── chat_agents.py      # المساعد العقاري
│       └── pdf_report.py       # تقارير PDF
├── frontend/
│   ├── index.html              # الصفحة الرئيسية (1026 سطر)
│   ├── app.js                  # المنطق البرمجي (8810 سطر)
│   ├── styles.css              # التصميم (9654 سطر)
│   ├── admin.html              # لوحة التحكم الإدارية
│   └── components/             # مكونات إضافية
├── tests/                      # اختبارات (662 اختبار)
├── mobile/                     # تطبيق React Native (Expo)
├── docs/                       # التوثيق
│   ├── USER_PROBLEMS_RESEARCH.md
│   ├── CHATGPT_RECOMMENDATIONS_ANALYSIS.md
│   └── GOOGLE_SIGNIN_SETUP.md
├── scripts/                    # سكربتات التشغيل
├── data/                       # البيانات المحفوظة
└── reports/                    # التقارير المولّدة
```

---

## 🗄️ قاعدة البيانات (Supabase)

### الجداول الرئيسية

| الجدول | الوصف | عدد السجلات |
|--------|-------|-------------|
| `listings` | إعلانات الفريج/المصادر المحفوظة | 182 |
| `market_listings` | إعلانات السوق الخارجية المحصودة | 2824 |
| `price_trends` | اتجاهات الأسعار الشهرية | 583 |
| `market_ads` | إعلانات السوق الحية | 18 |
| `official_transactions` | صفقات رسمية مستوردة | متغير |
| `official_market_indicators` | مؤشرات سعرية رسمية | 53 |
| `saved_reports` | تقارير بحث محفوظة | 749 |
| `source_runs` | سجل تشغيل المصادر | 5800 |
| `listing_evidence` | دليل كل رقم داخل النتائج | 74908 |
| `client_leads` | عملاء محتملون | 1 |
| `opportunities` | لقطات فرص محفوظة | 408 |
| `search_history` | سجل بحث | 482 |
| `users` | حسابات المستخدمين | 5 |
| `saved_searches` | الأبحاث المحفوظة | متغير |
| `user_alerts` | التنبيهات | متغير |
| `user_valuation_requests` | طلبات التقييم | متغير |

### هيكل الجداول المهمة

```sql
-- المستخدمين
CREATE TABLE users (
  phone TEXT PRIMARY KEY,
  secret TEXT,
  otp_hash TEXT,
  otp_expires_at TIMESTAMP,
  otp_attempts INT DEFAULT 0,
  otp_requested_at TIMESTAMP,
  verified BOOLEAN DEFAULT FALSE,
  role TEXT DEFAULT 'user',
  google_email TEXT,
  google_name TEXT,
  google_picture TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- الإعلانات
CREATE TABLE market_listings (
  id SERIAL PRIMARY KEY,
  code TEXT UNIQUE,
  source TEXT,
  area TEXT,
  governorate TEXT,
  price DECIMAL,
  space DECIMAL,
  property_type TEXT,
  transaction TEXT,
  summary TEXT,
  features TEXT,
  original_url TEXT,
  phone TEXT,
  photos JSONB,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

-- اتجاهات الأسعار
CREATE TABLE price_trends (
  id SERIAL PRIMARY KEY,
  area TEXT,
  property_type TEXT,
  month TEXT,
  median_price DECIMAL,
  median_price_per_m2 DECIMAL,
  sample_count INT,
  created_at TIMESTAMP DEFAULT NOW()
);

-- التقييمات
CREATE TABLE user_valuation_requests (
  id SERIAL PRIMARY KEY,
  user_secret TEXT,
  region TEXT,
  property_type TEXT,
  land_area_m2 DECIMAL,
  offered_price DECIMAL,
  fair_value_estimated DECIMAL,
  score INT,
  lang TEXT DEFAULT 'ar',
  created_at TIMESTAMP DEFAULT NOW()
);
```

---

## 🔌 API Endpoints الرئيسية

### البحث والتقييم

| Endpoint | Method | الوصف | Auth |
|----------|--------|-------|------|
| `/api/analyze` | POST | بحث وتقييم شامل | اختياري |
| `/api/parse` | POST | تحليل الطلب فقط | لا |
| `/api/report-pdf` | POST | تقرير PDF | لا |

### المصادقة

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/api/register` | POST | تسجيل مستخدم جديد (OTP) |
| `/api/verify-otp` | POST | تحقق من رمز OTP |
| `/api/google-login` | POST | تسجيل دخول Google |
| `/api/google-client-id` | GET | جلب Google Client ID |
| `/api/apple-login` | POST | تسجيل دخول Apple |

### البيانات

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/api/health` | GET | فحص صحة الخادم |
| `/api/sources` | GET | المصادر المتاحة |
| `/api/price-trends` | GET | اتجاهات الأسعار |
| `/api/opportunities` | GET | فرص المكسب |
| `/api/developments` | GET | تطورات السوق |
| `/api/analytics-dashboard` | GET | لوحة التحليلات |
| `/api/market-data` | GET | بيانات السوق |
| `/api/dashboard` | GET | لوحة التحكم |

### التمويل والاستثمار

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/api/invest/mortgage` | POST | حاسبة التمويل العقاري |
| `/api/invest/compare-banks` | POST | مقارنة بنوك الكويت |
| `/api/invest/compare` | POST | مقارنة أحياء |
| `/api/invest/forecast` | POST | توقع العائد |

### التنبيهات

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/api/smart-alerts/check` | POST | فحص التنبيهات الذكية |
| `/api/smart-alerts/subscribe` | POST | اشتراك في تنبيهات منطقة |
| `/api/smart-alerts/unsubscribe` | POST | إلغاء الاشتراك |
| `/api/smart-alerts/list` | GET | عرض التنبيهات النشطة |
| `/api/push/register` | POST | تسجيل جهاز للإشعارات |
| `/api/push/subscribe` | POST | اشتراك في إشعارات |

### الإدارة

| Endpoint | Method | الوصف |
|----------|--------|-------|
| `/api/admin/users` | GET | قائمة المستخدمين |
| `/api/admin/stats` | GET | إحصائيات الإدارة |
| `/api/admin/dashboard` | GET | لوحة تحكم الإدارة |
| `/api/roles` | GET | الأدوار المتاحة |
| `/api/ai/providers` | GET | مزودي الذكاء الاصطناعي |

---

## 🧠 نظام التقييم (valuation.py)

### المعادلات الأساسية

```python
# درجة التوصية = 62% مطابقة + 28% جاذبية السعر + 10% ثقة
REC_MATCH_WEIGHT = 0.62
REC_DEAL_WEIGHT = 0.28
REC_CONFIDENCE_WEIGHT = 0.10

# الثقة = أساس 50% + 6% لكل مقارنة (حد أقصى 90%)
CONFIDENCE_BASE = 0.5
CONFIDENCE_PER_COMPARABLE = 0.06
CONFIDENCE_MAX = 0.9

# حدود عدالة السعر (نسبة السعر/الوسيط)
DEAL_SCORE_BANDS = [
    (0.82, 100),  # ≤0.82 → لقطة ممتازة
    (0.92, 88),   # ≤0.92 → أقل من السوق
    (1.08, 74),   # ≤1.08 → سعر عادل
    (1.18, 58),   # ≤1.18 → أعلى قليلاً
    (1.35, 38),   # ≤1.35 → غالي
]
# >1.35 → مبالغ فيه (20 نقطة)
```

### Confidence Interval (نطاق الثقة)

```python
def _calculate_confidence_interval(market_median, confidence, comparables_count):
    # نسبة عدم اليقين: كلما زادت الثقة، قلّت النسبة
    ci_pct = max(5, min(25, round(25 - confidence * 20, 1)))
    low = market_median * (1 - ci_pct / 100)
    high = market_median * (1 + ci_pct / 100)
    return ci_pct, low, high

# مثال:
# ثقة 80% → ±9% → 182,000 – 218,000 د.ك
# ثقة 50% → ±15% → 170,000 – 230,000 د.ك
```

---

## 🎯 الميزات الجديدة (تم تطبيقها)

### 1. Trust Score (مؤشر ثقة الإعلان)
- **الملف:** `backend/services/trust_score.py`
- **الاختبارات:** `tests/test_trust_score.py` (21 اختبار)
- **الوزن:** عمر الإعلان (20) + استقرار السعر (25) + تعدد المصادر (15) + الصور (15) + المصدر (10) + مطابقة السعر (15)

### 2. Mortgage Calculator (حاسبة الرهن العقاري)
- **الملف:** `backend/services/mortgage_calculator.py`
- **الاختبارات:** `tests/test_mortgage_calculator.py` (22 اختبار)
- **البنوك:** KFH (4.5%) + KBK (4.75%) + CBK (5.0%) + Boubyan (4.25%)

### 3. Smart Alerts (تنبيهات ذكية)
- **الملف:** `backend/services/smart_alerts.py`
- **الاختبارات:** `tests/test_smart_alerts.py` (14 اختبار)
- **الأنواع:** انخفاض السعر + فرصة جديدة + سعر أقل من المتوسط

### 4. Confidence Intervals (نطاق الثقة)
- **الملف:** `backend/services/valuation.py`
- **الوظيفة:** `_calculate_confidence_interval()` + `_build_explanation_factors()`

---

## 📊 إحصائيات المشروع

| المقياس | القيمة |
|---------|--------|
| **إجمالي الملفات** | 100+ ملف |
| **Backend (Python)** | 20,000+ سطر |
| **Frontend (JS)** | 8,800+ سطر |
| **CSS** | 9,600+ سطر |
| **الاختبارات** | 662 اختبار (0 فاشل) |
| **API Endpoints** | 50+ endpoint |
| **جداول قاعدة البيانات** | 16 جدول |
| **البيانات** | 3,000+ إعلان |

---

## ⚠️ المشاكل والتحديات الحالية

### 1. مصادر البيانات المطلوبة

| المورد | الحالة | الملاحظة |
|--------|--------|----------|
| **Supabase** | ✅ مُعرّف | يعمل |
| **Google Client ID** | ⚠️ غير مُعرّف | يحتاج إعداد |
| **Apple Client ID** | ⚠️ غير مُعرّف | يحتاج إعداد |
| **WhatsApp API** | ⚠️ غير مُعرّف | Meta Cloud API |

### 2. ما نحتاجه من Codex

#### أ) إصلاح المشاكل المعروفة

1. **`test_radius_snapshot.py`** — يفشل أحياناً في سلسلة الاختبارات (flaky test)
2. **`live_sources.py`** — ملف ضخم (2726 سطر) يحتاج تحسين الأداء
3. **`app.js`** — ملف واحد ضخم (8800+ سطر) يحتاج تقسيم

#### ب) تحسينات مقترحة

1. **ML AVM** — بناء نموذج XGBoost/CatBoost لتقييم العقارات
2. **Building Age** — استخراج عمر البناء من النصوص
3. **Days on Market** — تتبع مدة بقاء الإعلان
4. **Orientation/Front** — استخراج واجهة العقار
5. **Similarity Score** — تحسين المقارنات بناءً على التشابه

#### ج) موارد مطلوبة

1. **Google Cloud Project** — لإعداد OAuth
2. **Apple Developer Account** — لإعداد Sign In with Apple
3. **Meta Business Account** — لرسائل واتساب

---

## 🚀 أوامر مفيدة

```bash
# تشغيل الخادم
cd alforaij-research-assistant
PYTHONIOENCODING=utf-8 python -m backend.main

# تشغيل الاختبارات
PYTHONIOENCODING=utf-8 python -m pytest tests/ -q

# اختبار ملف محدد
PYTHONIOENCODING=utf-8 python -m pytest tests/test_trust_score.py -v

# فحص JavaScript
node -c frontend/app.js

# فحص Python
python -c "from backend.main import *; print('OK')"

# بناء Docker
docker build -t alforaij .
docker run -p 8000:8000 alforaij
```

---

## 📚 المراجع الأكاديمية (من بحث ChatGPT)

1. **Ge & Raptis (2026)** — AI in real estate valuation
2. **Cacciamani et al. (2024)** — AI in Real Estate Industry
3. **Forradellas & Benítez (2026)** — ML for Real Estate Analysis
4. **Pollestad et al. (2026)** — Uncertainty in AVM
5. **Huang et al. (2026)** — Multimodal ML in real estate

---

## 🎯 أولويات Codex

### الأولوية الأولى ( hazard)
1. ✅ إصلاح `test_radius_snapshot.py` flaky test
2. ✅ مراجعة أمان `main.py` (API keys exposure)
3. ✅ فحص تسريب الذاكرة في `live_sources.py`

### الأولوية الثانية (مهم)
1. 🔄 بناء ML AVM مع XGBoost
2. 🔄 تحسين `app.js` (تقسيم إلى ملفات)
3. 🔄 إضافة Building Age + Days on Market

### الثالثة (تحسين)
1. 📊 تحسين الأداء (caching, lazy loading)
2. 📊 تحسين SEO (meta tags, structured data)
3. 📊 إضافة offline support (Service Worker)

---

## 📞 التواصل

- **المالك:** ahmedkamalsa
- **المستودع:** https://github.com/ahmedkamalsa/alforaij
- **الموقع:** http://127.0.0.1:8000 (محلي)
- **الإنتاج:** https://search.alforaij.com

---

*تم إنشاء هذا الملف في: 2026-08-29*
*آخر تحديث: 2026-08-29*
*الإصدار: 1.0.0*
