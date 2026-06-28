# Phase 0 — Step 3: Supabase Project Setup

> **Goal**: Create your Supabase project, enable Google OAuth, and collect all credentials.
> **Time estimate**: 20–30 minutes
> **Where**: [https://supabase.com/dashboard](https://supabase.com/dashboard)

---

## Why Supabase (Not Azure AD B2C)?

| | Supabase Auth | Azure AD B2C |
|---|---|---|
| Cost | Free for this scale | Adds Azure billing complexity |
| Integration | Native with the DB (RLS uses `auth.uid()` directly) | Requires token bridging |
| Google OAuth setup | Simple — done in < 10 minutes | Complex custom user flows |
| Learning value | Row-Level Security + JWT = real-world security | Enterprise-only pattern |
| **Decision** | ✅ **Use this** | ❌ Skip |

---

## Step 1 — Create Supabase Account + Project

1. Go to [https://supabase.com](https://supabase.com) → **"Start your project"**
2. Sign in with GitHub (recommended — free and easy)
3. Once in the dashboard, click **"New project"**
4. Fill in:
   - **Organization**: your personal org (created automatically)
   - **Name**: `agent-ochuko`
   - **Database Password**: generate a strong one → **SAVE IT** (you'll need it)
   - **Region**: `South Africa (Cape Town)` — closest to your Azure region
   - **Pricing plan**: `Free`
5. Click **"Create new project"** → wait 1–2 minutes

> [!IMPORTANT]
> The Free tier gives you: 500MB database, 1GB file storage, 50,000 monthly active users, unlimited API requests. This is more than enough.

---

## Step 2 — Collect Your Project Credentials

1. In your project dashboard, go to **Settings** (gear icon, bottom left)
2. Click **"API"** in the left menu
3. Write down:

```
SUPABASE_URL=https://<your-project-ref>.supabase.co
SUPABASE_ANON_KEY=eyJ...  (this is public — safe for frontend)
SUPABASE_SERVICE_ROLE_KEY=eyJ...  (PRIVATE — backend only, never expose)
```

4. Now go to **Settings** → **"Configuration"** → **"API"** → scroll to **"JWT Settings"**
5. Write down:
```
SUPABASE_JWT_SECRET=<your jwt secret>
```

> [!CAUTION]
> The `SERVICE_ROLE_KEY` bypasses Row-Level Security. It goes only in Azure Key Vault and your backend. NEVER put it in the frontend.

---

## Step 3 — Enable Google OAuth

### Part A — Google Cloud Console Setup

> If you've done this before, this is quick.

1. Go to [https://console.cloud.google.com](https://console.cloud.google.com)
2. Create a new project (or use an existing one):
   - Project name: `Agent Ochuko`
3. In the left menu: **APIs & Services** → **"OAuth consent screen"**
4. Select **"External"** → **Create**
5. Fill in:
   - **App name**: `Agent Ochuko`
   - **User support email**: your email
   - **Developer contact email**: your email
6. Click **Save and Continue** through the scopes (no special scopes needed — just basic profile + email)
7. Add yourself as a test user
8. Go back: **APIs & Services** → **"Credentials"**
9. Click **"+ Create Credentials"** → **"OAuth 2.0 Client IDs"**
10. **Application type**: `Web application`
11. **Name**: `Agent Ochuko Web`
12. **Authorized redirect URIs** — add these:
    ```
    https://<your-project-ref>.supabase.co/auth/v1/callback
    http://localhost:5173/auth/callback   (for local dev)
    https://agent-ochuko.azurestaticapps.net/auth/callback  (your production URL)
    ```
13. Click **Create**
14. Copy:
    ```
    GOOGLE_CLIENT_ID=<your client id>.apps.googleusercontent.com
    GOOGLE_CLIENT_SECRET=GOCSPX-<your secret>
    ```

### Part B — Add Google to Supabase

1. Back in Supabase → **Authentication** (left menu) → **"Providers"**
2. Find **Google** → click to expand → toggle **Enabled**
3. Paste:
   - **Client ID**: your Google Client ID
   - **Client Secret**: your Google Client Secret
4. Click **Save**
5. Copy the **Callback URL** shown (it's `https://<ref>.supabase.co/auth/v1/callback`) — make sure it matches what you put in Google Console

---

## Step 4 — Configure Auth Settings

1. Supabase → **Authentication** → **"URL Configuration"**
2. Set:
   - **Site URL**: `http://localhost:5173` (for now; update when deployed)
   - **Redirect URLs** (allow list): add
     ```
     http://localhost:5173/**
     https://agent-ochuko.azurestaticapps.net/**
     https://agent-ochuko-admin.azurestaticapps.net/**
     ```
3. **Save**

---

## Step 5 — Create the Database Schema

We'll run SQL directly in the Supabase SQL Editor now to set up your tables.

1. Supabase → **SQL Editor** (left menu) → **"New query"**
2. Copy and run each migration below (one at a time, click **Run** after each):

### Migration 001 — Core Tables

```sql
-- Enable UUID extension
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- PROFILES (extends Supabase auth.users)
CREATE TABLE profiles (
  id UUID PRIMARY KEY REFERENCES auth.users ON DELETE CASCADE,
  display_name TEXT,
  avatar_url TEXT,
  role TEXT DEFAULT 'user' CHECK (role IN ('guest','user','power_user','admin','superadmin')),
  is_active BOOLEAN DEFAULT TRUE,
  google_sub TEXT UNIQUE,
  device_fingerprint TEXT,
  created_at TIMESTAMPTZ DEFAULT now(),
  last_seen TIMESTAMPTZ DEFAULT now()
);

-- AUTO-CREATE PROFILE ON SIGNUP
CREATE OR REPLACE FUNCTION handle_new_user()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO profiles (id, display_name, avatar_url, google_sub)
  VALUES (
    NEW.id,
    NEW.raw_user_meta_data->>'full_name',
    NEW.raw_user_meta_data->>'avatar_url',
    NEW.raw_user_meta_data->>'provider_id'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION handle_new_user();

-- BLOCKED IDENTITIES
CREATE TABLE blocked_identities (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  google_sub TEXT UNIQUE NOT NULL,
  email TEXT,
  blocked_by UUID REFERENCES profiles(id),
  reason TEXT,
  blocked_at TIMESTAMPTZ DEFAULT now()
);

-- ADMIN SETTINGS
CREATE TABLE admin_settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_by UUID REFERENCES profiles(id),
  updated_at TIMESTAMPTZ DEFAULT now()
);

INSERT INTO admin_settings (key, value) VALUES
  ('registration_limit', '100'::jsonb),
  ('registration_open', 'true'::jsonb),
  ('maintenance_mode', 'false'::jsonb),
  ('global_daily_token_budget', '100000'::jsonb);

-- CONVERSATIONS
CREATE TABLE conversations (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES profiles(id) ON DELETE CASCADE,
  title           TEXT DEFAULT 'New Chat',
  model           TEXT DEFAULT 'gpt-5.4-nano',
  mode            TEXT DEFAULT 'discuss' CHECK (mode IN ('think','solve','discuss')),
  nano_turn_count INT  DEFAULT 0,               -- resets after NANO_MAX_TURNS
  agent_type      TEXT DEFAULT 'chat',
  system_prompt   TEXT,
  is_archived     BOOLEAN DEFAULT FALSE,
  is_shared       BOOLEAN DEFAULT FALSE,
  share_token     TEXT UNIQUE DEFAULT encode(gen_random_bytes(16), 'hex'),
  message_count   INT DEFAULT 0,                -- increment on each message; triggers compaction
  last_compacted_at TIMESTAMPTZ,               -- when compaction last ran on this conversation
  created_at      TIMESTAMPTZ DEFAULT now(),
  updated_at      TIMESTAMPTZ DEFAULT now()
);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_conversation_timestamp()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;

CREATE TRIGGER conversations_updated_at
  BEFORE UPDATE ON conversations
  FOR EACH ROW EXECUTE FUNCTION update_conversation_timestamp();

-- Atomic nano_turn_count increment — safe under concurrent requests
CREATE OR REPLACE FUNCTION increment_nano_turns(conv_id UUID)
RETURNS VOID LANGUAGE sql AS $$
  UPDATE conversations
  SET nano_turn_count = nano_turn_count + 1
  WHERE id = conv_id;
$$;

-- MESSAGES
CREATE TABLE messages (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id  UUID REFERENCES conversations(id) ON DELETE CASCADE,
  role             TEXT CHECK (role IN ('user','assistant','system','tool')),
  content          TEXT,
  content_parts    JSONB,                       -- [{type:"text",text:"..."},{type:"image_url",url:"..."}]
  response_id      TEXT,                        -- Azure OpenAI Responses API response ID
  model            TEXT,                        -- actual deployment used (e.g. gpt-5.4)
  routing_mode     TEXT CHECK (routing_mode IN ('think','solve','nano','summary')),
  routing_reason   TEXT,                        -- from ModelRouter.reasoning — for audit/debugging
  is_summary       BOOLEAN DEFAULT FALSE,       -- TRUE for compaction summary messages
  is_archived_msg  BOOLEAN DEFAULT FALSE,       -- TRUE for messages replaced by summary
  tokens_input     INT DEFAULT 0,
  tokens_output    INT DEFAULT 0,
  latency_ms       INT DEFAULT 0,
  is_error         BOOLEAN DEFAULT FALSE,
  created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_messages_conversation ON messages(conversation_id, created_at);

-- TOKEN BUDGETS
CREATE TABLE token_budgets (
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  period DATE DEFAULT CURRENT_DATE,
  tokens_used BIGINT DEFAULT 0,
  budget_limit BIGINT DEFAULT 100000,
  PRIMARY KEY (user_id, period)
);

-- AGENT QUOTAS (monthly)
CREATE TABLE agent_quotas (
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  period TEXT,
  ocr_pages_used INT DEFAULT 0,
  vision_calls_used INT DEFAULT 0,
  speech_seconds_used INT DEFAULT 0,
  image_gen_used INT DEFAULT 0,
  PRIMARY KEY (user_id, period)
);

-- AUDIT LOG
CREATE TABLE audit_log (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID REFERENCES profiles(id),
  action TEXT NOT NULL,
  resource_type TEXT,
  metadata JSONB,
  policy_decision TEXT CHECK (policy_decision IN ('ALLOW','DENY')),
  policy_reason TEXT,
  ip_address TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);

-- USER ATTRIBUTES (for ABAC)
CREATE TABLE user_attributes (
  user_id UUID REFERENCES profiles(id) ON DELETE CASCADE,
  key TEXT,
  value JSONB,
  PRIMARY KEY (user_id, key)
);

-- ACCESS POLICIES
CREATE TABLE access_policies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  resource_type TEXT,
  conditions JSONB,
  effect TEXT CHECK (effect IN ('allow','deny')),
  priority INT DEFAULT 0,
  is_active BOOLEAN DEFAULT TRUE
);
```

### Migration 002 — Row-Level Security Policies

```sql
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
CREATE POLICY "users_see_own_profile" ON profiles
  FOR SELECT USING (auth.uid() = id);

CREATE POLICY "admins_see_all_profiles" ON profiles
  FOR SELECT USING (is_admin());

CREATE POLICY "users_update_own_profile" ON profiles
  FOR UPDATE USING (auth.uid() = id);

CREATE POLICY "admins_update_any_profile" ON profiles
  FOR UPDATE USING (is_admin());

-- CONVERSATIONS policies
CREATE POLICY "own_conversations" ON conversations
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "shared_conversations_readable" ON conversations
  FOR SELECT USING (is_shared = TRUE);

CREATE POLICY "admins_see_all_conversations" ON conversations
  FOR SELECT USING (is_admin());

-- MESSAGES policies
CREATE POLICY "own_messages" ON messages
  FOR ALL USING (
    conversation_id IN (
      SELECT id FROM conversations WHERE user_id = auth.uid()
    )
  );

CREATE POLICY "shared_conversation_messages" ON messages
  FOR SELECT USING (
    conversation_id IN (
      SELECT id FROM conversations WHERE is_shared = TRUE
    )
  );

-- TOKEN BUDGETS policies
CREATE POLICY "own_budget" ON token_budgets
  FOR SELECT USING (auth.uid() = user_id);

CREATE POLICY "admins_see_all_budgets" ON token_budgets
  FOR ALL USING (is_admin());

-- AUDIT LOG policies
CREATE POLICY "admins_audit_log" ON audit_log
  FOR SELECT USING (is_admin());

-- ADMIN SETTINGS policies
CREATE POLICY "admins_settings" ON admin_settings
  FOR ALL USING (is_admin());

CREATE POLICY "public_read_maintenance" ON admin_settings
  FOR SELECT USING (key = 'maintenance_mode');
```

### Migration 003 — Seed Your Admin User

> Run this AFTER you've signed in once with Google (so your profile exists).

```sql
-- Replace with your actual Supabase user ID (find it in Authentication → Users)
UPDATE profiles
SET role = 'superadmin'
WHERE id = '<YOUR_USER_UUID_HERE>';
```

---

### Migration 004 — Jobs Table (Background Task Tracking)

> This table tracks all background agent tasks (OCR, Vision, Speech, Image Gen, File Gen). FastAPI writes a row on job creation; Azure Functions update it as the task progresses. Supabase Realtime pushes the updates live to the frontend.

```sql
-- JOBS (background agent task tracking)
CREATE TABLE jobs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id         UUID REFERENCES profiles(id) ON DELETE CASCADE,
  conversation_id UUID REFERENCES conversations(id) ON DELETE CASCADE,
  type            TEXT NOT NULL CHECK (type IN ('ocr','vision','speech','image_gen','file_gen')),
  status          TEXT DEFAULT 'pending' CHECK (status IN ('pending','processing','done','failed')),
  result          JSONB,                        -- populated by Azure Function on completion
  error           TEXT,                         -- error message if status = 'failed'
  blob_url        TEXT,                         -- input file reference (for OCR/Vision)
  started_at      TIMESTAMPTZ,
  completed_at    TIMESTAMPTZ,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_jobs_user ON jobs(user_id, created_at DESC);
CREATE INDEX idx_jobs_conversation ON jobs(conversation_id);

-- RLS
ALTER TABLE jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "own_jobs" ON jobs
  FOR ALL USING (auth.uid() = user_id);

CREATE POLICY "admins_see_all_jobs" ON jobs
  FOR SELECT USING (is_admin());
```

---


## Step 6 — Enable Realtime on Core Tables

1. Supabase → **Database** → **"Replication"**

2. Click on the **`supabase_realtime`** publication (or tables count/toggle).
3. Enable **"Realtime"** (toggle to **ON**) for these tables:
   - `messages` (for live chat updates)
   - `conversations` (for live conversation updates)
   - `jobs` (for live background task status updates)

This enables server-sent events (SSE) streaming to the frontend for real-time UI updates without polling.

---

## Step 7 — Set Up Supabase Storage

1. Supabase → **Storage** (left menu)
2. Click **"New bucket"**
3. Create these buckets:

| Bucket name | Public? | Purpose |
|---|---|---|
| `uploads` | No (Private) | User uploaded files |
| `generated` | No (Private) | AI-generated files |
| `exports` | Yes (Public) | Shared conversation exports |

For `exports`, since it's public, filenames should be random tokens (they already are — we use `share_token`).

---

## ✅ Phase 0 Step 3 Complete When You Have:

- [ ] Supabase project created in Cape Town region
- [ ] `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, `SUPABASE_JWT_SECRET` saved to Azure Key Vault
- [ ] Google OAuth configured and working in Supabase dashboard
- [ ] All 3 SQL migrations run successfully
- [ ] RLS enabled on all tables
- [ ] Realtime enabled for `messages` + `conversations`
- [ ] Storage buckets created
- [ ] Your user ID promoted to `superadmin`

---

## Next Step

→ Proceed to `04_local_dev_checklist.md`
