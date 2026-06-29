-- Migration 016 — Database Constraints & Schema Fixes
-- 1. Fix conversations table mode constraint to allow 'discuss'
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_mode_check;
ALTER TABLE conversations ADD CONSTRAINT conversations_mode_check CHECK (mode IN ('think','solve','discuss'));

-- 2. Add missing latency_ms column to audit_log table
ALTER TABLE audit_log ADD COLUMN IF NOT EXISTS latency_ms INT DEFAULT 0;

-- 3. Ensure messages routing_mode constraint includes 'discuss' and 'summary'
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_routing_mode_check;
ALTER TABLE messages ADD CONSTRAINT messages_routing_mode_check CHECK (routing_mode IN ('think','solve','nano','discuss','summary'));
