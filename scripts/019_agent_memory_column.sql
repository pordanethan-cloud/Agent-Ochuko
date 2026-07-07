-- 019_agent_memory_column.sql
-- Adds the agent_memory JSONB column to conversations.
-- This column stores key-value facts written by the write_memory tool during
-- agentic loop execution. It is loaded and injected into every LLM context
-- turn via build_llm_context so the model always sees its remembered state.
--
-- Safe to run multiple times (IF NOT EXISTS guard).

ALTER TABLE conversations
  ADD COLUMN IF NOT EXISTS agent_memory JSONB NOT NULL DEFAULT '{}';

-- Index enables fast lookup / partial queries on specific memory keys
-- (e.g. WHERE agent_memory ? 'user_goal') if needed in future admin queries.
CREATE INDEX IF NOT EXISTS idx_conversations_agent_memory_gin
  ON conversations USING GIN (agent_memory);

COMMENT ON COLUMN conversations.agent_memory IS
  'Key-value store written by the write_memory agent tool during OODA loop execution.
   Injected as a system context block into every LLM turn. Schema: {key: string, value: string}.';
