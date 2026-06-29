# Security & UI Fixes Documentation

This document explains the technical details of the bugs identified and the corresponding fixes implemented in the frontend and backend systems.

---

## 1. Paused User Chat Enforcement

### The Issue
When an administrator paused or suspended a user (updating `profiles.is_active` to `False` in the database), the user was still allowed to chat.
1. `verify_jwt` only validated the cryptographic signature of the token against Supabase auth public keys and did not query the database.
2. `BlockGuardMiddleware` checked the `blocked_identities` table using `google_sub`, but did not check the `profiles.is_active` flag.
3. FastStarlette middlewares ran before FastAPI route dependencies, meaning `request.state.user` was `None` during middleware execution. Consequently, the middlewares (including `BlockGuardMiddleware` and `TokenBudgetMiddleware`) skipped checks entirely, creating a bypass.

### The Fix
1. **Added Claims Extractor**: Implemented `get_auth_user(request: Request)` in [jwt_validator.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/core/jwt_validator.py). It reads the Bearer token, extracts unverified claims immediately (safe for middleware context since signature validation runs downstream), and caches the dictionary on `request.state.user`.
2. **Updated Middlewares**: Modified all guard and logging middlewares to use `get_auth_user` to ensure user context is populated.
3. **Deactivation Guard**: Added a query in [block_guard.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/middleware/block_guard.py) inside `BlockGuardMiddleware` to check if `profiles.is_active` is `False`. If deactivated, the request returns a `403 Forbidden` response:
   ```json
   {
     "error": {
       "code": "USER_INACTIVE",
       "message": "Your account has been deactivated. Please contact an administrator."
     }
   }
   ```

---

## 2. Admin Endpoint CORS & 500 Crashes

### The Issue
The admin dashboard threw CORS errors on `/v1/admin/usage` and `/v1/admin/audit` requests because the backend encountered unhandled `500 Internal Server Errors`. When FastAPI crashes with unhandled exceptions, it bypasses the CORS middleware headers, manifesting as a CORS policy block in the browser.
* **Usage Endpoint Crash**: [admin_service.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/services/admin_service.py) queried the `messages` table for non-existent columns `user_id` (stored in the linked `conversations` table), `input_tokens` (database: `tokens_input`), `output_tokens` (database: `tokens_output`), and `model_used` (database: `model`).
* **Audit Endpoint Crash**: The database query fetched `profiles(email, full_name)`. However, the `profiles` table does not store user emails (they reside in Supabase `auth.users`) and uses `display_name` instead of `full_name`.

### The Fix
* **Usage Stats Fixed**: Rewrote `get_usage_stats` to perform a select join: `tokens_input, tokens_output, model, conversations(user_id)`. The function then maps the returned rows to return the exact key names expected by the admin dashboard frontend (`user_id`, `input_tokens`, `output_tokens`, `model_used`).
* **Audit Log Fixed**: Updated `get_audit_log` to query `profiles(id, display_name)`. It then resolves the user emails using Supabase's admin SDK (`db.auth.admin.list_users()`) to build an in-memory `user_id -> email` lookup and constructs the expected profile payload format: `{"email": email, "full_name": display_name or prefix}`.

---

## 3. Azure Static Web Page 404 Route Refreshes

### The Issue
Refreshing the browser on pages like `/budgets` or `/audit` returned a `404 (The requested content does not exist.)` error. This occurs because the static page containers (`agentochukostore` and `agentochukoadmin`) operate as Single Page Applications (SPAs). Direct URL path requests look for corresponding blobs in Azure Storage which do not exist.

### The Fix
To handle SPA routing, Azure Storage must redirect all missing paths to `index.html` where React Router handles routing client-side:
1. Open the **Azure Portal**.
2. Navigate to your Storage Account (`agentochukostore` or `agentochukoadmin`).
3. Select **Static website** under Data management.
4. Set the **Error document path** input field to `index.html` (in addition to the Index document path).
5. Save the configuration.

---

## 4. UI Style Improvements

* **Floating Sidebar**: Updated the aside styling in [Dashboard.tsx](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/frontend/src/pages/Dashboard.tsx) to use margins `top-3 left-3 h-[calc(100vh-24px)] rounded-2xl border bg-[#0d0f11]/95` so that the drawer floats on the screen instead of sticking to edges.
* **Glow Removal**: Removed the central gold ambient background glow `div` that appeared on dashboard load to maintain a clean dark aesthetic.

---

## 5. Human-Friendly Error Explanations

### The Issue
When any API request failed or a user restriction (deactivation, daily budget exhaustion, monthly quota limits, maintenance mode) was active, the chat interface would either fail silently or display a raw technical message (e.g. `Error: HTTP error! status: 403` or `Error: USER_INACTIVE`). This exposed internal system details and was confusing to the end user.

### The Fix
1. **JSON/Text Error Body Parsing**: Modified `triggerStream` in [Dashboard.tsx](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/frontend/src/pages/Dashboard.tsx) to read and parse the server error response body. If the server returns a structured JSON payload, it extracts `error.message` or `error.code` instead of throwing a generic status code exception.
2. **Friendly Message Mapper**: Implemented `getFriendlyErrorMessage(message)` to map raw backend exception text to polite, clear explanations:
   * **Deactivated** (`USER_INACTIVE`) &rarr; *"Your account access has been deactivated. Please reach out to your workspace administrator for assistance."*
   * **Blocked** (`ACCOUNT_BLOCKED`) &rarr; *"Access to this system has been restricted. Please contact support if you believe this is in error."*
   * **Budget Exhausted** (`BUDGET_EXHAUSTED`) &rarr; *"You have reached your daily message budget. Daily limits reset automatically at midnight UTC."*
   * **Quota Exhausted** (`QUOTA_EXHAUSTED`) &rarr; *"Your monthly resource quota has been fully utilized. Quotas reset at the start of next month."*
   * **Maintenance Mode** (`MAINTENANCE`) &rarr; *"Agent Ochuko is currently undergoing scheduled maintenance. Please try again in a few minutes."*
   * **Registration Closed** (`REGISTRATION_CLOSED`) &rarr; *"New registrations are currently closed. Please contact the administrator."*
  * **Database Errors (Supabase/Postgres)** &rarr; *"We are experiencing a temporary database connection issue. Our team is working to restore full connectivity; please try again in a few moments."*
   * **Server Errors (500/503)** &rarr; *"We encountered a temporary technical issue. Our systems are recovering; please try sending your message again in a moment."*
3. **Graceful Bubble Injection**: The friendly text is injected directly into the chat bubble as an assistant response, with system badges disabled, making the interaction feel polished and premium.

---

## 6. Supabase DB Check Constraint & Schema Fixes

### The Issue
1. **Conversations Table Constraint Mismatch**: Creating a new conversation resulted in a `500 Internal Server Error` stating that the new row violates the check constraint `conversations_mode_check`. The production Supabase database had an older check constraint (`mode IN ('think','solve')`) which blocked the insertion of the default `'discuss'` mode introduced in Phase 8.
2. **Audit Log Table Missing Column**: The audit logger middleware returned a `400 Bad Request` from Supabase stating `Could not find the 'latency_ms' column of 'audit_log' in the schema cache`. The database table was missing the `latency_ms` (integer) tracking column.

### The Fix
Created a unified patch script [016_fix_db_constraints.sql](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/scripts/016_fix_db_constraints.sql) to run in the Supabase SQL Editor:
1. Recreates `conversations_mode_check` to permit `'think'`, `'solve'`, and `'discuss'`.
2. Adds `latency_ms` column to `audit_log`.
3. Ensures `messages_routing_mode_check` includes both `'discuss'` and `'summary'` modes.


