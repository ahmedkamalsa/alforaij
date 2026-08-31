# Alforaij Research Assistant — خطة التطوير الشاملة

> **Goal:** جعل منصة الفريج العقارية الأفضل في الكويت لفهم السوق العقاري والتقييم واكتشاف الفرص

**Architecture:** Python backend (HTTP server) + Static frontend (HTML/CSS/JS) + Supabase (PostgreSQL) + External scrapers (OpenSooq, Mourjan, Q8Aqar, etc.)

**Tech Stack:** Python 3.13, Supabase, HTML/CSS/JS (no framework), Tailwind-inspired custom CSS

---

## Phase 1: إصلاح مشكلة تحديد المناطق ✅ (مكتمل)
- [x] تعديل `market_ads.py` لاستخراج المنطقة المحددة من العنوان/الملخص
- [x] تعديل `normalize_dashboard_place()` لاستخراج منطقة أدق من النص
- [x] إضافة تنويعات أسماء المناطق الناقصة
- [x] إزالة رقم الهاتف الافتراضي من نموذج العملاء
- [x] إضافة حفظ محلي للعملاء في وضع الثابت

**Status:** complete
**Files:** `backend/connectors/market_ads.py`, `backend/services/request_parser.py`, `frontend/app.js`

---

## Phase 2: تحسين عرض اللوحة والنتائج 🔄 (التالي)
- [ ] تحسين عرض المناطق في جدول اللوحة — إظهار المنطقة + المحافظة معًا
- [ ] تحسين بطاقات النتائج — إظهار المنطقة المحددة بوضوح
- [ ] إضافة فلتر سريع حسب المنطقة في اللوحة
- [ ] تحسين عرض المحافظات — إظهار عدد المناطق الحقيقية

**Status:** in_progress
**Next Step:** تحسين عرض المنطقة في جدول اللوحة

---

## Phase 3: تحسين الرسوم البيانية والمخططات
- [ ] إضافة مكتبة Chart.js للرسوم البيانية التفاعلية
- [ ] تحسين مخطط حرارة المناطق (heatmap) بقيم وأدلة
- [ ] إضافة رسوم مقارنة السعر vs الإيجار
- [ ] تحسين عرض tooltips للرسوم البيانية

**Status:** pending

---

## Phase 4: تحسين البحث والتوافق
- [ ] تحسين خوارزمية البحث عن "مطلوب شراء/إيجار"
- [ ] توسيع المصادر — إضافة 4Sale و Bayut
- [ ] تحسين مطابقة العروض بالطلبات
- [ ] إضافة بحث بالقرب (proximity search)

**Status:** pending

---

## Phase 5: تحسين تجربة المستخدم
- [ ] تحسين بطاقات العرض والطلب
- [ ] إضافة إشعارات فورية للفرص الجديدة
- [ ] تحسين تجربة الجوال (responsive)
- [ ] إضافة وضع الليل/النهار التلقائي

**Status:** pending

---

## Phase 6: اختبارات ونشر
- [ ] تشغيل جميع الاختبارات والتأكد من خلو الأخطاء
- [ ] مراجعة الأداء والتحسين
- [ ] النشر النهائي على GitHub Pages

**Status:** pending

---

## Decisions Made
| Decision | Reason | Date |
|----------|--------|------|
| استخدام Supabase كقاعدة بيانات | تكامل سهل مع Python + PostgreSQL | 2026-08-18 |
| الاحتفاظ بالبيانات المحلية كأساس | تعمل بدون اتصال إنترنت | 2026-08-18 |
| استخدام detect_area_in_text() لاستخراج المناطق | أدق من الاعتماد على حقل المنطقة فقط | 2026-08-19 |

## Errors Encountered
| Error | Attempt | Resolution |
|-------|---------|------------|
| 405 في حفظ العملاء | 1 | إضافة حفظ محلي في وضع الثابت |
| المناطق تظهر كمحافظات فقط | 1 | تعديل market_ads.py + normalize_dashboard_place |
