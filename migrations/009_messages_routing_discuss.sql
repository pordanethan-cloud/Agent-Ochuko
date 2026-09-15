-- Migration 009 — messages.routing_mode Constraints
-- Modifies the check constraint on routing_mode to include 'discuss', and adds routing_reason.

ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_routing_mode_check;

ALTER TABLE messages ADD CONSTRAINT messages_routing_mode_check
  CHECK (routing_mode IN ('think','solve','nano','discuss','summary'));

ALTER TABLE messages ADD COLUMN IF NOT EXISTS routing_reason TEXT;
