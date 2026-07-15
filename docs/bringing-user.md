# Friend Onboarding Plan - Azure Pool Sharing System

> **Deprecated.** This draft was never implemented. The current source of truth is
> [`docs/monetization/README.md`](./monetization/README.md) ΓÇö two-tier model
> (renter + subscriber), self-serve script onboarding, no trial, unified `/login`.
> Do not build from this file.

---

This plan outlines the implementation of a friend onboarding system that allows trusted users to share their Azure OpenAI credits with your platform, with automatic 10% quota enforcement and usage tracking.

## Prompt Caching Status

**Current State**: Prompt caching is **NOT implemented** in the existing codebase.

**What exists instead**:
- Configuration caching (Azure App Configuration values cached in-memory)
- User profile/block status caching (TTL-based in-memory cache)
- Token budget check caching (per-user daily cache)
- Python/Node.js package caching in sandbox

**What's missing**:
- OpenAI prompt caching (prefix caching to reduce token costs on repeated prompts)
- System prompt caching across conversations
- Context window optimization through prompt caching

**Recommendation**: Implement OpenAI prompt caching after friend pool system is stable, as it would provide additional cost savings for both platform and friend accounts.

---

## Phase 1: Database Schema & Security Foundation

### 1.1 Database Tables

```sql
-- Friend Azure credentials storage
CREATE TABLE friend_azure_credentials (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id UUID REFERENCES profiles(id) NOT NULL, -- Your user ID
    friend_name TEXT NOT NULL,
    friend_email TEXT,
    azure_endpoint TEXT NOT NULL,
    azure_key_encrypted TEXT NOT NULL, -- Encrypted at rest
    account_type TEXT DEFAULT 'unknown', -- 'student' | 'premium' | 'pay-as-you-go'
    quota_limit_usd DECIMAL(10,2) NOT NULL, -- 10% of their monthly limit
    quota_used_usd DECIMAL(10,2) DEFAULT 0.00,
    quota_reset_date DATE NOT NULL,
    is_active BOOLEAN DEFAULT true,
    priority INT DEFAULT 0, -- Routing priority (higher = preferred)
    added_by UUID REFERENCES profiles(id), -- Who added this friend
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Usage tracking per friend
CREATE TABLE friend_usage_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    friend_credential_id UUID REFERENCES friend_azure_credentials(id) NOT NULL,
    user_id UUID REFERENCES profiles(id) NOT NULL,
    conversation_id UUID REFERENCES conversations(id),
    tokens_input INT NOT NULL,
    tokens_output INT NOT NULL,
    model TEXT NOT NULL,
    cost_usd DECIMAL(10,4) NOT NULL,
    platform_fee_usd DECIMAL(10,4) NOT NULL, -- 10% of cost_usd
    timestamp TIMESTAMPTZ DEFAULT now()
);

-- Friend invitations (for onboarding flow)
CREATE TABLE friend_invitations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    invited_by UUID REFERENCES profiles(id) NOT NULL,
    friend_email TEXT NOT NULL,
    invitation_token TEXT UNIQUE NOT NULL,
    status TEXT DEFAULT 'pending', -- 'pending' | 'accepted' | 'expired'
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);
```

### 1.2 Security Measures

**Encryption**:
- Use Azure Key Vault for master encryption key
- Encrypt friend API keys at rest using AES-256
- Decrypt only in memory during request routing

**Access Control**:
- Only superadmin can add/remove friends
- Friend credentials never exposed in API responses
- Audit log all friend credential changes

**Rate Limiting**:
- Per-friend request rate limits (prevent abuse)
- Automatic friend disable on quota exhaustion
- Alert on unusual usage patterns

---

## Phase 2: Backend Services

### 2.1 Friend Pool Manager Service

**File**: `backend/app/services/friend_pool_manager.py`

**Core Functions**:
- `get_available_friend()` - Find friend with available quota
- `deduct_usage(friend_id, cost)` - Deduct usage and log
- `reset_monthly_quotas()` - Reset all quotas on 1st of month
- `get_friend_usage_stats()` - Aggregate usage data
- `validate_friend_credentials()` - Test Azure endpoint connectivity

**Smart Routing Logic**:
- Prioritize student accounts for cheaper models (Nano, Mini)
- Use premium accounts for expensive models (GPT-5.4)
- Load balance across friends with available quota
- Automatic failover on quota exhaustion

### 2.2 OpenAI Client Factory

**File**: `backend/app/services/openai_client_factory.py`

**Core Functions**:
- `get_openai_client_for_request(user_id)` - Returns (client, friend_id)
- `create_friend_client(friend_credential)` - Create AzureOpenAI client
- `handle_quota_exhaustion()` - Graceful error handling

**Integration Points**:
- Modify existing chat endpoint to use friend pool
- Fallback to platform deployment if no friends available
- Track usage per request for billing

### 2.3 Usage Tracking Service

**File**: `backend/app/services/usage_tracker.py`

**Core Functions**:
- `calculate_token_cost(tokens, model)` - Cost calculation
- `log_friend_usage()` - Record usage in database
- `get_monthly_usage_report()` - Generate usage reports
- `detect_usage_anomalies()` - Alert on unusual patterns

---

## Phase 3: Admin UI Components

### 3.1 Friend Pool Management Page

**File**: `frontend/src/pages/FriendPool.tsx`

**Features**:
- List all friends with quota usage progress bars
- Add new friend (name, email, Azure credentials)
- Remove friend with confirmation
- Edit friend quota limits and priority
- View per-friend usage statistics

**Security**:
- Only accessible to superadmin role
- API key input masked with show/hide toggle
- All credential changes require confirmation

### 3.2 Friend Invitation Flow

**File**: `frontend/src/pages/FriendInvitation.tsx`

**Features**:
- Send invitation via email
- Generate unique invitation token
- Track invitation status
- Acceptance flow for friend to provide credentials

**User Flow**:
1. Admin enters friend email
2. System sends invitation with secure link
3. Friend clicks link, enters Azure credentials
4. System validates credentials
5. Friend added to pool with default 10% quota

### 3.3 Usage Dashboard

**File**: `frontend/src/pages/FriendUsageDashboard.tsx`

**Features**:
- Aggregate pool usage statistics
- Per-friend breakdown with charts
- Top users per friend
- Monthly cost projections
- Export to CSV functionality

---

## Phase 4: API Endpoints

### 4.1 Friend Management Endpoints

```python
# backend/app/api/v1/endpoints/friends.py

@router.post("/v1/admin/friends")
async def add_friend(friend_data: FriendCreateRequest, admin: UserContext):
    """Add new friend to Azure pool"""
    
@router.get("/v1/admin/friends")
async def list_friends(admin: UserContext):
    """List all friends with quota status"""
    
@router.patch("/v1/admin/friends/{id}")
async def update_friend(id: str, updates: FriendUpdateRequest, admin: UserContext):
    """Update friend quota or priority"""
    
@router.delete("/v1/admin/friends/{id}")
async def remove_friend(id: str, admin: UserContext):
    """Remove friend from pool"""
```

### 4.2 Usage Tracking Endpoints

```python
@router.get("/v1/admin/friends/usage")
async def get_friend_usage(admin: UserContext, days: int = 30):
    """Get aggregate usage statistics"""
    
@router.get("/v1/admin/friends/{id}/usage")
async def get_friend_usage_detail(id: str, admin: UserContext):
    """Get detailed usage for specific friend"""
    
@router.get("/v1/admin/friends/export")
async def export_usage_csv(admin: UserContext):
    """Export usage data as CSV"""
```

### 4.3 Invitation Endpoints

```python
@router.post("/v1/admin/friends/invite")
async def send_invitation(invitation: InvitationRequest, admin: UserContext):
    """Send invitation to friend"""
    
@router.get("/v1/friends/accept/{token}")
async def accept_invitation(token: str):
    """Public endpoint for friend to accept invitation"""
    
@router.post("/v1/friends/complete/{token}")
async def complete_onboarding(token: str, credentials: FriendCredentials):
    """Friend submits Azure credentials"""
```

---

## Phase 5: Integration & Testing

### 5.1 Chat Endpoint Integration

**Modify**: `backend/app/api/v1/endpoints/chat.py`

**Changes**:
- Before Azure OpenAI call, check friend pool availability
- If friend available, use their credentials
- Track usage and deduct from friend quota
- Fallback to platform deployment if no friends available

### 5.2 Testing Strategy

**Unit Tests**:
- Friend pool manager logic
- Usage calculation accuracy
- Encryption/decryption of credentials
- Quota enforcement

**Integration Tests**:
- End-to-end friend onboarding flow
- Chat requests using friend credentials
- Quota exhaustion handling
- Monthly reset automation

**Load Tests**:
- Multiple concurrent friends
- Failover scenarios
- Usage tracking accuracy under load

---

## Phase 6: Monitoring & Alerts

### 6.1 Azure Functions Cron Jobs

**Monthly Reset Function**:
- Trigger: 1st of every month at midnight UTC
- Reset all friend quotas to 0
- Send usage reports to friends
- Archive previous month's usage data

**Usage Anomaly Detection**:
- Trigger: Every 6 hours
- Detect unusual usage patterns
- Alert admin on potential abuse
- Auto-disable suspicious friends

### 6.2 Application Insights Metrics

**Custom Metrics**:
- `friend_pool.quota_utilization_pct` - Per friend
- `friend_pool.requests_routed` - Total requests via friends
- `friend_pool.cost_saved_usd` - Platform cost savings
- `friend_pool.failover_count` - Failover to platform

**Alerts**:
- Friend quota > 90% utilized
- Friend endpoint unreachable
- Unusual usage spike detected
- All friends exhausted

---

## Implementation Order

**Week 1**: Database schema + security foundation
**Week 2**: Backend services (pool manager, client factory)
**Week 3**: Admin UI components (friend pool, invitations)
**Week 4**: API endpoints + chat integration
**Week 5**: Testing + monitoring setup
**Week 6**: Deployment + friend onboarding

---

## Success Criteria

- Friends can be added securely with encrypted credentials
- Chat requests automatically route to available friends
- 10% quota enforcement works accurately
- Usage tracking is precise and auditable
- Admin has full visibility into pool usage
- System handles friend exhaustion gracefully
- Monthly resets work automatically
- Security audit shows no credential exposure
