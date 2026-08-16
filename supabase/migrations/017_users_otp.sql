-- حسابات المستخدمين المجانيين (المهمة 1): تسجيل بالهاتف بلا كلمة مرور.
--
-- OTP: 6 أرقام بملح (salt:sha256(code+salt))، صالح 10 دقائق، حد 5 محاولات،
-- ونافذة 15 دقيقة بين إعادة الإرسال (otp_requested_at).
--
-- الأمان: users.secret (24 حرفًا عشوائيًا) هو المفتاح الوحيد لبيانات المستخدم —
-- لا يُكشف أبدًا ويُحفظ في localStorage فقط. anon لا يقرأ الجدول ولا يكتبه
-- مباشرة: التسجيل/التحقق يتمان عبر خادم API (service_role)، وقراءة البيانات
-- الشخصية في المهام التالية عبر دوال RPC تتحقق من السرّ.

create table if not exists users (
  id bigint generated always as identity primary key,
  phone text not null unique,              -- بصيغة +965XXXXXXXX
  secret text not null default '',         -- 24 حرفًا عشوائيًا = المصداقية
  otp_hash text,                           -- salt:sha256(code+salt)
  otp_expires_at timestamptz,
  otp_attempts integer not null default 0,
  otp_requested_at timestamptz,            -- نافذة منع إعادة الإرسال المتكرر
  verified boolean not null default false,
  last_alert_at timestamptz,
  created_at timestamptz not null default now()
);

alter table users enable row level security;

drop policy if exists "users service role all" on users;
create policy "users service role all"
  on users for all to service_role using (true) with check (true);
