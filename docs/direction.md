# Direction Plan: Stateful Terminal & Bash Execution Upgrade

This document outlines the step-by-step instructions to implement the stateful terminal and bash execution upgrade in Agent Ochuko.

---

## Objective
Enable Agent Ochuko to execute arbitrary terminal commands (like `git clone`, `curl`, and file system manipulation) and maintain folder state across multiple conversational turns, matching the problem-solving style of advanced developer agents.

---

## Step-by-Step Implementation Steps

### Step 1: Update the Runtime Environment
To allow Git operations, the backend container must have the `git` client installed.
* **File to Modify**: [Dockerfile](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/Dockerfile)
* **Changes**:
  Add `git` to the list of packages installed via `apt-get` in the runtime stage (Stage 2):
  ```dockerfile
  RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      git \
      && curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
      && apt-get install -y nodejs \
      && rm -rf /var/lib/apt/lists/*
  ```

### Step 2: Implement Bash Support and Stateful Workspace in the Sandbox
We must update the sandbox service to support shell commands and keep directory state alive per conversation.
* **File to Modify**: [code_sandbox.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/services/code_sandbox.py)
* **Changes**:
  1. **Persistent Directory**: Define `work_dir` as `/tmp/sandbox_{conversation_id}` instead of a random UUID so that it persists across turns.
  2. **Selective Cleanup**: Do not run `shutil.rmtree(work_dir)` in the `finally` block by default.
  3. **State Snapshotting**: Before running a script, scan and record the modification times of existing files. After execution, only scan and upload files that are newly created or modified during that specific run. Skip dependency/version control folders (`.git`, `node_modules`, `.venv`, `__pycache__`) to prevent massive network overhead.
  4. **Bash Execution Execution Path**: Add a block to handle `bash` or `shell` scripts:
     ```python
     if language in ("bash", "shell", "sh"):
         script_path = os.path.join(work_dir, "command.sh")
         with open(script_path, "w", encoding="utf-8") as f:
             f.write(code)
         
         proc = await asyncio.create_subprocess_exec(
             "/bin/bash", script_path,
             stdout=asyncio.subprocess.PIPE,
             stderr=asyncio.subprocess.PIPE,
             env=env,
             cwd=work_dir
         )
     ```

### Step 3: Register the Terminal Tool in the Chat Endpoint
We must advertise the bash execution capability to the LLM and pass the parameters to the sandbox service.
* **File to Modify**: [chat.py](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/agent-ochuko/backend/app/api/v1/endpoints/chat.py)
* **Changes**:
  1. Add `"bash"` to the allowed parameters list of `language` under the `run_code_agent` tool registration.
  2. Update the system prompt instructions (`_OCHUKO_RULE`) to explain that the agent can execute terminal commands using the `"bash"` language option when cloning repos or executing scripts.

---

## Verification & Testing Strategy
To prevent user-facing downtime, we will perform local surgical verification:
1. Run backend unit tests using `pytest` to make sure existing sandbox features aren't broken.
2. Manually test the shell execution by requesting the agent to clone a public dummy repository and list the files in the workspace.
3. Verify that third-party source files inside the cloned repository are not uploaded to R2, and only explicit modifications are processed.
