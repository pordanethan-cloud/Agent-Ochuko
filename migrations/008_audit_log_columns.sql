-- Migration 008 — Audit Log Missing Columns
-- Adds columns resource_id, user_agent, and policy_reason to audit_log if they do not exist.

ALTER TABLE audit_log
  ADD COLUMN IF NOT EXISTS resource_id   UUID,
  ADD COLUMN IF NOT EXISTS user_agent    TEXT,
  ADD COLUMN IF NOT EXISTS policy_reason TEXT;

CREATE INDEX IF NOT EXISTS idx_audit_user   ON audit_log(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action, created_at DESC);
