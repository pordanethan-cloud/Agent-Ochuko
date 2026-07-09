# Architectural Design: Code Sandbox Run Location & Capabilities

This document details the environment in which the agent executes user-requested Python, JavaScript (Node.js), and Bash scripts.

---

## 1. Sandbox Run Location

The sandbox code execution is managed by the FastAPI backend. It runs on the **Backend Application Host** (e.g., inside the Azure Container App or local dev server) utilizing a highly-isolated process directory design.

### Directory Architecture

```
/backend
  /app
  /scratch
    /sandbox_workspaces
      /{conversation_id}
        /work_dir  <-- Executable scripts, downloads, and output assets are restricted here
```

For every code execution turn:
1. **Dynamic Workspace Provisioning**: A unique directory (`work_dir`) is created for the conversation.
2. **State Persistence**: The workspace folder is **persisted across turns** inside the active conversation, allowing a user to run sequential commands (e.g., install a package, write a file, execute it, read results).
3. **Execution Context**: Commands are launched under standard execution sub-shells (`asyncio.create_subprocess_exec`), completely isolated to the workspace context.

---

## 2. Capabilities & Languages

The sandbox supports three core runtime environments:

### A. Python (`python`)
* Runs using the backend host's Python interpreter.
* **Auto-Package Hydration**: If the execution fails with a `ModuleNotFoundError`, the sandbox parser intercepts the error, identifies the missing PyPI module, and runs an automatic background install (`pip install --target`) into a local dependency path.
* Common math, data analysis (pandas, numpy), and plotting (matplotlib) libraries are supported out-of-the-box.

### B. JavaScript / Node.js (`javascript`)
* Runs using Node.js.
* Recommended runtime for advanced file formatting operations (like generating Word documents using the `docx` package).

### C. Bash Terminal (`bash`)
* Provides a stateful command-line interface.
* Used for git operations (cloning repositories), folder scanning, compiling binaries, and running custom shell scripts.

---

## 3. Network Access & Security Boundaries

To maintain software reliability and prevent malicious exploitation:

* **Outbound Internet Access**: The sandbox possesses outbound internet connectivity to allow:
  - Downloading dependencies via package managers (`pip`, `npm`).
  - Fetching data from public APIs or downloading remote code bases (e.g. via `curl`, `wget`, or `git clone`).
* **Isolation Constraints**:
  - **No Inbound Connection**: The sandbox cannot bind port listeners that are reachable from the public web.
  - **Directory Traversal Protection**: Subprocesses are executed within their specific workspace folder. Directory walking is restricted to prevent scraping the parent system directories.
  - **Execution Timeouts**: A hard limit is set per sandbox command execution (typically 30 seconds) to prevent infinite loops, hanging threads, or memory leaks from exhausting backend resources.
