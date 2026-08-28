# PROJECT_CONTEXT.md — منصة الفريج للفرص والتقييم العقاري

## نظرة عامة

منصة **الفريج** هي نظام متكامل للبحث والتقييم العقاري في الكويت، يجمع بيانات من مصادر متعددة (محليّة وخارجية) ويوفر تحليلًا ذكيًا مبنيًا على الأدلة.

### القيم الجوهرية

- **بحث موحد** في 2894+ إعلان من 6 مصادر
- **تقييم مقارن ذكي** يربط العرض بالطلب والعملاء المحتملين
- **فرص مكسب** تربط السعر بالسوق والعميل المناسب
- ** Updates يومية** من 11 مصدر عقاري كويتي

---

## البنية التحتية

```
alforaij-research-assistant/
├── backend/                    # الخادم الرئيسي (Python 3.11)
│   ├── main.py                 # نقطة الدخول — HTTP handler
│   ├── config.py               # إعدادات الخادم
│   ├── models.py               # نماذج البيانات
│   ├── connectors/             # جامعات البيانات من المصادر الخارجية
│   │   ├── alforaij.py         # بيانات الفريج المحلية
│   │   ├── live_sources.py     # OpenSooq, Mourjan, 4Sale, Q8Aqar
│   │   ├── official_data.py    # بيانات وزارة العدل الرسمية
│   │   └── market_ads.py       # إعلانات السوق المباشرة
│   └── services/               # خدمات العمل (35 ملف)
│       ├── request_parser.py   # تحليل الطلبات العربية
│       ├── matching.py         # مطابقة الإعلانات بالطلب
│       ├── valuation.py        # تقييم الأسعار المقارن
│       ├── opportunities.py    # حساب فرص المكسب
│       ├── report_generator.py # بناء التقارير
│       ├── ai_evaluator.py     # التحليل بالذكاء الاصطناعي
│       ├── supabase_store.py   # قاعدة البيانات (Supabase)
│       ├── analytics_dashboard.py # لوحة التحليلات
│       └── chat_agents.py      # المساعد العقاري
├── frontend/                   # الواجهة الأمامية
│   ├── index.html              # الصفحة الرئيسية (950+ سطر)
│   ├── app.js                  # المنطق البرمجي (8100+ سطر)
│   ├── styles.css              # التصميم (9100+ سطر)
│   ├── config.js               # إعدادات الواجهة
│   └── assets/                 # الصور والخطوط
├── mcp_server/                 # خادم MCP للegration مع AI
│   ├── server.py               # نقطة الدخول
│   ├── tools.py                # 9 أدوات MCP
│   └── protocol.py             # بروتوكول JSON-RPC
├── tests/                      # اختبارات (550+ اختبار)
├── scripts/                    # سكربتات التشغيل اليومي
├── data/                       # البيانات المحفوظة
├── reports/                    # التقارير المولّدة
├── canvas/                     # أعمال فنية
├── docs/                       # التوثيق
└── Dockerfile                  # حاوية Docker
```

---

## how to run

### التشغيل المحلي

```bash
cd alforaij-research-assistant
PYTHONIOENCODING=utf-8 python -m backend.main
# الخادم يعمل على http://127.0.0.1:8000
```

### الاختبارات

```bash
PYTHONIOENCODING=utf-8 python -m pytest tests/ -q
# 550+ اختبار يجتاز
```

### Docker

```bash
docker build -t alforaij .
docker run -p 8000:8000 alforaij
```

---

## البيانات والمصادر

### المصادر المحلية (182 إعلان)
- **الفيج العقاري** — إعلانات مجمّعة من البيانات المحلية

### المصادر الخارجية (2700+ إعلان)
| المصدر | العدد | الحالة |
|--------|-------|--------|
| OpenSooq | 1150+ | ✅ يعمل |
| 4Sale | 480+ | ✅ يعمل |
| Mourjan | 260+ | ✅ يعمل |
| Q8Aqar | 15 | ✅ يعمل |
| Ministry of Justice | متغير | ✅ بيانات رسمية |
| KFH Reports | 4 | ✅ تقارير رسمية |

### قاعدة البيانات (Supabase)
- **users** — حسابات المستخدمين
- **saved_searches** — الأبحاث المحفوظة
- **user_alerts** — التنبيهات
- **market_listings** — إعلانات السوق المحصّلة
- **price_trends** — اتجاهات الأسعار

---

## الميزات الرئيسية

### 1. البحث الذكي
- تحليل الطلبات العربية (المنطقة، المساحة، السعر، النوع)
- مطابقة صارمة ثم توسعة المحافظة ثم استرشادية
- تقييم سعر كل نتيجة (مقارنات + أدلة)

### 2. فرص المكسب
- ربط السعر بالسوق والعميل المحتمل
- 3 تصنيفات: فرصة واعدة / فرصة جيدة / فرصة ممتازة
- روابط واتساب مباشرة للعملاء

### 3. التحليل بالذكاء الاصطناعي
- تحليل النية من النص الطبيعي
- توليد تقارير احترافية بالعربية
- مساعد عقاري فوري (-fast mode: 0.46 ثانية)

### 4. التقييم المقارن
- مقارنة مع وسيط المنطقة
- حكم: لقطة / عادي / غالي
- العائد الإيجاري السنوي

### 5. لوحة التحليلات
- إحصائيات البحث والمناطق الأكثر بحثًا
- اتجاهات الأسعار والنشاط اليومي
- مصادر الإعلانات وأنواع العقارات

---

## API Endpoints الرئيسية

| Endpoint | Method | الوظيفة |
|----------|--------|---------|
| `/api/health` | GET | فحص صحة الخادم |
| `/api/analyze` | POST | بحث وتقييم شامل |
| `/api/google-login` | POST | تسجيل دخول Google |
| `/api/google-client-id` | GET | جلب Client ID |
| `/api/analytics-dashboard` | GET | لوحة التحليلات |
| `/api/opportunities` | GET | فرص المكسب |
| `/api/sources` | GET | المصادر المتاحة |
| `/api/developments` | GET | تطورات السوق |

---

## متغيرات البيئة المهمة

| المتغير | الافتراضي | الوصف |
|---------|-----------|-------|
| `ALFORAIJ_ASSISTANT_PORT` | 8000 | منفذ الخادم |
| `ALFORAIJ_ASSISTANT_HOST` | 127.0.0.1 | مضيف الخادم |
| `ALFORAIJ_LOG_LEVEL` | INFO | مستوى السجلات |
| `GOOGLE_CLIENT_ID` | "" | معرّف Google |
| `SUPABASE_URL` | "" | رابط Supabase |
| `SUPABASE_KEY` | "" | مفتاح Supabase |

---

## الارتباطات المهمة

- **`main.py` ← `request_parser.py`**: `_area_governorate_map` يُصدَّر من `request_parser` إلى `main` — إذا نُقل، حدّث 12+ موقع استيراد
- **`live_sources.py`**: أضخم ملف (2726 سطر) — يحتوي على parsers لكل مصدر
- **`app.js`**: ملف واجهة واحد (8100+ سطر) — يحتوي على كل المنطق
- **`styles.css`**: نظام تصميم كامل (9100+ سطر) — brand gold/navy

---

## أوامر مفيدة

```bash
# تشغيل الخادم
PYTHONIOENCODING=utf-8 python -m backend.main

# تشغيل الاختبارات
PYTHONIOENCODING=utf-8 python -m pytest tests/ -q

# فحص الجوال
python scripts/run_mobile_checks.py

# فحص الأداء
python scripts/run_performance_checks.py

# بناء Docker
docker build -t alforaij .

# اختبار MCP server
echo '{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}' | python mcp_server/server.py
```

---

## ملاحظات تقنية مهمة

1. **لا تضع API Keys في الكود** — استخدم `os.getenv()`
2. **الخادم يعمل بـ Python 3.11** — لا 3.13 (للتوافق مع pytest)
3. **`PYTHONIOENCODING=utf-8`** ضروري على Windows للعربية
4. **`fast: true`** في `/api/analyze` يُسرّع الاستجابة من 40s إلى 0.46s
5. **localStorage** يُرجع strings وليس JSON — لا تستخدم `JSON.parse("")`
6. **Health endpoint** قد يعلق إذا Supabase بطيء — استخدم `/api/google-client-id` للاختبار
