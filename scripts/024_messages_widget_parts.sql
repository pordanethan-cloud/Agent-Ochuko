-- 024_messages_widget_parts.sql
-- Implements plan §8.4: widget block persistence in messages.content_parts.
--
-- The `content_parts` JSONB column already exists (Migration 001).
-- Widget blocks are written by the backend when visualize__show_widget fires
-- during an agent turn. On conversation reload the frontend reads them back
-- and re-renders without re-calling the API.
--
-- Widget block schema stored under content_parts -> 'widgets':
--   [
--     {
--       "type":  "widget",
--       "title": "auth_flow_diagram",          -- snake_case identifier
--       "mode":  "svg" | "html",               -- auto-detected from code
--       "code":  "<svg ...> | <div ...>",      -- raw render payload
--       "widget_type": "diagram"               -- module hint for the header badge
--     },
--     ...
--   ]
--
-- Safe to run multiple times (IF NOT EXISTS / OR REPLACE guards).

-- 1. GIN index on content_parts for fast JSONB containment queries.
--    Already created if 021_generated_files_table or similar ran it;
--    the IF NOT EXISTS guard makes this idempotent.
CREATE INDEX IF NOT EXISTS idx_messages_content_parts_gin
  ON messages USING GIN (content_parts);

-- 2. Focused expression index on just the widgets array — useful for
--    admin queries like "find all messages that contain widgets".
CREATE INDEX IF NOT EXISTS idx_messages_content_parts_widgets
  ON messages USING GIN ((content_parts -> 'widgets'));

-- 3. Update the column comment to document all known content_parts keys
--    (additive — does not change any data).
COMMENT ON COLUMN messages.content_parts IS
  'Structured metadata for the assistant message. Known keys:
   - thinking_content  TEXT      Reasoning chain from THINK/SOLVE modes
   - image_jobs        JSONB[]   Queued image generation job IDs
   - generated_files   JSONB[]   [{filename, download_url, size_bytes}]
   - widgets           JSONB[]   [{type:"widget", title, mode, code, widget_type}]
                                 Written by visualize__show_widget. Re-rendered
                                 on history reload without re-calling the API.';
