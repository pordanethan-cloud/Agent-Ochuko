-- Migration 025 — Agent Mode Tasks Table & Constraints
-- Implements Phase 1 Autonomous Agent Mode infrastructure.
-- Extends mode check constraints and creates the agent_tasks table with RLS.

-- 1. Update conversations table mode constraint to allow 'agent'
ALTER TABLE conversations DROP CONSTRAINT IF EXISTS conversations_mode_check;
ALTER TABLE conversations ADD CONSTRAINT conversations_mode_check 
  CHECK (mode IS NULL OR mode IN ('think','solve','discuss','agent'));

-- 2. Update messages table routing_mode constraint to allow 'agent'
ALTER TABLE messages DROP CONSTRAINT IF EXISTS messages_routing_mode_check;
ALTER TABLE messages ADD CONSTRAINT messages_routing_mode_check 
  CHECK (routing_mode IS NULL OR routing_mode IN ('think','solve','nano','discuss','summary','agent'));

-- 3. Create agent_tasks table
CREATE TABLE IF NOT EXISTS agent_tasks (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id      UUID REFERENCES conversations(id) ON DELETE CASCADE,
  user_id              UUID NOT NULL REFERENCES profiles(id) ON DELETE CASCADE,
  goal                 TEXT NOT NULL,
  plan                 JSONB DEFAULT '[]'::jsonb,
  state                TEXT NOT NULL DEFAULT 'planning'
                       CHECK (state IN ('planning','awaiting_approval','executing','paused_for_hitl','completed','failed','cancelled')),
  current_step         INT DEFAULT 0,
  step_results         JSONB DEFAULT '[]'::jsonb,
  artifacts            JSONB DEFAULT '[]'::jsonb,
  total_token_spend    INT DEFAULT 0,
  max_duration_seconds INT DEFAULT 300,
  error_message        TEXT,
  created_at           TIMESTAMPTZ DEFAULT now(),
  updated_at           TIMESTAMPTZ DEFAULT now(),
  started_at           TIMESTAMPTZ,
  completed_at         TIMESTAMPTZ
);

-- 4. Indexes for fast per-user and per-conversation lookups
CREATE INDEX IF NOT EXISTS idx_agent_tasks_user ON agent_tasks(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_agent_tasks_conversation ON agent_tasks(conversation_id);

-- 5. Row-Level Security (RLS) matching Migration 002 pattern
ALTER TABLE agent_tasks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "agent_tasks_own" ON agent_tasks;
CREATE POLICY "agent_tasks_own" ON agent_tasks
  FOR ALL USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "agent_tasks_admin" ON agent_tasks;
CREATE POLICY "agent_tasks_admin" ON agent_tasks
  FOR SELECT USING (is_admin());

-- 6. Auto-update updated_at timestamp trigger
DROP TRIGGER IF EXISTS agent_tasks_updated_at ON agent_tasks;
CREATE TRIGGER agent_tasks_updated_at
  BEFORE UPDATE ON agent_tasks
  FOR EACH ROW EXECUTE FUNCTION update_conversation_timestamp();

COMMENT ON TABLE agent_tasks IS
  'Tracks autonomous multi-step agent tasks, execution plans, step results, and artifacts.';
