-- Migration 002 — Row-Level Security Policies
-- Enables RLS and configures access control policies using names that match the active database.

-- Enable RLS on all tables
ALTER TABLE profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;
ALTER TABLE token_budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_quotas ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE blocked_identities ENABLE ROW LEVEL SECURITY;
ALTER TABLE admin_settings ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_attributes ENABLE ROW LEVEL SECURITY;

-- Helper function: is current user an admin?
CREATE OR REPLACE FUNCTION is_admin()
RETURNS BOOLEAN AS $$
  SELECT EXISTS (
    SELECT 1 FROM profiles
    WHERE id = auth.uid()
    AND role IN ('admin', 'superadmin')
  );
$$ LANGUAGE sql SECURITY DEFINER;

-- PROFILES policies
CREATE POLICY "profiles_own" ON profiles
  FOR SELECT USING (auth.uid() = id);

CREATE POLICY "profiles_admin_all" ON profiles
  FOR SELECT USING (is_admin());

CREATE POLICY "profiles_own_update" ON profiles
  FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "profiles_admin_update" ON profiles
  FOR UPDATE USING (is_admin());

-- CONVERSATIONS policies
CREATE POLICY "convos_own" ON conversations
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "convos_shared" ON conversations
  FOR SELECT USING (is_shared = TRUE);

CREATE POLICY "convos_admin" ON conversations
  FOR SELECT USING (is_admin());

-- MESSAGES policies
CREATE POLICY "msgs_own" ON messages
  FOR ALL USING (
    conversation_id IN (
      SELECT id FROM conversations WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "msgs_shared" ON messages
  FOR SELECT USING (
    conversation_id IN (
      SELECT id FROM conversations WHERE is_shared = TRUE
    )
  );

-- TOKEN BUDGETS policies
CREATE POLICY "budget_own" ON token_budgets
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "budget_admin" ON token_budgets
  FOR ALL USING (is_admin());

-- AUDIT LOG policies
CREATE POLICY "audit_admin" ON audit_log
  FOR SELECT USING (is_admin());

-- ADMIN SETTINGS policies
CREATE POLICY "settings_admin" ON admin_settings
  FOR ALL USING (is_admin());

CREATE POLICY "settings_maintenance" ON admin_settings
  FOR SELECT USING (key = 'maintenance_mode');

-- BLOCKED IDENTITIES policies
CREATE POLICY "blocked_admin" ON blocked_identities
  FOR ALL USING (is_admin());
