# Agent Ochuko — Operational Scripts & Utilities

This directory is strictly reserved for **executable operational tools, setup automation, diagnostics, and CLI utilities**. 

Database schema migrations have been organized into the dedicated top-level [`migrations/`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations) directory.

---

## Catalog of Scripts

### 1. `fetch_public_book.py`
**Purpose**: Unified multi-library book downloader & search engine used by the Agent Ochuko `public-library-books` skill. Searches and fetches public-domain texts across Internet Archive, Open Library, Project Gutenberg, Standard Ebooks, and Anna's Archive in a token-efficient loop.

**Usage**:
```bash
# Search across repositories (returns concise structured summaries)
python scripts/fetch_public_book.py search "Pride and Prejudice"

# Download a specific book by identifier
python scripts/fetch_public_book.py download "texts:prideandprejudic00austuoft" pdf "C:\Users\T14 GEN 5\Downloads\books"
```

---

### 2. `download_livestream_vod.py`
**Purpose**: High-reliability YouTube livestream DVR / VOD capture utility. Extracts active M3U8 streaming playlists using `yt-dlp` (prioritizing 1080p, falling back to 720p) and downloads all captured segments sequentially.

**Usage**:
```bash
# Run with default or configured video URL
python scripts/download_livestream_vod.py
```

---

### 3. `enable_hyperv_wsl.ps1`
**Purpose**: Windows host provisioning script. Configures hypervisor launch type in Windows BCD, enables VirtualMachinePlatform, Microsoft-Windows-Subsystem-Linux (WSL), and Hyper-V features without forced reboots.

**Usage** (Run as Administrator):
```powershell
powershell -ExecutionPolicy Bypass -File scripts\enable_hyperv_wsl.ps1
```

---

### 4. `diag_conversation_owner.py`
**Purpose**: Diagnostic tool for troubleshooting conversation row ownership in production Supabase. Verifies that the conversation exists, prints user ID attribution, and diagnoses 403 or permission mismatches.

**Usage**:
```bash
python scripts/diag_conversation_owner.py
```

---

## Guidelines for Adding New Scripts

1. **Executable Only**: Only Python (`.py`), PowerShell (`.ps1`), Shell (`.sh`), or Batch (`.bat`) scripts belong here.
2. **No Migrations**: Never place raw SQL schema migrations in `scripts/`; all database DDL/DML belongs in [`migrations/`](file:///c:/Users/T14%20GEN%205/Documents/WORK%20AND%20PLAN/AZURE%20SYSTEM-AUTH%20AT%20SCALE/migrations).
3. **Self-Documenting**: New scripts must include a top-level docstring detailing their objective, requirements, and CLI flags.
