-- Migration 007 — ensure_budget_row RPC
-- Creates helper function to ensure a budget record exists for a user on the current day.

CREATE OR REPLACE FUNCTION ensure_budget_row(p_user_id UUID)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  INSERT INTO token_budgets (user_id, period, budget_limit)
  VALUES (
    p_user_id,
    CURRENT_DATE,
    (SELECT (value#>>'{}')::bigint FROM admin_settings WHERE key = 'global_daily_token_budget')
  )
  ON CONFLICT (user_id, period) DO NOTHING;
END;
$$;
