# 🏢 الفريج العقاري — Al-Furaj Real Estate Platform

<div align="center">

**بحث وتقييم وفرص عقارية مبنية على الأدلة والمصادر**

[![CI/CD](https://github.com/ahmedkamalsa/alforaij/actions/workflows/ci-cd.yml/badge.svg)](https://github.com/ahmedkamalsa/alforaij/actions/workflows/ci-cd.yml)
[![Tests](https://img.shields.io/badge/tests-576%20passed-brightgreen)]()
[![Python](https://img.shields.io/badge/python-3.13-blue)]()
[![License](https://img.shields.io/badge/license-MIT-green)]()

</div>

---

## 🎯 ما هي المنصة؟

الفريج هي منصة بحث وتقييم عقاري ذكية تجمع **18+ مصدر** في بحث واحد، وتقدم:

| الميزة | الوصف |
|--------|-------|
| 🔍 **بحث ذكي بالعربية** | اكتب "بيت 400م في الفردوس" واحصل على نتائج مقيّمة |
| 📊 **تقييم بالأدلة** | كل رقم له مصدر ودليل |
| 🗺️ **خريطة تفاعلية** | مواقع العقارات على OpenStreetMap |
| 📈 **اتجاهات الأسعار** | رسوم بيانية شهرياً لكل منطقة |
| 💰 **حاسبة العائد** | ROI + تمويل عقاري |
| 🤖 **مساعد ذكي** | أسئلة وأجوبة عقارية |
| 📱 **تطبيق جوال** | React Native + إشعارات فورية |
| 🏢 **لوحة تحكم** | إدارة المستخدمين والإعلانات |

---

## 🏗️ الهيكل التقني

```
┌─────────────────────────────────────────────────────────────┐
│                      FRONTEND                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │  index   │  │  admin   │  │  mobile  │  │  styles  │   │
│  │  .html   │  │  .html   │  │  App.js  │  │  .css    │   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └──────────┘   │
│       │              │              │                        │
│  ┌────▼──────────────▼──────────────▼────┐                  │
│  │         app.js (8,527 lines)          │                  │
│  │  Search • Map • Charts • Chat • PDF   │                  │
│  └──────────────────┬───────────────────┘                  │
└─────────────────────┼───────────────────────────────────────┘
                      │ HTTP REST (50+ endpoints)
┌─────────────────────▼───────────────────────────────────────┐
│                      BACKEND                                │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  main.py — Python 3.13 stdlib HTTP server            │  │
│  └──────────────────────┬───────────────────────────────┘  │
│                         │                                   │
│  ┌──────────┐  ┌────────▼───────┐  ┌──────────────────┐   │
│  │  AI RAG  │  │  Services      │  │  Connectors      │   │
│  │  System  │  │  (37 modules)  │  │  (18+ scrapers)  │   │
│  └──────────┘  └────────┬───────┘  └──────────────────┘   │
│                         │                                   │
│  ┌──────────────────────▼───────────────────────────────┐  │
│  │              Supabase (PostgreSQL)                    │  │
│  │  14 tables • 72,486 evidence rows • 3,024 listings  │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 🚀 التشغيل المحلي

### المتطلبات
- Python 3.13+
- Node.js 18+ (للتقديم)
- Supabase account (مجاني)

### خطوات التشغيل

```bash
# 1. استنساخ المستودع
git clone https://github.com/ahmedkamalsa/alforaij.git
cd alforaij-research-assistant

# 2. تثبيت الاعتماديات
pip install -r requirements.txt

# 3. تكوين متغيرات البيئة
cp .env.example .env
# عدّل .env بمفاتيحك

# 4. تشغيل الخادم
python -m backend.main

# 5. فتح المتصفح
# الموقع: http://127.0.0.1:8000
# لوحة التحكم: http://127.0.0.1:8000/admin.html
```

### تشغيل الاختبارات

```bash
# الاختبارات الكاملة
PYTHONIOENCODING=utf-8 python -m pytest tests/ -x -q

# مع تغطية
PYTHONIOENCODING=utf-8 python -m pytest tests/ --cov=backend --cov-report=term-missing
```

---

## 📡 API Endpoints

### البحث والتحليل
| Method | Endpoint | الوصف |
|--------|----------|-------|
| POST | `/api/analyze` | البحث الرئيسي + تقييم |
| POST | `/api/parse` | تحليل الاستعلام الطبيعي |
| GET | `/api/price-trends?area=X` | اتجاهات الأسعار |
| GET | `/api/opportunities` | فرص الاستثمار |
| GET | `/api/dashboard/summary` | ملخص لوحة التحكم |

### المصادقة
| Method | Endpoint | الوصف |
|--------|----------|-------|
| POST | `/api/register` | تسجيل رقم الهاتف |
| POST | `/api/verify-otp` | التحقق من OTP |
| POST | `/api/google-login` | تسجيل دخول Google |

### الإدارة
| Method | Endpoint | الوصف |
|--------|----------|-------|
| GET | `/api/admin/users` | قائمة المستخدمين |
| GET | `/api/roles` | الأدوار والصلاحيات |
| GET | `/api/push/stats` | إحصائيات الإشعارات |

> **الدليل الكامل**: راجع `CODEX_REVIEW.md` و `sitenoladge.md`

---

## 🧪 الاختبارات

```
576 اختبار | 52 ملف اختبار | 50+ subtests
```

| الملف | الاختبارات | التغطية |
|-------|-----------|---------|
| test_accounts.py | 15 | OTP + phone + roles |
| test_ai_router.py | 18 | AI fallback chain |
| test_request_parser.py | 40+ | Arabic NLP parsing |
| test_live_sources.py | 57 | External scrapers |
| test_analysis.py | 30+ | Search + evaluation |
| test_api.py | 20+ | API endpoints |
| test_opportunities.py | 15+ | Opportunity detection |

---

## 🔧 الإعدادات

### متغيرات البيئة المطلوبة

```env
# الخادم
ALFORAIJ_ASSISTANT_HOST=127.0.0.1
ALFORAIJ_ASSISTANT_PORT=8000

# قاعدة البيانات (Supabase)
SUPABASE_URL=https://xxx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=xxx

# Google Sign-In (اختياري)
GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com

# WhatsApp (اختياري)
WHATSAPP_TOKEN=xxx
WHATSAPP_PHONE_ID=xxx

# الذكاء الاصطناعي (واحد على الأقل)
OLLAMA_URL=http://127.0.0.1:11434
GEMINI_API_KEY=xxx
OPENROUTER_API_KEY=xxx
```

---

## 📱 تطبيق الجوال

```bash
cd mobile
npm install
npx expo start
# امسح QR كود بتطبيق Expo Go
```

**المميزات**: WebView + إشعارات فورية + بحث + خريطة

---

## 🏢 لوحة التحكم

**الوصول**: `http://127.0.0.1:8000/admin.html`

| القسم | المحتوى |
|-------|---------|
| نظرة عامة | إحصائيات + أنشطة + حالة المصادر |
| المستخدمون | جدول + بحث + تعيين أدوار + تصدير CSV |
| الأدوار | محرر صلاحيات بصري |
| الإعلانات | بطاقات + حالة + موافقة + تعديل + حذف |
| التحليلات | رسوم بيانية + اتجاهات |
| السوق | حالة المصادر الخارجية |

---

## 🤖 نظام الذكاء الاصطناعي

### RAG (Retrieval Augmented Generation)
```
استعلام المستخدم → تحليل → بحث متجهي → سياق ذكي → تحليل AI
```

### AI Router (Fallback Chain)
```
FreeLLMAPI → Ollama → Gemini → OpenRouter → AgentRouter
(34 مزوّد)   (محلي)   (مجاني)   (مجاني)    (احتياطي)
```

---

## 📊 أداء المنصة

| المقياس | القيمة |
|---------|--------|
| Lighthouse Performance | 50/100 |
| First Contentful Paint | 3.6s |
| Total Blocking Time | 718ms |
| سرعة البحث (سريع) | 3.1s |
| سرعة البحث (كامل) | 47s |
| الاختبارات | 576 ✅ |
| APIs | 50+ |
| المصادر الخارجية | 18+ |

---

## 📁 هيكل الملفات

```
alforaij-research-assistant/
├── backend/
│   ├── main.py                    # الخادم + 50+ API
│   ├── connectors/                # 18+ مصادر خارجية
│   └── services/                  # 37 خدمة
├── frontend/
│   ├── index.html                 # الموقع الرئيسي
│   ├── admin.html                 # لوحة التحكم
│   └── app.js                     # المنطق (8,527 سطر)
├── mobile/                        # تطبيق الجوال
├── tests/                         # 576 اختبار
├── .github/workflows/             # CI/CD
├── CODEX_REVIEW.md                # مراجعة تقنية
├── sitenoladge.md                 # معرفة المنصة الشاملة
└── requirements.txt               # الاعتماديات
```

---

## 🤝 المساهمة

1. Fork المستودع
2. Create branch جديد (`git checkout -b feature/amazing-feature`)
3. Commit (`git commit -m 'Add amazing feature'`)
4. Push (`git push origin feature/amazing-feature`)
5. Open Pull Request

---

## 📄 التوثيق

- **`CODEX_REVIEW.md`** — مراجعة تقنية شاملة
- **`sitenoladge.md`** — معرفة المنصة الكاملة
- **`PROJECT_CONTEXT.md`** — سياق المشروع
- **`README_AR.md`** — README بالعربي

---

## 📞 التواصل

**شركة عبدالعزيز سعود الفريج العقارية**  
ABDUL AZIZ SAUD AL-FURAJ REAL ESTATE COMPANY

---

*Last updated: 2026-08-29 | Version: 1.0 | Tests: 576 passed*
