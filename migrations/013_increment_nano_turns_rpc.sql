-- Migration 013 — increment_nano_turns RPC
-- Atomic counter for the Model Router's silent Nano interceptor.
-- Called every time model_router decides to use gpt-5.4-nano instead of
-- the requested THINK/SOLVE deployment (silent nano turn).
-- Resets nano_turn_count to 0 once NANO_MAX_TURNS threshold is reached
-- so the next batch of turns starts fresh.
--
-- Called by: backend/app/core/model_router.py on every nano-intercepted message
-- Table:     conversations.nano_turn_count (INT DEFAULT 0)

CREATE OR REPLACE FUNCTION increment_nano_turns(
  p_conv_id        UUID,
  p_nano_max_turns INT DEFAULT 3
)
RETURNS INT        -- returns the NEW nano_turn_count after increment/reset
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_new_count INT;
BEGIN
  UPDATE conversations
  SET nano_turn_count = CASE
    -- If we've reached the max, reset to 0 so next turn uses full model
    WHEN nano_turn_count + 1 >= p_nano_max_turns THEN 0
    ELSE nano_turn_count + 1
  END
  WHERE id = p_conv_id
  RETURNING nano_turn_count INTO v_new_count;

  RETURN COALESCE(v_new_count, 0);
END;
$$;
