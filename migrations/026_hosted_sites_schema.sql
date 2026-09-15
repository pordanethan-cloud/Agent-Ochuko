-- Migration 026 — Hosted Static Sites Table
-- Implements Phase 2 Instant 1-Click Static Site Deployment (/sites/:id).

CREATE TABLE IF NOT EXISTS hosted_sites (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug            TEXT UNIQUE NOT NULL,
  user_id         UUID REFERENCES profiles(id) ON DELETE SET NULL,
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  title           TEXT NOT NULL DEFAULT 'Untitled Project',
  html_content    TEXT NOT NULL,
  css_content     TEXT DEFAULT '',
  js_content      TEXT DEFAULT '',
  is_public       BOOLEAN DEFAULT true,
  view_count      INT DEFAULT 0,
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Indexes for fast slug lookup and user listings
CREATE INDEX IF NOT EXISTS idx_hosted_sites_slug ON hosted_sites(slug);
CREATE INDEX IF NOT EXISTS idx_hosted_sites_user ON hosted_sites(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hosted_sites_conversation ON hosted_sites(conversation_id);

-- Enable Row-Level Security
ALTER TABLE hosted_sites ENABLE ROW LEVEL SECURITY;

-- Anyone can view public sites
DROP POLICY IF EXISTS "hosted_sites_public_read" ON hosted_sites;
CREATE POLICY "hosted_sites_public_read" ON hosted_sites
  FOR SELECT USING (is_public = true);

-- Authenticated users can manage their own sites
DROP POLICY IF EXISTS "hosted_sites_owner_all" ON hosted_sites;
CREATE POLICY "hosted_sites_owner_all" ON hosted_sites
  FOR ALL USING (auth.uid() = user_id);

-- Auto-update updated_at trigger
DROP TRIGGER IF EXISTS hosted_sites_updated_at ON hosted_sites;
CREATE TRIGGER hosted_sites_updated_at
  BEFORE UPDATE ON hosted_sites
  FOR EACH ROW EXECUTE FUNCTION update_conversation_timestamp();

COMMENT ON TABLE hosted_sites IS
  'Stores instant user & agent deployed static web apps and preview landing pages.';
