-- Migration 011 — aggregate_hourly_usage RPC
-- Creates helper function to aggregate hourly token consumption and agent calls from messages and jobs.

CREATE OR REPLACE FUNCTION aggregate_hourly_usage(p_start TIMESTAMPTZ, p_end TIMESTAMPTZ)
RETURNS VOID LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  -- 1. Insert/Upsert stats from messages
  INSERT INTO usage_stats (period_hour, user_id, model, tokens_in, tokens_out, request_count, agent_type, agent_calls)
  SELECT 
    date_trunc('hour', m.created_at) as period_hour,
    c.user_id,
    COALESCE(m.model, 'unknown') as model,
    SUM(COALESCE(m.tokens_input, 0))::bigint as tokens_in,
    SUM(COALESCE(m.tokens_output, 0))::bigint as tokens_out,
    COUNT(m.id)::int as request_count,
    'chat' as agent_type,
    0 as agent_calls
  FROM messages m
  JOIN conversations c ON m.conversation_id = c.id
  WHERE m.created_at >= p_start AND m.created_at < p_end
  GROUP BY 1, 2, 3
  ON CONFLICT (period_hour, user_id, model, agent_type) 
  DO UPDATE SET
    tokens_in = EXCLUDED.tokens_in,
    tokens_out = EXCLUDED.tokens_out,
    request_count = EXCLUDED.request_count;

  -- 2. Insert/Upsert stats from jobs
  INSERT INTO usage_stats (period_hour, user_id, model, tokens_in, tokens_out, request_count, agent_type, agent_calls)
  SELECT 
    date_trunc('hour', j.created_at) as period_hour,
    j.user_id,
    'agent' as model,
    0::bigint as tokens_in,
    0::bigint as tokens_out,
    0::int as request_count,
    j.type as agent_type,
    COUNT(j.id)::int as agent_calls
  FROM jobs j
  WHERE j.created_at >= p_start AND j.created_at < p_end
  GROUP BY 1, 2, 3, 7
  ON CONFLICT (period_hour, user_id, model, agent_type) 
  DO UPDATE SET
    agent_calls = EXCLUDED.agent_calls;
END;
$$;
