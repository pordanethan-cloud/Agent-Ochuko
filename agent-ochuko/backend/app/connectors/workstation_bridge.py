# app/connectors/workstation_bridge.py
"""
Agent Ochuko Local Workstation Companion Bridge.
A lightweight local server that runs on the user's physical machine (e.g. Windows / Mac / Linux)
and exposes secure local file reading, writing, directory listing, and shell execution to Agent Ochuko.
Operates on http://127.0.0.1:3920 with CORS enabled for the Agent Ochuko web application.
"""

import os
import sys
import re
import time
import json
import glob
import shlex
import shutil
import getpass
import platform
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone
from typing import Optional

PORT = 3920

_PROMPT_INJECTION_RE = re.compile(
    r"(?i)\b(ignore\s+(?:all\s+)?previous\s+instructions|"
    r"disregard\s+(?:all\s+)?prior\s+(?:directives|instructions)|"
    r"you\s+are\s+now\s+in\s+debug\s+mode|"
    r"system\s*prompt\s*:|"
    r"override\s+system\s+prompt|"
    r"new\s+system\s+instruction|"
    r"bypass\s+(?:all\s+)?safety\s+filter|"
    r"dan\s+mode)\b"
)

# Standard directory names to exclude from directory listings to preserve token limits
_BLOAT_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", ".git", ".svn",
    ".hg", "dist", "build", ".next", ".nuxt", ".turbo", ".cache",
}


def _format_relative_time(timestamp: float) -> str:
    """Formats epoch timestamp into concise human-readable relative time string."""
    diff = max(0, time.time() - timestamp)
    if diff < 60:
        return "<1m ago"
    elif diff < 3600:
        return f"{int(diff // 60)}m ago"
    elif diff < 86400:
        return f"{int(diff // 3600)}h ago"
    elif diff < 604800:
        return f"{int(diff // 86400)}d ago"
    return f"{int(diff // 604800)}w ago"


def _format_size(size_bytes: int) -> str:
    """Formats raw byte count into compact human-readable string."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes // 1024}KB"
    return f"{(size_bytes / (1024 * 1024)):.1f}MB"


def _compact_stream(text: str, head_lines: int = 20, tail_lines: int = 35) -> str:
    """
    Truncates large subprocess output to head and tail blocks to optimize token economy
    while preserving compiler initialization and bottom failure stack traces / exit summaries.
    """
    if not text:
        return ""
    lines = text.splitlines(keepends=True)
    total = len(lines)
    if total <= 60:
        return text

    head = "".join(lines[:head_lines])
    tail = "".join(lines[-tail_lines:])
    omitted = total - head_lines - tail_lines
    banner = f"\n[... {omitted} lines omitted to optimize tokens & context window ...]\n"
    return f"{head}{banner}{tail}"


def _backup_file(filepath: str) -> Optional[str]:
    """
    Creates a backup of the file before overwriting, storing all backups in a single
    centralized folder (~/.ochuko/pc_bak) regardless of the file's original location.
    """
    try:
        if not os.path.exists(filepath) or not os.path.isfile(filepath):
            return None
        backup_dir = os.path.join(os.path.expanduser("~"), ".ochuko", "pc_bak")
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        base = os.path.basename(filepath)
        backup_filename = f"{base}.{ts}.bak"
        backup_path = os.path.join(backup_dir, backup_filename)
        shutil.copy2(filepath, backup_path)
        return backup_path
    except Exception:
        return None


def get_standard_user_folders():
    """Detects standard OS directories (Downloads, Documents, Desktop)."""
    home = os.path.expanduser("~")
    return {
        "home": home,
        "downloads": os.path.join(home, "Downloads"),
        "documents": os.path.join(home, "Documents"),
        "desktop": os.path.join(home, "Desktop"),
    }


def resolve_local_path(target_path: str, cwd: Optional[str] = None) -> str:
    """
    Resolves relative or friendly aliases like 'downloads' to the physical absolute path.
    Includes reverse-mtime fuzzy probing as a fallback if the exact path does not exist.
    """
    if not target_path or target_path.strip() in (".", "./", ""):
        return cwd or os.getcwd()

    t = target_path.strip().strip("'\"")
    base_dir = cwd or os.getcwd()
    folders = get_standard_user_folders()

    # 1. Friendly folder alias support
    lower_t = t.lower()
    if lower_t in ("downloads", "download", "my downloads", "my download folder"):
        return folders["downloads"]
    if lower_t in ("desktop", "my desktop"):
        return folders["desktop"]
    if lower_t in ("documents", "my documents"):
        return folders["documents"]

    # Natural language phrases: "books folder in documents", "books in documents"
    m_in = re.match(r"(?:my\s+)?(.+?)(?:\s+folder|\s+directory)?\s+(?:in|under|inside)\s+(documents|downloads|desktop|home)\b", lower_t)
    if m_in:
        sub_name = m_in.group(1).strip()
        parent_alias = m_in.group(2).strip()
        parent_dir = folders.get(parent_alias, folders["documents"])
        cand_in = os.path.normpath(os.path.join(parent_dir, sub_name))
        if os.path.exists(cand_in):
            return cand_in
        if os.path.exists(parent_dir):
            try:
                for entry in os.scandir(parent_dir):
                    if entry.name.lower() == sub_name.lower():
                        return os.path.normpath(entry.path)
            except Exception:
                pass

    if t.startswith("~"):
        return os.path.normpath(os.path.expanduser(t))

    # 2. Absolute path rule
    if os.path.isabs(t) or (len(t) > 2 and t[1] == ":" and t[2] in ("\\", "/")):
        return os.path.normpath(t)

    # 2b. Check if path starts with friendly alias like "documents/..." or "downloads/..."
    clean_slash = t.replace("\\", "/")
    for alias_name in ("documents", "downloads", "desktop", "home"):
        if clean_slash.lower().startswith(f"{alias_name}/"):
            sub_rel = clean_slash[len(alias_name) + 1:]
            cand_alias = os.path.normpath(os.path.join(folders[alias_name], sub_rel))
            if os.path.exists(cand_alias):
                return cand_alias
            # Case-insensitive first-segment lookup ("documents/books/x"
            # -> "~/Documents/BOOKS/x"). Returns the host path even when it
            # doesn't exist yet — writes create missing parents.
            if os.path.exists(folders[alias_name]):
                parts = sub_rel.replace("\\", "/").split("/")
                try:
                    for entry in os.scandir(folders[alias_name]):
                        if entry.name.lower() == parts[0].lower():
                            return os.path.normpath(os.path.join(entry.path, *parts[1:]))
                except Exception:
                    pass
                return cand_alias

    # 3. Explicit directory separator rule (e.g. sub/test.txt) -> join directly with base_dir
    if "/" in t or "\\" in t:
        return os.path.normpath(os.path.join(base_dir, t))

    # 4. Check if exact file exists in base_dir or home
    candidate = os.path.normpath(os.path.join(base_dir, t))
    if os.path.exists(candidate):
        return candidate

    home_candidate = os.path.normpath(os.path.join(folders["home"], t))
    if os.path.exists(home_candidate):
        return home_candidate

    # 5. Fallback fuzzy recent-file probing for single words/filenames (>= 3 chars, no separators)
    if len(t) >= 3 and not any(c in t for c in ("*", "?", "\n", "\r")):
        clean_needle = t.lower()
        needle_root = os.path.splitext(clean_needle)[0] if "." in clean_needle else clean_needle
        fuzzy_matches = []
        probe_dirs = [base_dir, folders["downloads"], folders["desktop"], folders["documents"]]
        seen_dirs = set()
        for probe_dir in probe_dirs:
            if not probe_dir or probe_dir in seen_dirs or not os.path.exists(probe_dir) or not os.path.isdir(probe_dir):
                continue
            seen_dirs.add(probe_dir)
            try:
                for entry in os.scandir(probe_dir):
                    entry_name_lower = entry.name.lower()
                    if needle_root in entry_name_lower or clean_needle in entry_name_lower:
                        try:
                            st = entry.stat()
                            fuzzy_matches.append((st.st_mtime, os.path.normpath(entry.path)))
                        except Exception:
                            continue
            except Exception:
                continue

        if fuzzy_matches:
            fuzzy_matches.sort(key=lambda x: x[0], reverse=True)
            return fuzzy_matches[0][1]

    return candidate


class WorkstationBridgeHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler for Workstation Bridge."""

    def _set_cors_headers(self, status=200, content_type="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")
        self.end_headers()

    def do_OPTIONS(self):
        self._set_cors_headers(200)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        params = parse_qs(parsed.query)

        # 1. Health check
        if path in ("/health", "/status", "/"):
            folders = get_standard_user_folders()
            data = {
                "status": "online",
                "service": "agent-ochuko-workstation-bridge",
                "version": "1.0.0",
                "platform": platform.system(),
                "os_release": platform.release(),
                "username": getpass.getuser(),
                "hostname": platform.node(),
                "standard_folders": folders,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            self._set_cors_headers(200)
            self.wfile.write(json.dumps(data, indent=2).encode("utf-8"))
            return

        # 2. List directory (compact token-efficient listing, max 25 items sorted newest first)
        elif path == "/list":
            target = params.get("path", ["."])[0]
            pattern = params.get("pattern", [""])[0].strip().lower()
            resolved = resolve_local_path(target)
            if not os.path.exists(resolved):
                self._set_cors_headers(404)
                self.wfile.write(json.dumps({"error": f"Path '{target}' (resolved: '{resolved}') does not exist."}).encode("utf-8"))
                return

            if not os.path.isdir(resolved):
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": f"Path '{resolved}' is a file, not a directory."}).encode("utf-8"))
                return

            try:
                raw_entries = []
                for item in os.scandir(resolved):
                    if item.name.startswith(".") and item.name not in (".env", ".dockerignore", ".gitignore"):
                        continue
                    # Skip bloat dependency & build directories unless explicitly requested in pattern
                    if item.is_dir() and item.name.lower() in _BLOAT_DIRS:
                        if not pattern or item.name.lower() not in pattern:
                            continue
                    if pattern and pattern not in item.name.lower():
                        continue
                    is_d = item.is_dir()
                    try:
                        st = item.stat()
                        st_mtime = st.st_mtime
                        size = st.st_size if not is_d else 0
                        mtime_str = datetime.fromtimestamp(st_mtime).strftime("%Y-%m-%d %H:%M")
                        rel_time = _format_relative_time(st_mtime)
                        size_fmt = _format_size(size) if not is_d else "<DIR>"
                    except Exception:
                        st_mtime = 0
                        size = 0
                        mtime_str = ""
                        rel_time = ""
                        size_fmt = "<DIR>" if is_d else "0B"

                    raw_entries.append({
                        "mtime_epoch": st_mtime,
                        "name": item.name,
                        "path": os.path.join(resolved, item.name),
                        "is_dir": is_d,
                        "size": size,
                        "size_formatted": size_fmt,
                        "modified": mtime_str,
                        "relative_time": rel_time,
                    })

                # Sort by modification time descending (newest items first)
                raw_entries.sort(key=lambda e: e["mtime_epoch"], reverse=True)

                resp = {
                    "success": True,
                    "target_path": target,
                    "resolved_path": resolved,
                    "total_count": len(raw_entries),
                    "entries": raw_entries[:25],
                }
                self._set_cors_headers(200)
                self.wfile.write(json.dumps(resp).encode("utf-8"))
                return
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return

        # 3. Read file (chunked line-offset reading with max 50KB token guard & injection scanner)
        elif path == "/read":
            target = params.get("path", [""])[0]
            if not target:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": "Query parameter 'path' is required."}).encode("utf-8"))
                return

            resolved = resolve_local_path(target)
            if not os.path.exists(resolved):
                self._set_cors_headers(404)
                self.wfile.write(json.dumps({"error": f"File '{target}' (resolved: '{resolved}') does not exist."}).encode("utf-8"))
                return

            if os.path.isdir(resolved):
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": f"'{resolved}' is a directory, not a file."}).encode("utf-8"))
                return

            try:
                sz = os.path.getsize(resolved)
                offset = int(params.get("offset", [0])[0])
                length = int(params.get("length", [35000])[0])
                length = min(max(100, length), 50000)

                start_line = int(params["start_line"][0]) if "start_line" in params else None
                end_line = int(params["end_line"][0]) if "end_line" in params else None

                if start_line is not None or end_line is not None:
                    s_line = max(1, start_line or 1)
                    e_line = end_line or (s_line + 500)
                    with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                        lines = f.readlines()
                    total_lines = len(lines)
                    selected_lines = lines[s_line - 1 : e_line]
                    content = "".join(selected_lines)
                    is_trunc = e_line < total_lines
                    if len(content.encode("utf-8")) > length:
                        content = content[:length]
                        is_trunc = True
                else:
                    with open(resolved, "r", encoding="utf-8", errors="replace") as f:
                        if offset > 0:
                            f.seek(offset)
                        content = f.read(length)
                    is_trunc = (offset + length) < sz

                # Prompt-Injection Guard Scan
                has_inj = False
                inj_directive = ""
                inj_match = _PROMPT_INJECTION_RE.search(content)
                if inj_match:
                    has_inj = True
                    inj_directive = inj_match.group(0)

                resp = {
                    "success": True,
                    "target_path": target,
                    "resolved_path": resolved,
                    "size_bytes": sz,
                    "offset": offset,
                    "content": content,
                    "is_truncated": is_trunc,
                    "has_prompt_injection": has_inj,
                    "injection_directive": inj_directive,
                }
                self._set_cors_headers(200)
                self.wfile.write(json.dumps(resp).encode("utf-8"))
                return
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return

        else:
            self._set_cors_headers(404)
            self.wfile.write(json.dumps({"error": "Unknown endpoint"}).encode("utf-8"))

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else "{}"
        try:
            payload = json.loads(body)
        except Exception:
            payload = {}

        # 1. Write file
        if path == "/write":
            target = payload.get("path", "")
            content = payload.get("content", "")
            if not target:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": "'path' is required."}).encode("utf-8"))
                return

            resolved = resolve_local_path(target)
            # Alias paths must land in the REAL user folder, never nested under
            # the bridge process cwd (agents often run with cwd=.../backend,
            # which would swallow alias writes into backend/documents/...).
            cwd_docs = os.path.normcase(os.path.normpath(os.path.join(os.getcwd(), "Documents")))
            resolved_norm = os.path.normcase(os.path.normpath(resolved))
            if resolved_norm == cwd_docs or resolved_norm.startswith(cwd_docs + os.sep):
                try:
                    sys.stderr.write(
                        f"[Bridge] WARNING: alias '{target}' resolved under bridge cwd "
                        f"({resolved}); remapping to ~/Documents.\n"
                    )
                except Exception:
                    pass
                rel = os.path.relpath(resolved, os.path.join(os.getcwd(), "Documents"))
                resolved = os.path.normpath(os.path.join(os.path.expanduser("~"), "Documents", rel))
            try:
                parent = os.path.dirname(resolved)
                if parent and not os.path.exists(parent):
                    os.makedirs(parent, exist_ok=True)

                # Centralized backup in ~/.ochuko/pc_bak before overwriting
                backup_path = _backup_file(resolved)

                with open(resolved, "w", encoding="utf-8", errors="replace") as f:
                    f.write(content)

                sz = len(content.encode("utf-8"))
                resp = {
                    "success": True,
                    "target_path": target,
                    "resolved_path": resolved,
                    "bytes_written": sz,
                    "backup_path": backup_path,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                # Compact single-line log to the bridge console so host writes are auditable
                try:
                    print(f"[Bridge WRITE] {target} -> {resolved} ({sz} bytes)", flush=True)
                except Exception:
                    pass
                self._set_cors_headers(200)
                self.wfile.write(json.dumps(resp).encode("utf-8"))
                return
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return

        # 2. Execute command
        elif path == "/exec":
            cmd = payload.get("command", "")
            cwd = payload.get("cwd", ".")
            timeout = int(payload.get("timeout", 60))
            if not cmd:
                self._set_cors_headers(400)
                self.wfile.write(json.dumps({"error": "'command' is required."}).encode("utf-8"))
                return

            resolved_cwd = resolve_local_path(cwd)
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=resolved_cwd,
                    capture_output=True,
                    text=True,
                    timeout=timeout,
                )
                resp = {
                    "success": proc.returncode == 0,
                    "exit_code": proc.returncode,
                    "stdout": _compact_stream(proc.stdout or ""),
                    "stderr": _compact_stream(proc.stderr or ""),
                    "cwd": resolved_cwd,
                }
                self._set_cors_headers(200)
                self.wfile.write(json.dumps(resp).encode("utf-8"))
                return
            except subprocess.TimeoutExpired:
                self._set_cors_headers(408)
                self.wfile.write(json.dumps({"error": f"Command timed out after {timeout} seconds."}).encode("utf-8"))
                return
            except Exception as e:
                self._set_cors_headers(500)
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
                return

        else:
            self._set_cors_headers(404)
            self.wfile.write(json.dumps({"error": "Unknown endpoint"}).encode("utf-8"))

    def log_message(self, format, *args):
        # Clean custom logging without spam
        sys.stderr.write(f"[{datetime.now().strftime('%H:%M:%S')}] WorkstationBridge: {format % args}\n")


def run_bridge(port=PORT):
    server = HTTPServer(("127.0.0.1", port), WorkstationBridgeHandler)
    folders = get_standard_user_folders()
    print("=" * 60)
    print(" AGENT OCHUKO WORKSTATION COMPANION BRIDGE")
    print("=" * 60)
    print(f"Status: Online on http://127.0.0.1:{port}")
    print(f"Host:   {platform.node()} ({platform.system()} {platform.release()})")
    print(f"User:   {getpass.getuser()}")
    print(f"Downloads: {folders['downloads']}")
    print("-" * 60)
    print("Agent Ochuko now has secure local read, write, and terminal access to your workstation.")
    print("Press Ctrl+C to stop.\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Workstation Bridge...")
        server.server_close()


if __name__ == "__main__":
    import argparse

    _parser = argparse.ArgumentParser(description="Agent Ochuko Workstation Companion Bridge")
    _parser.add_argument("--port", type=int, default=PORT)
    _parser.add_argument("--host", default="127.0.0.1")
    _args = _parser.parse_args()
    PORT = _args.port
    run_bridge(port=_args.port)
