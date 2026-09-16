# دليل مشروع alforaij-research-assistant

آخر تحديث: 2026-09-16

## وظيفة المشروع

هذا هو المشروع الأساسي لمنصة بحث الفريج:

- backend/API.
- واجهة `frontend`.
- تحليل فرص عقارية.
- تصدير static data.
- workflows للنشر إلى GitHub Pages ولوحة الفريج.

## روابط مهمة

- GitHub repo: `https://github.com/ahmedkamalsa/alforaij.git`
- GitHub Pages المؤكد للوحة: `https://ahmedkamalsa.github.io/alforaijboard/`

## أهم ملفات

- `AGENTS.md`: تعليمات تشغيل إلزامية لأي Agent.
- `frontend/app.js`: منطق الواجهة والعدادات.
- `frontend/static-data/`: fallback للواجهة الثابتة.
- `scripts/export_static_frontend_data.py`: تصدير بيانات static.
- `.github/workflows/deploy-alforaijboard.yml`: نشر الواجهة إلى `alforaijboard` فرع `gh-pages`.

## حالة رقم 182

تم إصلاح السبب في commit:

`b787454 fix: refresh alforaij live count in static frontend`

السبب كان الاعتماد على `frontend/static-data/health.json` وفيه `localRecords=182` عند فشل مسار live-db/Supabase.

الإصلاح جعل الواجهة تقرأ API الفريج الحي مباشرة.

## أوامر تحقق

```powershell
cd D:\foraj_social\287\alforaij-research-assistant
git status --short
node --check frontend\app.js
```

## قواعد أمان

- لا تطبع secrets.
- لا ترفع `.env`.
- لا تعدل `data/daily_agent_status.json` إلا إذا كان المطلوب تحديث runtime status.

