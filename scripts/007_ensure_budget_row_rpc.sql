-- Migration 007 — ensure_budget_row RPC (upgraded)
-- Ensures a token budget row exists for a user on the current day.
-- Inheritance order:
--   1. User's own budget_limit from their most recent previous row (preserves admin overrides)
--   2. Global default from admin_settings.global_daily_token_budget
--   3. Hardcoded fallback: 100,000 tokens

CREATE OR REPLACE FUNCTION ensure_budget_row(p_user_id UUID)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
DECLARE
  v_limit BIGINT;
BEGIN
  -- 1. Inherit the user's most recent custom budget_limit (preserves admin overrides)
  SELECT budget_limit INTO v_limit
  FROM token_budgets
  WHERE user_id = p_user_id
  ORDER BY period DESC
  LIMIT 1;

  -- 2. No prior row — fall back to global default in admin_settings
  IF v_limit IS NULL THEN
    SELECT (value#>>'{}')::bigint INTO v_limit
    FROM admin_settings
    WHERE key = 'global_daily_token_budget';
  END IF;

  -- 3. Ultimate fallback (100,000 tokens) if admin_settings row is also missing
  IF v_limit IS NULL THEN
    v_limit := 100000;
  END IF;

  -- 4. Insert today's row — ON CONFLICT DO NOTHING preserves any admin override
  --    already set for today via the dashboard
  INSERT INTO token_budgets (user_id, period, budget_limit)
  VALUES (p_user_id, CURRENT_DATE, v_limit)
  ON CONFLICT (user_id, period) DO NOTHING;
END;
$$;
