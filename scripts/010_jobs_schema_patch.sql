-- Migration 010 (C4) — Jobs Table Schema Patch
-- Adds missing columns (input_metadata, result_blob_url, queue_message_id, retry_count) to the jobs table.

ALTER TABLE jobs
  ADD COLUMN IF NOT EXISTS input_metadata   JSONB,
  ADD COLUMN IF NOT EXISTS result_blob_url  TEXT,
  ADD COLUMN IF NOT EXISTS queue_message_id TEXT,
  ADD COLUMN IF NOT EXISTS retry_count      INT DEFAULT 0;

-- Migrate existing blob_url data if needed
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns 
    WHERE table_name='jobs' AND column_name='blob_url'
  ) THEN
    UPDATE jobs SET input_metadata = jsonb_build_object('blob_url', blob_url) WHERE blob_url IS NOT NULL;
    ALTER TABLE jobs DROP COLUMN IF EXISTS blob_url;
  END IF;
END $$;
