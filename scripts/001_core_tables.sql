-- Migration 001 — Core Tables
-- Creates all core database tables, triggers, and helper functions for Agent Ochuko.

-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- PROFILES (extends Supabase auth.users)
CREATE TABLE IF NOT EXISTS profiles (
  id UUID PRIMARY KEY REFERENCES auth.users ON DELETE CASCADE,
  display_name TEXT,
  avatar_url TEXT,
  role TEXT DEFAULT 'user' CHECK (role IN ('guest','user','power_user','admin','superadmin')),
  is_active BOOLEAN DEFAULT TRUE,
  google_sub TEXT UNIQUE,
  device_fingerprint TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now()
);

-- AUTO-CREATE PROFILE ON SIGNUP
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, display_name, avatar_url, google_sub)
  VALUES (
    NEW.id,
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'avatar_url',
    NEW.raw_user_meta_data->>'provider_id'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Trigger to run on auth.users insert
CREATE OR REPLACE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- BLOCKED IDENTITIES
CREATE TABLE IF NOT EXISTS blocked_identities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  google_sub TEXT UNIQUE NOT NULL,
  email TEXT,
  blocked_by UUID REFERENCES profiles(id),
  reason TEXT,
  blocked_at TIMESTAMPTZ DEFAULT now()
);

-- ADMIN SETTINGS
CREATE TABLE IF NOT EXISTS admin_settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_by UUID REFERENCES profiles(id),
  updated_at TIMESTAMPTZ DEFAULT now()
);

-- Seed basic settings
INSERT INTO admin_settings (key, value) VALUES
  ('registration_limit', '100'::jsonb),
  ('registration_open', 'true'::jsonb),
  ('maintenance_mode', 'false'::jsonb),
  ('global_daily_token_budget', '100000'::jsonb)
ON CONFLICT (key) DO NOTHING;

-- CONVERSATIONS
CREATE TABLE IF NOT EXISTS conversations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES profiles(id) ON DELETE CASCADE,
  title           TEXT DEFAULT 'New Chat',
  model           TEXT DEFAULT 'gpt-5.4-nano',
  mode            TEXT DEFAULT 'discuss' CHECK (mode IN ('think','solve','discuss')),
  nano_turn_count INT  DEFAULT 0,
  agent_type      TEXT DEFAULT 'chat',
  system_prompt   TEXT,
  is_archived     BOOLEAN DEFAULT FALSE,
  is_shared       BOOLEAN DEFAULT FALSE,
  share_token     TEXT UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
  message_count   INT DEFAULT 0,
  last_compacted_at TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Auto-update updated_at timestamp trigger function
CREATE OR REPLACE FUNCTION update_conversation_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

-- Trigger to run on conversations update
CREATE OR REPLACE TRIGGER conversations_updated_at
  BEFORE UPDATE ON conversations
  FOR EACH ROW EXECUTE FUNCTION update_conversation_timestamp();

-- Atomic nano_turn_count increment RPC
CREATE OR REPLACE FUNCTION increment_nano_turns(conv_id UUID)
RETURNS VOID LANGUAGE sql AS $$
  UPDATE conversations
  SET nano_turn_count = nano_turn_count + 1
  WHERE id = conv_id;
$$;

-- MESSAGES
CREATE TABLE IF NOT EXISTS messages (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id  UUID REFERENCES conversations(id) ON DELETE CASCADE,
  role             TEXT CHECK (role IN ('user','assistant','system','tool')),
  content          TEXT,
  content_parts    JSONB,
  response_id      TEXT,
  model            TEXT,
  routing_mode     TEXT CHECK (routing_mode IN ('think','solve','nano','summary')),
  routing_reason   TEXT,
  is_summary       BOOLEAN DEFAULT FALSE,
  is_archived_msg  BOOLEAN DEFAULT FALSE,
  tokens_input     INT DEFAULT 0,
  tokens_output    INT DEFAULT 0,
  latency_ms       INT DEFAULT 0,
  is_error         BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON messages(conversation_id, created_at);

-- TOKEN BUDGETS
CREATE TABLE IF NOT EXISTS token_budgets (
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  period DATE DEFAULT CURRENT_DATE,
  tokens_used BIGINT DEFAULT 0,
  budget_limit BIGINT DEFAULT 100000,
  PRIMARY KEY (user_id, period)
);

-- AGENT QUOTAS
CREATE TABLE IF NOT EXISTS agent_quotas (
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  period TEXT,
  ocr_pages_used INT DEFAULT 0,
  vision_calls_used INT DEFAULT 0,
  speech_seconds_used INT DEFAULT 0,
  image_gen_used INT DEFAULT 0,
  PRIMARY KEY (user_id, period)
);

-- AUDIT LOG
CREATE TABLE IF NOT EXISTS audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES profiles(id),
  action TEXT NOT NULL,
  resource_type TEXT,
  metadata JSONB,
  policy_decision TEXT CHECK (policy_decision IN ('ALLOW','DENY')),
  policy_reason TEXT,
  ip_address TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- USER ATTRIBUTES
CREATE TABLE IF NOT EXISTS user_attributes (
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  key TEXT,
  value JSONB,
  PRIMARY KEY (user_id, key)
);

-- ACCESS POLICIES
CREATE TABLE IF NOT EXISTS access_policies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  resource_type TEXT,
  conditions JSONB,
  effect TEXT CHECK (effect IN ('allow','deny')),
  priority INT DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE
);
