# منصة الفريج للبحث والتقييم العقاري

منصة عربية لتحليل السوق العقاري في الكويت: تبحث في بيانات الفريج والمصادر الخارجية، تقارن الأسعار، تعرض الأدلة، وتحفظ مسار القرار في Supabase. الهدف ليس مجرد عرض إعلانات، بل مساعدة المستخدم على فهم السعر والفرصة والطلب الحقيقي حول العقار.

## التشغيل السريع

المتطلبات:

- Python 3.11 أو أحدث.
- Node.js اختياري لفحص ملفات JavaScript.
- Supabase اختياري؛ عند غياب مفاتيحه تعمل المنصة محليا ببيانات الفريج والملفات.

```bash
cd alforaij-research-assistant
PYTHONIOENCODING=utf-8 python -m backend.main
```

افتح:

```text
http://127.0.0.1:8000
```

فحص الصحة:

```bash
curl http://127.0.0.1:8000/api/health
```

## فكرة العمل

```text
نص المستخدم
  -> تحليل النية والمنطقة والميزانية
  -> جلب بيانات الفريج والمصادر الخارجية
  -> إزالة التكرار وتصنيف الإعلانات
  -> تقييم السعر والفرصة من الأرقام الفعلية
  -> توليد تقرير عربي مع مصادر وأدلة
  -> حفظ التقرير ومسار الوكلاء في Supabase
```

النماذج اللغوية لا تنتج أرقام التقييم. الأرقام تأتي من `valuation.py`، المقارنات، Supabase، والمصادر الموثقة. الذكاء الاصطناعي يستخدم للتفسير، تلخيص الأدلة، واكتشاف نواقص البيانات.

## التبويبات

| التبويب | الوظيفة |
|---|---|
| البحث والتقييم | شات عربي، فلاتر، مصادر خارجية، نتائج مرتبة حسب درجة التوصية |
| النتائج | بطاقات عقارات، مصادر كل رقم، الطلبات المطابقة، فرص الربح |
| أفضل الفرص | فرص يومية/أسبوعية/شهرية، انخفاضات سعر، وفرص حسب العملاء |
| لوحة السوق | إحصاءات المحافظات والمناطق، العرض والطلب، حركة السوق |
| تحليلات السوق | عائد الإيجار، فجوات السعر، مؤشرات الاتجاهات |
| التطورات | أخبار ومؤشرات السوق من وكيل الاكتشاف |
| مجاني وأدق | مقارنة مع المنصات المدفوعة وخريطة الربط والاشتراكات |
| المصادر والتشغيل | حالة المصادر، الوكيل اليومي، الاستيراد، وسجل التشغيل |
| سجل المقاييس | تعريف كل رقم وصيغته ومصدره |

## مسار الوكلاء

كل تحليل يرجع `agentTrace`:

| الوكيل | المهمة |
|---|---|
| `intent_agent` | فهم نص المستخدم وتحويله إلى حقول منظمة |
| `source_agent` | تحديد المصادر التي دخلت البحث وحالة كل مصدر |
| `quality_agent` | تقييم جودة البيانات ونواقصها |
| `valuation_agent` | تلخيص السعر، الوسيط، الثقة، ودرجة التوصية |
| `demand_agent` | ربط التحليل بما يريده المستخدمون والعملاء |
| `report_agent` | صياغة التقرير النهائي وفصل الأرقام عن التفسير |

تظهر هذه المعلومات في الواجهة داخل لوحة "مسار التحليل"، وتحفظ في Supabase عند توفر الجداول.

## مزودات الذكاء الاصطناعي

الترتيب الافتراضي:

```text
nvidia_nim,freellmapi,gemini,openrouter,ollama,agentrouter
```

الإعدادات الاختيارية:

```env
NVIDIA_API_KEY=
NVIDIA_API_URL=https://integrate.api.nvidia.com/v1
NVIDIA_MODEL=minimaxai/minimax-m3

FREELLMAPI_URL=http://127.0.0.1:5050/v1
FREELLMAPI_KEY=
FREELLMAPI_MODEL=minimaxai/minimax-m3

GEMINI_API_KEY=
OPENROUTER_API_KEY=
OLLAMA_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1:8b
AGENT_ROUTER_API_KEY=
AI_PROVIDER_ORDER=nvidia_nim,freellmapi,gemini,openrouter,ollama,agentrouter
```

إذا فشل كل مزود، تستخدم المنصة تحليلا محليا حتميا ولا يفشل طلب المستخدم.

## مصادر البيانات

| المصدر | الحالة | الاستخدام |
|---|---|---|
| بيانات الفريج | متصل | أساس البحث والمطابقة |
| OpenSooq | حي/مسجل | مقارنات سوقية عند تطابق المنطقة والنوع |
| Mourjan | حي/مسجل | إعلانات عامة بروابط وأدلة |
| Q8Aqar | حي/تفاصيل | تحسين السعر والمساحة من صفحات التفاصيل |
| Yebtah | حي مشروط | قوائم بيع وإيجار منظمة جزئيا |
| 4Sale | مشروط | مصدر مهم، لكن الظهور مدفوع ويجب فصل الإعلان عن التقييم |
| Property Finder Kuwait | يحتاج شراكة | يدخل فقط عبر Feed أو تصدير مرخص |
| Bayut Kuwait | يحتاج شراكة | مرشح ربط رسمي أو Feed مرخص |
| وزارة العدل | رسمي | صفقات وتحقق تسجيل عقاري عند توفر بيانات منظمة |
| PACI / Kuwait Finder | رسمي مكاني | تأكيد المنطقة والقطعة، لا ينتج سعرا وحده |

## Supabase

الجداول الأساسية:

| الجدول | الغرض |
|---|---|
| `listings` | بيانات الفريج المحلية |
| `market_ads` | إعلانات السوق الحية |
| `market_listings` | قاعدة المعرفة المتراكمة من المنصات |
| `source_registry` | سجل المصادر وسياسة الثقة |
| `source_runs` | تشغيل كل مصدر وحالته |
| `listing_evidence` | مصدر كل رقم داخل النتائج |
| `official_transactions` | الصفقات الرسمية المستوردة |
| `official_market_indicators` | مؤشرات سعرية رسمية/مرجعية |
| `search_history` | ما يريده المستخدمون وطلبات البحث |
| `saved_reports` | التقارير الكاملة |
| `saved_searches` | الأبحاث المحفوظة والتنبيهات |
| `client_leads` | العملاء المحتملون |
| `opportunities` | لقطات الفرص |
| `price_trends` | اتجاهات الأسعار |
| `ai_provider_runs` | محاولات مزودي AI |
| `analysis_agent_runs` | الوكلاء الرئيسيون لكل تحليل |
| `analysis_agent_steps` | مخرجات الوكلاء التفصيلية |
| `partner_feeds` | شراكات/اشتراكات المنصات المرخصة |
| `data_quality_events` | أخطاء ونواقص جودة البيانات |

تطبيق السكيما:

```text
شغل supabase/setup_all.sql من Supabase SQL Editor
أو شغل supabase/migrations/024_ai_agents_audit.sql فقط للجداول الجديدة
```

كل كتابات Supabase best-effort: إذا غاب جدول اختياري أو فشل الاتصال لا يتوقف تحليل المستخدم.

## أهم نقاط API

| المسار | الطريقة | الوظيفة |
|---|---|---|
| `/api/health` | GET | صحة الخادم وملخص الجداول |
| `/api/analyze` | POST | البحث والتقييم الكامل |
| `/api/analyze/progress` | GET | تقدم البحث الحي |
| `/api/sources` | GET | سجل المصادر |
| `/api/platform-intelligence` | GET | خريطة الربط والاشتراكات وقاعدة البيانات |
| `/api/metric-registry` | GET | تعريف المقاييس والصيغ |
| `/api/dashboard/summary` | GET | لوحة السوق |
| `/api/market-insights` | GET | تحليلات السوق |
| `/api/opportunities` | GET | أفضل الفرص |
| `/api/market-matching` | GET | توفيق العرض والطلب |
| `/api/weekly-digest` | GET | موجز أسبوعي |
| `/api/report-pdf` | POST | تقرير PDF |
| `/api/report-excel` | POST | تقرير Excel |
| `/api/register` | POST | تسجيل OTP |
| `/api/verify-otp` | POST | تحقق OTP |
| `/api/google-login` | POST | دخول Google |
| `/api/daily-agent/run` | POST | تشغيل الوكيل اليومي |
| `/api/official-transactions/import` | POST | استيراد صفقات رسمية |
| `/api/ai/providers` | GET/POST | حالة مزودي AI |

## متغيرات البيئة

```env
ALFORAIJ_ASSISTANT_HOST=127.0.0.1
ALFORAIJ_ASSISTANT_PORT=8000
ALFORAIJ_LOG_LEVEL=INFO

SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=

WHATSAPP_TOKEN=
WHATSAPP_PHONE_ID=
WHATSAPP_SENDER_NAME=فريق الفريج العقاري

GOOGLE_CLIENT_ID=
OFFICIAL_TRANSACTIONS_SOURCE=
```

## الاختبارات

```bash
python -m py_compile backend/main.py backend/services/ai_router.py backend/services/analysis_agents.py backend/services/supabase_store.py
python -m pytest tests/test_ai_router.py tests/test_analysis_agents.py tests/test_supabase_store.py tests/test_platform_intelligence.py -q
node --check frontend/app.js
node --check frontend/sw.js
```

## التنظيف

سياسة التنظيف:

- حذف الملفات المؤقتة غير المتتبعة إذا ثبت أنها غير مستخدمة.
- عدم حذف مستندات أو عروض أو ملفات مستخدم بدون دليل.
- عدم حذف ملفات Git المتتبعة حتى لو تشابهت بالـ hash إلا بعد فحص المراجع.
- لقطات Playwright و`test-results` لا تحذف إلا إذا كانت غير متتبعة وغير مطلوبة للتحقق.

## النشر والرفع

قبل الرفع:

```bash
git status --short
python -m pytest tests/ -q
node --check frontend/app.js
node --check frontend/sw.js
```

الواجهة تعمل كلقطة ثابتة عند غياب خادم API، لكن أفضل تجربة حية تحتاج backend منشور وضبط:

```env
ALFORAIJ_API_BASE=https://your-backend-domain.example.com
```

## ملاحظات للمبرمج

- `backend/main.py` كبير؛ أي ميزة جديدة يفضل أن تكون في خدمة مستقلة داخل `backend/services`.
- `supabase_store.py` هو مكان الكتابة والقراءة من Supabase.
- `source_registry.py` هو مصدر الحقيقة لأسماء المصادر ومعرفاتها.
- `platform_intelligence.py` يشرح حالة الربط والاشتراكات.
- `analysis_agents.py` يبني trace الوكلاء دون استدعاء AI.
- `ai_router.py` وحده يتعامل مع مزودي الذكاء الاصطناعي.
- أي مصدر مدفوع أو محمي لا يدخل التقييم إلا عبر شراكة أو Feed مرخص.

## آخر تحديث

2026-08-31:

- إضافة NVIDIA NIM / MiniMax M3 كمسار AI اختياري.
- تتبع محاولات مزودي AI.
- إضافة وكلاء تحليل رئيسيين وفرعيين.
- إضافة جداول audit في Supabase.
- إضافة خريطة الربط والاشتراكات.
- إصلاح Service Worker.
- إصلاح حفظ `search_history` عند عدم وجود نتيجة عليا.

المشروع للتقييم الاسترشادي فقط، وليس بديلا عن تقييم رسمي أو فحص قانوني للعقار.
