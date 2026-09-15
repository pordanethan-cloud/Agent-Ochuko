-- Migration 030 — Agent Task scratchpad / blackboard working memory.
-- Backs AgentTask.scratchpad: structured working-memory entries
-- (facts, decisions, discoveries, artifact refs) that survive
-- save_state()/resume and get injected into step prompts and the
-- final synthesis. Capped by the task manager (30 entries, 500 chars).

ALTER TABLE agent_tasks
  ADD COLUMN IF NOT EXISTS scratchpad JSONB NOT NULL DEFAULT '{}'::jsonb;

COMMENT ON COLUMN agent_tasks.scratchpad IS
  'Blackboard working memory: {"entries": [{id, kind, content, step_index, created_at}]} — kinds: fact|decision|discovery|artifact_ref|open_question|constraint. Capped at 30 entries / 500 chars each by the task manager.';
