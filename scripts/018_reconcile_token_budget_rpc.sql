-- Migration 018 — reconcile_token_budget RPC
-- Reconciles estimated pre-deductions with actual token counts after the stream completes.
-- Safely increments/decrements tokens_used ensuring it never drops below 0.

CREATE OR REPLACE FUNCTION reconcile_token_budget(
  p_user_id UUID,
  p_diff     BIGINT
)
RETURNS VOID
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  UPDATE token_budgets
  SET tokens_used = GREATEST(0, tokens_used + p_diff)
  WHERE user_id  = p_user_id
    AND period   = CURRENT_DATE;
END;
$$;
