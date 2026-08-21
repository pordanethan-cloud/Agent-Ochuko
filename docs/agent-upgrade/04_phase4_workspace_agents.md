# Phase 4: Workspace Agents & Team Collaboration

> **Parent**: [Master Plan](./00_master_plan.md)
> **Depends on**: [Phase 1](./01_phase1_foundation.md), [Phase 2](./02_phase2_browser_and_background.md), [Phase 3](./03_phase3_mcp_connectors.md)
> **Timeline**: Weeks 11–14
> **Status**: Draft

---

## Phase 4 Overview

Phase 4 introduces **Workspace Agents** — shared, configurable AI agents that teams can create, customize, and share within an organization. Each workspace agent has its own persona, system prompt, allowed tools, and connector access — scoped by an admin.

This is the equivalent of ChatGPT's "Custom GPTs" but within a team workspace, with enterprise-grade permission controls and usage analytics.

### Deliverables

1. Workspace Agent data model and CRUD API
2. Custom system prompt editor
3. Tool and connector permission matrix (per agent)
4. Team sharing with role-based access (admin, editor, viewer)
5. Usage analytics dashboard (tokens, tasks, success rate per agent)
6. Agent marketplace/gallery UI (browse and activate shared agents)
7. Database: `workspace_agents`, `workspace_agent_members` tables

---

## 4.1 Data Model

### Supabase Schema

```sql
-- Workspace Agents
CREATE TABLE IF NOT EXISTS workspace_agents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    organization_id UUID,                -- Optional org-level grouping
    created_by UUID NOT NULL,
    name TEXT NOT NULL,
    slug TEXT UNIQUE NOT NULL,            -- URL-friendly identifier
    description TEXT,
    avatar_url TEXT,                      -- Agent avatar/icon
    system_prompt TEXT NOT NULL,          -- Custom instructions
    greeting_message TEXT,               -- First message when user opens agent
    allowed_tools TEXT[] DEFAULT '{}',   -- Scoped tool whitelist
    allowed_connectors TEXT[] DEFAULT '{}', -- Which connectors this agent can use
    max_steps_per_task INT DEFAULT 10,
    max_duration_seconds INT DEFAULT 300,
    model_tier TEXT DEFAULT 'solve'      -- "think" | "solve" | "nano"
        CHECK (model_tier IN ('think', 'solve', 'nano')),
    is_shared BOOLEAN DEFAULT false,     -- Visible to org members
    is_published BOOLEAN DEFAULT false,  -- Visible in marketplace/gallery
    metadata JSONB DEFAULT '{}'::jsonb,  -- Extensible metadata
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Agent team membership
CREATE TABLE IF NOT EXISTS workspace_agent_members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES workspace_agents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    role TEXT NOT NULL DEFAULT 'viewer'
        CHECK (role IN ('admin', 'editor', 'viewer')),
    added_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(agent_id, user_id)
);

-- Usage analytics
CREATE TABLE IF NOT EXISTS workspace_agent_usage (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    agent_id UUID REFERENCES workspace_agents(id) ON DELETE CASCADE,
    user_id UUID NOT NULL,
    task_id UUID REFERENCES agent_tasks(id),
    tokens_used INT DEFAULT 0,
    steps_executed INT DEFAULT 0,
    success BOOLEAN,
    duration_seconds INT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- RLS
ALTER TABLE workspace_agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_agent_members ENABLE ROW LEVEL SECURITY;
ALTER TABLE workspace_agent_usage ENABLE ROW LEVEL SECURITY;

-- Creators can manage their agents
CREATE POLICY "Creators manage agents"
    ON workspace_agents FOR ALL
    USING (auth.uid() = created_by);

-- Shared agents visible to org members (via membership table)
CREATE POLICY "Members view shared agents"
    ON workspace_agents FOR SELECT
    USING (
        is_shared = true AND id IN (
            SELECT agent_id FROM workspace_agent_members
            WHERE user_id = auth.uid()
        )
    );

-- Published agents visible to all authenticated users
CREATE POLICY "Published agents public"
    ON workspace_agents FOR SELECT
    USING (is_published = true);

-- Members manage own membership
CREATE POLICY "Members view own membership"
    ON workspace_agent_members FOR SELECT
    USING (user_id = auth.uid());

-- Service role bypass
CREATE POLICY "Service role agents"
    ON workspace_agents FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role members"
    ON workspace_agent_members FOR ALL USING (auth.role() = 'service_role');
CREATE POLICY "Service role usage"
    ON workspace_agent_usage FOR ALL USING (auth.role() = 'service_role');

-- Indexes
CREATE INDEX idx_workspace_agents_org ON workspace_agents(organization_id);
CREATE INDEX idx_workspace_agents_shared ON workspace_agents(is_shared, is_published);
CREATE INDEX idx_workspace_agent_members_user ON workspace_agent_members(user_id);
CREATE INDEX idx_workspace_agent_usage_agent ON workspace_agent_usage(agent_id, created_at DESC);
```

---

## 4.2 Workspace Agent API

### File: [NEW] `app/api/v1/endpoints/workspace_agents.py`

```python
router = APIRouter()

class CreateAgentRequest(BaseModel):
    name: str
    description: Optional[str] = None
    system_prompt: str
    greeting_message: Optional[str] = None
    allowed_tools: List[str] = []
    allowed_connectors: List[str] = []
    model_tier: str = "solve"
    max_steps_per_task: int = 10
    max_duration_seconds: int = 300

class UpdateAgentRequest(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    system_prompt: Optional[str] = None
    allowed_tools: Optional[List[str]] = None
    allowed_connectors: Optional[List[str]] = None
    is_shared: Optional[bool] = None

class InviteMemberRequest(BaseModel):
    user_email: str
    role: str = "viewer"  # "admin" | "editor" | "viewer"

@router.post("/")
async def create_workspace_agent(payload: CreateAgentRequest, user=Depends(verify_jwt)):
    """Create a new workspace agent. Creator becomes admin."""

@router.get("/")
async def list_workspace_agents(user=Depends(verify_jwt)):
    """List agents created by user + shared with user + published."""

@router.get("/{agent_id}")
async def get_workspace_agent(agent_id: str, user=Depends(verify_jwt)):
    """Get agent details, tools, connectors, and members."""

@router.put("/{agent_id}")
async def update_workspace_agent(agent_id: str, payload: UpdateAgentRequest, user=Depends(verify_jwt)):
    """Update agent config. Requires admin/editor role."""

@router.delete("/{agent_id}")
async def delete_workspace_agent(agent_id: str, user=Depends(verify_jwt)):
    """Delete agent. Requires admin role."""

@router.post("/{agent_id}/members")
async def invite_member(agent_id: str, payload: InviteMemberRequest, user=Depends(verify_jwt)):
    """Invite a user to access this agent."""

@router.delete("/{agent_id}/members/{member_id}")
async def remove_member(agent_id: str, member_id: str, user=Depends(verify_jwt)):
    """Remove a member from the agent."""

@router.get("/{agent_id}/analytics")
async def get_agent_analytics(agent_id: str, user=Depends(verify_jwt)):
    """
    Returns usage analytics:
    - Total tasks, success rate, avg duration
    - Token spend (daily/weekly/monthly)
    - Top users by usage
    - Step completion heatmap
    """
```

---

## 4.3 Agent Routing Integration

### File: [MODIFY] `app/core/agent_task_manager.py`

When a user selects a workspace agent for their task, the task manager:

1. Loads the workspace agent's config (system_prompt, allowed_tools, model_tier)
2. Overrides the default system prompt with the agent's custom prompt
3. Filters the tool set to only allowed_tools
4. Uses the agent's model_tier for routing
5. Records usage to `workspace_agent_usage`

```python
async def execute_with_workspace_agent(self, workspace_agent_id: str):
    """Run task using a workspace agent's configuration."""
    agent_config = await load_workspace_agent(workspace_agent_id)

    # Override system prompt
    self.system_prompt = agent_config.system_prompt

    # Filter tools to only allowed
    self.allowed_tools = set(agent_config.allowed_tools)
    self.tools = [t for t in self.all_tools if t["name"] in self.allowed_tools]

    # Override model tier
    self.model_tier = agent_config.model_tier

    # Execute normally
    async for event in self.execute_plan():
        yield event

    # Record usage
    await record_usage(
        agent_id=workspace_agent_id,
        user_id=self.task.user_id,
        task_id=self.task.id,
        tokens=self.task.total_token_spend,
        steps=self.task.current_step,
        success=self.task.state == TaskState.COMPLETED,
        duration=(self.task.completed_at - self.task.started_at).seconds
    )
```

---

## 4.4 Frontend Components

### Agent Gallery / Marketplace

```
┌─────────────────────────────────────────────────────────────┐
│  AGENT GALLERY                                [+ Create]    │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │  🔬          │  │  📊          │  │  ✉️          │     │
│  │  Research    │  │  Data        │  │  Email       │     │
│  │  Assistant   │  │  Analyst     │  │  Manager     │     │
│  │              │  │              │  │              │     │
│  │  By: admin   │  │  By: team    │  │  By: you     │     │
│  │  Tasks: 142  │  │  Tasks: 89   │  │  Tasks: 23   │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
│                                                             │
│  ┌──────────────┐  ┌──────────────┐                        │
│  │  📝          │  │  🏗️          │                        │
│  │  Report      │  │  DevOps      │                        │
│  │  Writer      │  │  Agent       │                        │
│  └──────────────┘  └──────────────┘                        │
└─────────────────────────────────────────────────────────────┘
```

### Agent Configuration Editor

```
┌─────────────────────────────────────────────────────────────┐
│  CONFIGURE AGENT: Research Assistant                         │
│                                                             │
│  Name:        [Research Assistant        ]                  │
│  Description: [Autonomous research agent...]                │
│  Model Tier:  [Solve ▾]                                     │
│                                                             │
│  System Prompt:                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ You are a research assistant specialized in...       │  │
│  │ Always cite sources. Produce structured reports.     │  │
│  │ Use deep_research for multi-query investigations.    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                             │
│  Allowed Tools:                                              │
│  [x] search_web    [x] deep_research    [ ] execute_code   │
│  [ ] generate_image [ ] browse_web      [x] visualize      │
│                                                             │
│  Allowed Connectors:                                         │
│  [ ] Gmail          [ ] Calendar         [x] GitHub          │
│                                                             │
│  Limits:                                                     │
│  Max Steps: [10]    Max Duration: [5 min ▾]                  │
│                                                             │
│  Sharing:                                                    │
│  [x] Share with team    [ ] Publish to gallery              │
│                                                             │
│  [Save Changes]                                              │
└─────────────────────────────────────────────────────────────┘
```

### Usage Analytics

```
┌─────────────────────────────────────────────────────────────┐
│  ANALYTICS: Research Assistant (Last 30 days)                │
│                                                             │
│  Total Tasks: 142    Success Rate: 87%    Avg Duration: 2m  │
│  Token Spend: 45,200                                         │
│                                                             │
│  Daily Usage:                                                │
│  ▓▓▓▓▓▓▓▓░░░ 8 tasks/day avg                               │
│                                                             │
│  Top Users:                                                  │
│  1. user@example.com  — 48 tasks, 15k tokens                │
│  2. admin@example.com — 35 tasks, 12k tokens                │
│                                                             │
│  Step Completion Heatmap:                                    │
│  Step 1: ██████████ 98%                                      │
│  Step 2: █████████░ 92%                                      │
│  Step 3: ████████░░ 85%                                      │
│  Step 4: ██████░░░░ 71%                                      │
│  Step 5: ████░░░░░░ 55%                                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 4.5 File Change Summary

| Action | File | Description |
|---|---|---|
| **NEW** | `app/api/v1/endpoints/workspace_agents.py` | CRUD + analytics API |
| **NEW** | `frontend/src/pages/WorkspaceAgents.tsx` | Agent gallery/marketplace |
| **NEW** | `frontend/src/components/AgentConfigEditor.tsx` | Agent configuration form |
| **NEW** | `frontend/src/components/AgentAnalytics.tsx` | Usage analytics dashboard |
| **MODIFY** | `app/core/agent_task_manager.py` | Workspace agent config override |
| **MODIFY** | `app/core/model_router.py` | Route based on agent's model_tier |
| **MODIFY** | `app/main.py` | Register workspace_agents router |
| **NEW** | Supabase migration | `workspace_agents`, `workspace_agent_members`, `workspace_agent_usage` |

---

## 4.6 Verification Plan

```bash
python -m pytest tests/test_workspace_agents.py -v
python -m pytest tests/test_agent_permissions.py -v
python -m pytest tests/test_agent_analytics.py -v
```

### Manual Scenarios

1. **Create agent**: Admin creates "Research Assistant" with search + deep_research tools only → verify it cannot use execute_code
2. **Share agent**: Share with team → team member accesses → runs a task → verify usage recorded
3. **Permission enforcement**: Editor tries to delete agent → denied. Admin deletes → succeeds
4. **Analytics**: Run 10 tasks with an agent → verify analytics dashboard shows correct counts
5. **Gallery**: Publish agent → verify it appears in gallery for all authenticated users
