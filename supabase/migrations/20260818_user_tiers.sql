-- Migration: user_tiers + user_usage tables for server-side tier tracking
-- Created: 2026-08-18
-- Purpose: Replace in-memory tier storage with persistent database tracking

-- ─── جدول خطط المستخدمين (user_tiers) ───
CREATE TABLE IF NOT EXISTS user_tiers (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL UNIQUE,  -- JWT sub claim (user ID from Supabase Auth)
    phone TEXT,  -- رقم الهاتف الكويتي (+965XXXXXXXX)
    tier TEXT NOT NULL DEFAULT 'free',  -- free | trial | pro | enterprise
    trial_starts_at TIMESTAMPTZ,
    trial_ends_at TIMESTAMPTZ,  -- ينتهي بعد 7 أيام من التفعيل
    subscription_id TEXT,  -- معرف الاشتراك (للمدفوعات المستقبلية)
    subscription_status TEXT DEFAULT 'active',  -- active | cancelled | expired
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- قيود
    CONSTRAINT valid_tier CHECK (tier IN ('free', 'trial', 'pro', 'enterprise')),
    CONSTRAINT valid_status CHECK (subscription_status IN ('active', 'cancelled', 'expired'))
);

-- فهرس للبحث السريع
CREATE INDEX IF NOT EXISTS idx_user_tiers_user_id ON user_tiers(user_id);
CREATE INDEX IF NOT EXISTS idx_user_tiers_phone ON user_tiers(phone);
CREATE INDEX IF NOT EXISTS idx_user_tiers_tier ON user_tiers(tier);

-- ─── جدول الاستخدام اليومي (user_usage) ───
CREATE TABLE IF NOT EXISTS user_usage (
    id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
    user_id TEXT NOT NULL,
    feature TEXT NOT NULL,  -- search | comparisons | pdf_reports | etc.
    usage_date DATE NOT NULL DEFAULT CURRENT_DATE,
    count INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    -- فهرس فريد لمنع التكرار (user + feature + date)
    CONSTRAINT unique_user_feature_date UNIQUE (user_id, feature, usage_date)
);

-- فهارس للبحث السريع
CREATE INDEX IF NOT EXISTS idx_user_usage_user_id ON user_usage(user_id);
CREATE INDEX IF NOT EXISTS idx_user_usage_date ON user_usage(usage_date);
CREATE INDEX IF NOT EXISTS idx_user_usage_feature ON user_usage(feature);

-- ─── RLS Policies ───

-- تفعيل RLS
ALTER TABLE user_tiers ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_usage ENABLE ROW LEVEL SECURITY;

-- سياسة قراءة: المستخدم يقرأ خطته فقط (أو المدير عبر service role)
CREATE POLICY "Users can read own tier"
    ON user_tiers FOR SELECT
    USING (
        auth.uid()::text = user_id
        OR
        -- service role يقرأ كل شيء
        current_setting('role') = 'service_role'
    );

-- سياسة إدراج: المستخدم ينشئ خطته فقط (أو المدير)
CREATE POLICY "Users can insert own tier"
    ON user_tiers FOR INSERT
    WITH CHECK (
        auth.uid()::text = user_id
        OR
        current_setting('role') = 'service_role'
    );

-- سياسة تحديث: المستخدم يحدث خطته فقط (أو المدير)
CREATE POLICY "Users can update own tier"
    ON user_tiers FOR UPDATE
    USING (
        auth.uid()::text = user_id
        OR
        current_setting('role') = 'service_role'
    );

-- سياسة قراءة الاستخدام: المستخدم يقرأ استخدامه فقط
CREATE POLICY "Users can read own usage"
    ON user_usage FOR SELECT
    USING (
        auth.uid()::text = user_id
        OR
        current_setting('role') = 'service_role'
    );

-- سياسة إدراج الاستخدام: المستخدم يسجل استخدامه فقط
CREATE POLICY "Users can insert own usage"
    ON user_usage FOR INSERT
    WITH CHECK (
        auth.uid()::text = user_id
        OR
        current_setting('role') = 'service_role'
    );

-- سياسة تحديث الاستخدام: المستخدم يحدث استخدامه فقط (لincrement)
CREATE POLICY "Users can update own usage"
    ON user_usage FOR UPDATE
    USING (
        auth.uid()::text = user_id
        OR
        current_setting('role') = 'service_role'
    );

-- ─── Functions ───

-- دالة لزيادة عداد الاستخدام (upsert)
CREATE OR REPLACE FUNCTION increment_usage(
    p_user_id TEXT,
    p_feature TEXT,
    p_date DATE DEFAULT CURRENT_DATE
) RETURNS VOID AS $$
BEGIN
    INSERT INTO user_usage (user_id, feature, usage_date, count)
    VALUES (p_user_id, p_feature, p_date, 1)
    ON CONFLICT (user_id, feature, usage_date)
    DO UPDATE SET count = user_usage.count + 1;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- دالة لجلب عدد استخدامات اليوم
CREATE OR REPLACE FUNCTION get_daily_usage(
    p_user_id TEXT,
    p_feature TEXT,
    p_date DATE DEFAULT CURRENT_DATE
) RETURNS INTEGER AS $$
DECLARE
    usage_count INTEGER;
BEGIN
    SELECT COALESCE(count, 0) INTO usage_count
    FROM user_usage
    WHERE user_id = p_user_id 
      AND feature = p_feature 
      AND usage_date = p_date;
    
    RETURN COALESCE(usage_count, 0);
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- ─── Comments ───
COMMENT ON TABLE user_tiers IS 'خطط المستخدمين والاشتراكات (مجاني/تجريبي/محترف/مؤسسات)';
COMMENT ON TABLE user_usage IS 'عداد الاستخدام اليومي لكل ميزة (يُصفّر يومياً)';
COMMENT ON FUNCTION increment_usage IS 'زيادة عداد الاستخدام مع upsert (يمنع التكرار)';
COMMENT ON FUNCTION get_daily_usage IS 'جلب عدد استخدامات ميزة معينة في يوم محدد';
