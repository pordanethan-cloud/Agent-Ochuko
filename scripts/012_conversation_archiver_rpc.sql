-- Migration 012 — archive_stale_conversations RPC
-- Creates helper function to soft-archive conversations older than 90 days and return the archived count.

CREATE OR REPLACE FUNCTION archive_stale_conversations()
RETURNS INT LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_count INT;
BEGIN
  WITH updated AS (
    UPDATE conversations
    SET is_archived = TRUE
    WHERE updated_at < now() - INTERVAL '90 days'
      AND is_archived = FALSE
    RETURNING id
  )
  SELECT COUNT(*) INTO v_count FROM updated;
  RETURN v_count;
END;
$$;
