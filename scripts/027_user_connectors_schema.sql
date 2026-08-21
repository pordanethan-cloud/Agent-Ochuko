-- 027_user_connectors_schema.sql
-- Migration for User Connectors (MCP servers, Google APIs, OAuth integrations)

CREATE TABLE IF NOT EXISTS public.user_connectors (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL,
    connector_name TEXT NOT NULL,
    connector_type TEXT NOT NULL DEFAULT 'mcp'
        CHECK (connector_type IN ('mcp', 'google_api', 'oauth2', 'custom')),
    access_token_encrypted TEXT,
    refresh_token_encrypted TEXT,
    token_expiry TIMESTAMPTZ,
    scopes TEXT[] DEFAULT '{}',
    permissions TEXT[] DEFAULT '{"read"}', -- e.g. "read", "write", "delete"
    review_policy TEXT NOT NULL DEFAULT 'always_ask'
        CHECK (review_policy IN ('always_ask', 'always_proceed')),
    is_active BOOLEAN DEFAULT true,
    config_json JSONB DEFAULT '{}'::jsonb, -- MCP-specific config (e.g. command, args, url)
    connected_at TIMESTAMPTZ DEFAULT now(),
    last_used_at TIMESTAMPTZ,
    UNIQUE(user_id, connector_name)
);

ALTER TABLE public.user_connectors ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can manage their own connectors"
    ON public.user_connectors
    FOR ALL
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS idx_user_connectors_user_active 
    ON public.user_connectors(user_id, is_active);

CREATE INDEX IF NOT EXISTS idx_user_connectors_name 
    ON public.user_connectors(connector_name);
