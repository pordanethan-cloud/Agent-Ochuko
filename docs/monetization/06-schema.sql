-- ============================================================================
-- 023_monetization_core.sql
-- Two-tier access model: renter (donate quota) / subscriber (pay) / admin.
-- No trial tier. access_tier defaults to NULL — signup does not grant access.
-- ============================================================================

-- ─── profiles: access tier + renter onboarding state ───────────────────────

ALTER TABLE profiles
  ADD COLUMN access_tier TEXT
    CHECK (access_tier IN ('renter', 'subscriber', 'admin'))
    DEFAULT NULL;

ALTER TABLE profiles
  ADD COLUMN renter_onboarding_status TEXT
    DEFAULT NULL
    CHECK (renter_onboarding_status IS NULL OR renter_onboarding_status IN
      ('pending_setup', 'validating', 'active', 'failed', 'suspended'));

COMMENT ON COLUMN profiles.renter_onboarding_status IS
  'NULL for subscribers and unfinished signups. pending_setup only when signup_type=renter.';

COMMENT ON COLUMN profiles.access_tier IS
  'NULL until a renter completes Azure registration or a subscriber''s payment clears. Never defaulted to a non-null value.';

-- ─── renter_setup_tokens: one-time tokens for the local setup script ───────

CREATE TABLE renter_setup_tokens (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,   -- SHA-256 hash; plaintext token shown once, never stored
    expires_at TIMESTAMPTZ NOT NULL,   -- created_at + 24h
    used_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_renter_setup_tokens_user ON renter_setup_tokens(user_id);
CREATE INDEX idx_renter_setup_tokens_hash ON renter_setup_tokens(token_hash);

-- ─── capacity_providers: platform's own deployment + each renter's row ─────

CREATE TABLE capacity_providers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    type TEXT NOT NULL CHECK (type IN ('platform', 'renter')),
    owner_id UUID REFERENCES profiles(id),  -- NULL for the platform's own deployment
    azure_endpoint TEXT NOT NULL,
    azure_key_encrypted TEXT NOT NULL,       -- AES-256-GCM, master key in env/App Config
    deployment_mapping JSONB DEFAULT '{"nano": "gpt-5.4-nano"}',
    region TEXT,
    quota_limit_usd DECIMAL(10,2) NOT NULL,
    quota_used_usd DECIMAL(10,2) DEFAULT 0.00,
    quota_reset_date DATE NOT NULL,
    priority INT DEFAULT 0,          -- higher = preferred; platform rows typically 100
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_capacity_providers_owner ON capacity_providers(owner_id);
CREATE INDEX idx_capacity_providers_active ON capacity_providers(is_active) WHERE is_active = true;

-- ─── usage_log: shared across both tiers for cost + abuse reporting ────────

CREATE TABLE usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    capacity_provider_id UUID REFERENCES capacity_providers(id) NOT NULL,
    user_id UUID REFERENCES profiles(id) NOT NULL,
    conversation_id UUID REFERENCES conversations(id),
    tokens_input INT NOT NULL,
    tokens_output INT NOT NULL,
    model TEXT NOT NULL,
    cost_usd DECIMAL(10,4) NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_usage_log_provider ON usage_log(capacity_provider_id);
CREATE INDEX idx_usage_log_user ON usage_log(user_id);
CREATE INDEX idx_usage_log_timestamp ON usage_log(timestamp);

-- ─── subscriptions: subscriber payment state, source of truth for access ──

CREATE TABLE subscriptions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID REFERENCES profiles(id) UNIQUE NOT NULL,
    provider TEXT NOT NULL,              -- 'paystack' | 'flutterwave' | 'stripe'
    provider_customer_id TEXT NOT NULL,
    provider_subscription_id TEXT,
    status TEXT DEFAULT 'inactive'
      CHECK (status IN ('inactive', 'active', 'past_due', 'canceled')),
    plan_amount_usd DECIMAL(10,2) NOT NULL,
    current_period_end TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_subscriptions_user ON subscriptions(user_id);
CREATE INDEX idx_subscriptions_status ON subscriptions(status);

-- ============================================================================
-- Row Level Security
-- ============================================================================

ALTER TABLE renter_setup_tokens ENABLE ROW LEVEL SECURITY;
ALTER TABLE capacity_providers ENABLE ROW LEVEL SECURITY;
ALTER TABLE usage_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE subscriptions ENABLE ROW LEVEL SECURITY;

-- Renters can only see their own setup tokens
CREATE POLICY renter_setup_tokens_own ON renter_setup_tokens
  FOR SELECT USING (user_id = auth.uid());

-- Renters can only see their own capacity provider row; admins see all
CREATE POLICY capacity_providers_own ON capacity_providers
  FOR SELECT USING (
    owner_id = auth.uid()
    OR EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'superadmin'))
  );

-- Renters can only see their own usage rows; admins see all
CREATE POLICY usage_log_own ON usage_log
  FOR SELECT USING (
    user_id = auth.uid()
    OR EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'superadmin'))
  );

-- Subscribers can only see their own subscription; admins see all
CREATE POLICY subscriptions_own ON subscriptions
  FOR SELECT USING (
    user_id = auth.uid()
    OR EXISTS (SELECT 1 FROM profiles WHERE id = auth.uid() AND role IN ('admin', 'superadmin'))
  );

-- ============================================================================
-- Seed: platform's own capacity row (migrate existing AZURE_OPENAI_* env values)
-- Run manually with real values — placeholders below.
-- ============================================================================

-- INSERT INTO capacity_providers (
--   type, owner_id, azure_endpoint, azure_key_encrypted,
--   deployment_mapping, quota_limit_usd, quota_reset_date, priority
-- ) VALUES (
--   'platform', NULL, '<AZURE_OPENAI_ENDPOINT>', '<encrypted AZURE_OPENAI_API_KEY>',
--   '{"nano": "gpt-5.4-nano", "standard": "gpt-5.4"}',
--   <monthly_budget_usd>, date_trunc('month', now()) + interval '1 month', 100
-- );
