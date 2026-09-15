-- Migration 017 — Top Users RPC
-- Creates the public.get_top_users_by_tokens function to aggregate token consumption in-database.

CREATE OR REPLACE FUNCTION get_top_users_by_tokens(p_limit INT)
RETURNS TABLE (
  user_id UUID,
  display_name TEXT,
  email TEXT,
  total_tokens BIGINT
) LANGUAGE plpgsql SECURITY DEFINER AS $$
BEGIN
  RETURN QUERY
  WITH user_token_sums AS (
    SELECT 
      c.user_id,
      SUM(COALESCE(m.tokens_input, 0) + COALESCE(m.tokens_output, 0))::BIGINT as total_tokens
    FROM messages m
    JOIN conversations c ON m.conversation_id = c.id
    WHERE m.role = 'assistant'
    GROUP BY c.user_id
  )
  SELECT 
    uts.user_id,
    p.display_name,
    NULL::TEXT as email, -- Responding email is resolved from auth metadata in app services
    uts.total_tokens
  FROM user_token_sums uts
  LEFT JOIN profiles p ON uts.user_id = p.id
  ORDER BY uts.total_tokens DESC
  LIMIT p_limit;
END;
$$;
