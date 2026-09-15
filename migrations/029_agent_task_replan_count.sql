-- Migration 029 — Agent Task re-plan budget (Phase 8 long-horizon re-orientation).
-- Backs AgentTask.replan_count, which survives save_state()/resume.

ALTER TABLE agent_tasks ADD COLUMN IF NOT EXISTS replan_count INT NOT NULL DEFAULT 0;

COMMENT ON COLUMN agent_tasks.replan_count IS
  'Number of dynamic plan re-orientations executed for this task (budget-capped via AGENT_MODE_MAX_REPLANS).';
