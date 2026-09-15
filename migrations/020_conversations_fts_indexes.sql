-- 020_conversations_fts_indexes.sql
-- Full-text search indexes for conversation and message search.
-- Safe to run on live DB — CREATE INDEX IF NOT EXISTS is a no-op if already exists.
-- These enable Supabase textSearch() and raw SQL tsvector queries.
-- Run: paste into Supabase SQL Editor and execute.

-- Index on conversation titles (fast sidebar title search)
CREATE INDEX IF NOT EXISTS idx_conversations_fts
  ON conversations
  USING gin(to_tsvector('english', coalesce(title, '')));

-- Index on message content (deep content search)
CREATE INDEX IF NOT EXISTS idx_messages_fts
  ON messages
  USING gin(to_tsvector('english', coalesce(content, '')));

-- Verify indexes were created
SELECT
  indexname,
  tablename,
  indexdef
FROM pg_indexes
WHERE indexname IN ('idx_conversations_fts', 'idx_messages_fts');
