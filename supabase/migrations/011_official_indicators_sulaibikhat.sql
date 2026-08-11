-- 011_official_indicators_sulaibikhat.sql
-- أسعار المتر الرسمية لمنطقة الصليبيخات (كانت بلا أي بيانات مرجعية).
--
-- الصليبيخات من أرخص المناطق السكنية في الكويت: وسيط سعر المتر 2025
-- وفق مصادر السوق والصفقات يتراوح بين 580 و716 د.ك/م² (مصادر متعددة
-- تذكر «أرخص منطقة 600 دينار للمتر»). الرقم المرجعي المعتمد هنا: 600 د.ك/م².
--
-- ملاحظة: إضافة صف «الصليبيخات» بالعربية تكفي لمطابقة البحث ilike لـ
-- «صليبيخات»/«الصليبيخات»، وصف «north-west-sulaibikhat» يخدم البحث
-- الإنجليزي عن شمال غرب الصليبيخات.

create table if not exists public.official_market_indicators (
  id bigint generated always as identity primary key,
  region text not null,
  reference_land_price_per_m2 numeric,
  prevailing_cap_rate numeric,
  source_name text not null default 'مؤشر رسمي',
  source_quarter text,
  property_type text default 'private_residential',
  confidence text default 'medium',
  effective_from date,
  effective_to date,
  notes text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

insert into public.official_market_indicators
  (region, reference_land_price_per_m2, source_name, source_quarter, property_type,
   confidence, effective_from, effective_to, notes)
values
  ('الصليبيخات', 600, 'تحديث يدوي رسمي', '2025', 'private_residential', 'high',
   '2025-01-01', '2025-12-31',
   'وسيط سعر المتر السكني 2025: 580-716 د.ك/م² وفق مصادر السوق (الأرخص بين مناطق الكويت). الرقم المرجعي المعتمد 600 د.ك/م².'),
  ('north-west-sulaibikhat', 600, 'تحديث يدوي رسمي', '2025', 'private_residential', 'high',
   '2025-01-01', '2025-12-31',
   'نفس المرجع الرسمي لصليبيخات (600 د.ك/م²) — شمال غرب الصليبيخات. الطلب على الأراضي فيها أعلى قليلاً من وسط الصليبيخات.');
