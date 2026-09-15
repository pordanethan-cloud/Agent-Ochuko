-- Migration 006 — usage_stats Table
-- Creates the usage_stats table for pre-computed hourly dashboard metrics.

CREATE TABLE IF NOT EXISTS usage_stats (
  period_hour    TIMESTAMPTZ,
  user_id        UUID REFERENCES profiles(id) ON DELETE CASCADE,
  model          TEXT,
  tokens_in      BIGINT DEFAULT 0,
  tokens_out     BIGINT DEFAULT 0,
  request_count  INT DEFAULT 0,
  agent_type     TEXT,
  agent_calls    INT DEFAULT 0,
  PRIMARY KEY (period_hour, user_id, model, agent_type)
);

ALTER TABLE usage_stats ENABLE ROW LEVEL SECURITY;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies WHERE tablename = 'usage_stats' AND policyname = 'usage_admin'
  ) THEN
    CREATE POLICY "usage_admin" ON usage_stats FOR SELECT USING (is_admin());
  END IF;
END $$;
