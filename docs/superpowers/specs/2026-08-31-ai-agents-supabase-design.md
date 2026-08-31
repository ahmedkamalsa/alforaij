# AI Agents And Supabase Design - 2026-08-31

## الهدف

ترقية منصة الفريج من "بحث + تقرير" إلى منصة تحليل مترابطة: مزودات AI قابلة للتبديل، وكلاء مهام واضحة، وسجل Supabase يحفظ مصادر القرار وخطواته بدون أن تصبح النماذج اللغوية مصدر الأرقام.

## حدود التصميم

- الأرقام والتقييمات تبقى من `valuation.py` وبيانات Supabase والمصادر الموثقة.
- AI يكتب التفسير، يراجع نقص البيانات، ويصيغ خلاصة مفهومة فقط.
- أي API مجاني مثل FreeLLMAPI أو NVIDIA NIM يستخدم كطبقة اختيارية مع fallback، وليس اعتماد إنتاج وحيد.
- كل استدعاء AI وكل وكيل يجب أن يكون قابلا للتتبع في القاعدة عند توفر Supabase.

## AI Providers

الترتيب الافتراضي الجديد:

`nvidia_nim,freellmapi,gemini,openrouter,ollama,agentrouter`

الإعدادات:

- `NVIDIA_API_KEY`
- `NVIDIA_API_URL=https://integrate.api.nvidia.com/v1`
- `NVIDIA_MODEL=minimaxai/minimax-m3`
- `FREELLMAPI_URL`
- `FREELLMAPI_KEY`
- `FREELLMAPI_MODEL=minimaxai/minimax-m3`

## الوكلاء

- `intent_agent`: فهم الطلب وتحويله إلى حقول منظمة.
- `source_agent`: تحديد المصادر التي دخلت فعلا والتي فشلت أو تحتاج شراكة.
- `quality_agent`: جودة البيانات وأسباب الاستبعاد أو الثقة.
- `valuation_agent`: خلاصة التقييم الرقمي من النتائج لا من AI.
- `demand_agent`: ما يريده المستخدمون من `search_history` و`saved_searches`.
- `report_agent`: صياغة الملخص النهائي والأدلة.

## Supabase

Migration جديدة تضيف:

- `ai_provider_runs`: كل محاولة AI، المزود، النموذج، الزمن، الحالة.
- `analysis_agent_runs`: ملخص وكلاء التحليل لكل بحث.
- `analysis_agent_steps`: الخطوات الفرعية لكل وكيل.
- `partner_feeds`: مسار الشراكات والمنصات المدفوعة.
- `data_quality_events`: أحداث جودة البيانات والاستبعاد.

## الواجهة

إضافة قسم صغير في صفحة المقاييس/المصادر أو لوحة الثقة يعرض:

- المزود المستخدم أو fallback محلي.
- الوكلاء الذين عملوا.
- المصادر التي دخلت في التقييم.
- الجداول التي تغذي التقرير.

## التوثيق

إنشاء/تحديث ملف عربي شامل `README_AR.md` يشرح:

- تشغيل المشروع.
- كل التبويبات.
- APIs.
- Supabase.
- الوكلاء.
- مفاتيح البيئة.
- طريقة الاختبار والرفع.

## المصادر

- FreeLLMAPI GitHub: OpenAI-compatible gateway مع failover، لكن مناسب للتجربة الشخصية لا اعتماد إنتاج وحيد.
- NVIDIA NIM MiniMax M3: endpoint مجاني عبر `/v1/chat/completions`.
- MiniMax: M3 طويل السياق ومناسب للمهام الوكيلة والبرمجة.
