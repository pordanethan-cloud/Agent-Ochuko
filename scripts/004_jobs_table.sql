-- Migration 004 — Jobs Table
-- Creates the jobs table for tracking background agent task execution and enables RLS.

CREATE TABLE IF NOT EXISTS jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES profiles(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  type            TEXT NOT NULL CHECK (type IN ('ocr','vision','speech','image_gen','file_gen')),
  status          TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','done','failed')),
  result          JSONB,
  error           TEXT,
  blob_url        TEXT,
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_jobs_conversation ON jobs(conversation_id);

-- RLS
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

-- Policies aligned with database naming conventions
CREATE POLICY "jobs_own" ON jobs
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "jobs_admin" ON jobs
  FOR SELECT USING (is_admin());
