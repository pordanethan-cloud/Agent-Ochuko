# Cost Analysis: Stateful Terminal & Bash Execution Upgrade

This document outlines the financial, resource, and technical costs associated with implementing the bash and persistent workspace upgrade.

---

## 1. Financial Costs

### A. OpenAI/LLM Token Costs
* **Expected Increase**: **Low to Medium (+15-30%)**
* **Rationale**: Giving the model terminal access means it can now perform multi-step operations (e.g., clone a repository, edit a file, run tests, and check logs). This adds OODA loop turns to a single request. 
* **Mitigation**: The existing `max_iterations` guardrail in [chat.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/api/v1/endpoints/chat.py#L1032) limits total loop execution turns, preventing infinite runaway loops.

### B. Hosting & Storage Costs
* **Cloudflare R2 Storage**: Negligible. The delta-snapshot scanner prevents uploading third-party cloned repos (like `node_modules` or `.git`) and only uploads user artifacts.
* **Azure Container App Resource Footprint**: 
  * Running `git` and lightweight shell scripts requires virtually no extra CPU or RAM.
  * **Disk Usage**: Persistent workspaces `/tmp/sandbox_{conversation_id}` will consume storage over time as users run commands and clone files.
  * **Mitigation**: Introduce a daily cron in [function_app.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/functions/function_app.py) or an automated cleanup system that removes workspace directories `/tmp/sandbox_{conversation_id}` for conversations that have been archived or have not been active for more than 7 days.

---

## 2. Technical and Operational Costs

### A. Security Risk (High)
* **Risk**: Giving the LLM bash shell access means untrusted or hallucinated code can run arbitrary commands. It could execute network scanning, malware insertion, or try to access host environment variables.
* **Mitigation**:
  1. We already strip sensitive variables (`SUPABASE_KEY`, `OPENAI_API_KEY`, etc.) in the sandbox wrapper.
  2. The backend is non-root (`appuser`), which mitigates system-wide compromise risks.
  3. Ensure container isolation policies are strictly configured in Azure Container Apps.

### B. Complexity and Maintenance
* **Build Time**: Adding Node.js, Python, and Git to a single Docker image increases the initial image build size (~1.5 GB). 
* **Error Vectors**: Command timeouts, stuck processes, or heavy git clones (e.g., cloning a 500MB repository) could hang execution.
* **Mitigation**: Standard execution timeouts (45 seconds) in [code_sandbox.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/services/code_sandbox.py#L31) terminate hung subprocesses cleanly.
