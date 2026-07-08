-- Migration 022 — align_timezone_nigeria
-- Alters ensure_budget_row, check_and_deduct_budget, and reconcile_token_budget
-- to use timezone('Africa/Lagos', now())::date instead of UTC CURRENT_DATE.

-- 1. Upgraded ensure_budget_row
CREATE OR REPLACE FUNCTION ensure_budget_row(p_user_id UUID)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_limit BIGINT;
BEGIN
  -- Inherit the user's most recent custom budget_limit (preserves admin overrides)
  SELECT budget_limit INTO v_limit
  FROM token_budgets
  WHERE user_id = p_user_id
  ORDER BY period DESC
  LIMIT 1;

  -- No prior row — fall back to global default in admin_settings
  IF v_limit IS NULL THEN
    SELECT (value#>>'{}')::bigint INTO v_limit
    FROM admin_settings
    WHERE key = 'global_daily_token_budget';
  END IF;

  -- Ultimate fallback (100,000 tokens) if admin_settings row is also missing
  IF v_limit IS NULL THEN
    v_limit := 100000;
  END IF;

  -- Insert today's row (using Africa/Lagos timezone for date) — ON CONFLICT DO NOTHING preserves any admin override
  -- already set for today via the dashboard
  INSERT INTO token_budgets (user_id, period, budget_limit)
  VALUES (p_user_id, timezone('Africa/Lagos', now())::date, v_limit)
  ON CONFLICT (user_id, period) DO NOTHING;
END;
$$;


-- 2. Upgraded check_and_deduct_budget
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
    AND period   = timezone('Africa/Lagos', now())::date
    AND tokens_used + p_tokens <= budget_limit;

  GET DIAGNOSTICS v_rows_updated = ROW_COUNT;

  -- TRUE = deduction succeeded, FALSE = budget exhausted
  RETURN v_rows_updated > 0;
END;
$$;


-- 3. Upgraded reconcile_token_budget
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
    AND period   = timezone('Africa/Lagos', now())::date;
END;
$$;
