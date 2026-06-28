-- Migration 014 — check_and_deduct_budget RPC
-- Called by the TokenBudgetMiddleware before every chat stream.
-- Atomically checks if the user has sufficient budget and deducts tokens.
-- Returns TRUE if deduction succeeded, FALSE if budget is exhausted.
--
-- Why atomic?
--   Without this, two simultaneous requests could both read "budget ok"
--   then both deduct — allowing spend beyond the limit.
--   The UPDATE with WHERE guard ensures only one wins.

CREATE OR REPLACE FUNCTION check_and_deduct_budget(
  p_user_id UUID,
  p_tokens  BIGINT
)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  v_rows_updated INT;
BEGIN
  UPDATE token_budgets
  SET tokens_used = tokens_used + p_tokens
  WHERE user_id  = p_user_id
    AND period   = CURRENT_DATE
    AND tokens_used + p_tokens <= budget_limit;

  GET DIAGNOSTICS v_rows_updated = ROW_COUNT;

  -- TRUE = deduction succeeded, FALSE = budget exhausted
  RETURN v_rows_updated > 0;
END;
$$;
