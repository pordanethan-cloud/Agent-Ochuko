# Agent Ochuko — Database Migrations

This directory contains the canonical SQL schema migrations for Agent Ochuko's Supabase (PostgreSQL) database.

---

## Migration Execution Order

Migrations are ordered numerically from `001` to `030`. All migrations are written to be idempotent (`CREATE TABLE IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`, `CREATE OR REPLACE FUNCTION`).

| # | File | Purpose | Target |
|---|---|---|---|
| **001** | [`001_core_tables.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/001_core_tables.sql) | Core user tables, profiles, and basic schemas | Supabase core |
| **002** | [`002_rls_policies.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/002_rls_policies.sql) | Row-Level Security (RLS) policies for user data isolation | Security |
| **003** | [`003_seed_admin_user.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/003_seed_admin_user.sql) | Seed default administrative user identity | Admin setup |
| **004** | [`004_jobs_table.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/004_jobs_table.sql) | Background jobs and async processing queue | Task worker |
| **005** | [`005_seed_admin_settings.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/005_seed_admin_settings.sql) | Seed runtime dynamic configuration and operational settings | Admin config |
| **006** | [`006_usage_stats_table.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/006_usage_stats_table.sql) | Token tracking, model usage, and session consumption stats | Billing/telemetry |
| **007** | [`007_ensure_budget_row_rpc.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/007_ensure_budget_row_rpc.sql) | RPC function to ensure a budget row exists per active user | Token budget |
| **008** | [`008_audit_log_columns.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/008_audit_log_columns.sql) | Audit log schema and metadata tracking columns | Compliance |
| **009** | [`009_messages_routing_discuss.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/009_messages_routing_discuss.sql) | Message routing classification (`think`, `solve`, `discuss`, `agent`) | Router |
| **010** | [`010_jobs_schema_patch.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/010_jobs_schema_patch.sql) | Background jobs schema hardening patch | Jobs |
| **011** | [`011_aggregate_hourly_usage_rpc.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/011_aggregate_hourly_usage_rpc.sql) | Hourly rollups for user analytics and dashboards | Aggregation |
| **012** | [`012_conversation_archiver_rpc.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/012_conversation_archiver_rpc.sql) | Automated archive / soft-deletion for conversations | Conversations |
| **013** | [`013_increment_nano_turns_rpc.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/013_increment_nano_turns_rpc.sql) | Fast counter increment RPC for nano turns | Nano router |
| **014** | [`014_check_and_deduct_budget_rpc.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/014_check_and_deduct_budget_rpc.sql) | Atomic budget verification and token deduction RPC | Budget |
| **015** | [`015_enforce_registration_limits.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/015_enforce_registration_limits.sql) | Registration rate limiter and domain gating | Security |
| **016** | [`016_fix_db_constraints.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/016_fix_db_constraints.sql) | Foreign key and check constraint fixes | Integrity |
| **017** | [`017_top_users_rpc.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/017_top_users_rpc.sql) | Admin query RPC for top users by consumption | Admin |
| **018** | [`018_reconcile_token_budget_rpc.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/018_reconcile_token_budget_rpc.sql) | Budget reconciliation and ledger balancing RPC | Ledger |
| **019** | [`019_agent_memory_column.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/019_agent_memory_column.sql) | Vector memory / conversational memory storage | Memory |
| **020** | [`020_conversations_fts_indexes.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/020_conversations_fts_indexes.sql) | Full-text search (FTS) indexes on conversation messages | Search |
| **021** | [`021_generated_files_table.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/021_generated_files_table.sql) | Metadata and R2/Azure links for agent-generated deliverables | Files |
| **022** | [`022_align_timezone_nigeria.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/022_align_timezone_nigeria.sql) | Timezone alignment defaults (Africa/Lagos, UTC+1) | Localization |
| **023** | [`023_google_credentials_table.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/023_google_credentials_table.sql) | Secure OAuth token and credential storage for Google Workspace | Connectors |
| **024** | [`024_messages_widget_parts.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/024_messages_widget_parts.sql) | Interactive widgets and structured cards on message rows | UI rendering |
| **025** | [`025_agent_tasks_schema.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/025_agent_tasks_schema.sql) | Agent tasks, steps, plans, execution states, and resume markers | Agent Mode |
| **026** | [`026_hosted_sites_schema.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/026_hosted_sites_schema.sql) | Live multi-file web app deployments and static site preview links | Web engine |
| **027** | [`027_user_connectors_schema.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/027_user_connectors_schema.sql) | User-level connector status and auth tokens (Gmail, Drive, Workstation) | Connectors |
| **028** | [`028_user_settings_table.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/028_user_settings_table.sql) | User preferences, custom system prompts, and UI configuration | Preferences |
| **029** | [`029_agent_task_replan_count.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/029_agent_task_replan_count.sql) | Replan attempt counter column on `agent_tasks` for OODA drift recovery | Agent Mode |
| **030** | [`030_agent_task_scratchpad.sql`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations/030_agent_task_scratchpad.sql) | Blackboard working memory column on `agent_tasks` across step turns | Agent Mode |

---

## How to Apply

1. Open the [Supabase Dashboard](https://supabase.com/dashboard).
2. Navigate to **SQL Editor**.
3. Apply migrations in numerical order or paste the desired migration script directly into the editor and execute.
