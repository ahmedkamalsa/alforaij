-- تسجيل/تحقق OTP عبر دوال RPC عامة (المكمل لـ 017): الموقع المنشور ثابت (GH Pages/
-- Cloudflare بلا خادم API)، لذا التسجيل من المتصفح يتم مباشرة عبر anon REST —
-- نفس نمط increment_share المُثبَت. الواجهة تستدعي هاتين الدالتين محروسًا،
-- والانحدار دائمًا on_screen (الرمز على الشاشة) عند غياب أسرار واتساب؛ خادم API
-- المحلي (نقطتا /api/register و/api/verify-otp) يبقى مسارًا مكمّلًا للتسليم
-- عبر واتساب حين تُضبط الأسرار.

-- التسجيل: يتحقق من الصيغة الكويتية (+965[2-9]XXXXXXXX)، يفرض نافذة 15 دقيقة
-- بين إعادة الإرسال، يبطل الرمز القديم ويصدر جديدًا (6 أرقام من gen_random_uuid).
create or replace function register_user(p_phone text)
returns json
language plpgsql
security definer
as $$
declare
  v_code text;
  v_salt text;
  v_digest text;
  v_user users%rowtype;
begin
  if p_phone !~ '^\+965[2-9][0-9]{7}$' then
    raise exception 'invalid phone';
  end if;
  select * into v_user from users where phone = p_phone;
  if v_user.id is not null then
    if now() - coalesce(v_user.otp_requested_at, now() - interval '1 hour') < interval '15 minutes' then
      raise exception 'rate limited';
    end if;
  end if;
  v_salt := replace(gen_random_uuid()::text, '-', '');
  v_code := lpad((((('x' || substr(v_salt, 1, 8))::bit(32))::bigint) % 1000000)::text, 6, '0');
  v_digest := v_salt || ':' || encode(sha256(convert_to(v_code || ':' || v_salt, 'UTF8')), 'hex');
  insert into users (phone, otp_hash, otp_expires_at, otp_attempts, otp_requested_at)
  values (p_phone, v_digest, now() + interval '10 minutes', 0, now())
  on conflict (phone) do update
    set otp_hash = excluded.otp_hash,
        otp_expires_at = excluded.otp_expires_at,
        otp_attempts = 0,
        otp_requested_at = excluded.otp_requested_at;
  return json_build_object('status', 'ok', 'delivery', 'on_screen', 'code', v_code);
end;
$$;

-- التحقق: يصحح المحاولات (حد 5)/الانتهاء (10 دقائق)، يُنشئ سرّ المستخدم (24 حرفًا)
-- عند أول تحقق ناجح ويرجعه — المفتاح الوحيد لبياناته في saved_searches/user_alerts.
create or replace function verify_otp_code(p_phone text, p_code text)
returns json
language plpgsql
security definer
as $$
declare
  v_user users%rowtype;
  v_salt text;
  v_digest text;
  v_secret text;
begin
  if p_phone !~ '^\+965[2-9][0-9]{7}$' or p_code is null or p_code = '' then
    raise exception 'invalid input';
  end if;
  select * into v_user from users where phone = p_phone;
  if v_user.id is null or v_user.otp_hash is null then
    raise exception 'no otp';
  end if;
  if now() > v_user.otp_expires_at then
    raise exception 'expired';
  end if;
  if v_user.otp_attempts >= 5 then
    raise exception 'too many attempts';
  end if;
  v_salt := split_part(v_user.otp_hash, ':', 1);
  v_digest := encode(sha256(convert_to(p_code || ':' || v_salt, 'UTF8')), 'hex');
  if v_digest <> split_part(v_user.otp_hash, ':', 2) then
    update users set otp_attempts = otp_attempts + 1 where phone = p_phone;
    raise exception 'wrong code';
  end if;
  v_secret := v_user.secret;
  if v_secret is null or v_secret = '' then
    v_secret := substr(replace(gen_random_uuid()::text, '-', ''), 1, 24);
  end if;
  update users
    set verified = true, secret = v_secret,
        otp_hash = null, otp_expires_at = null, otp_attempts = 0
  where phone = p_phone;
  return json_build_object('status', 'ok', 'secret', v_secret, 'phone', p_phone);
end;
$$;

revoke all on function register_user(text) from public;
revoke all on function verify_otp_code(text, text) from public;
grant execute on function register_user(text) to anon, service_role;
grant execute on function verify_otp_code(text, text) to anon, service_role;
