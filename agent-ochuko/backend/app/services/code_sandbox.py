# app/services/code_sandbox.py
"""
Code Sandbox Execution Service.
Provides secure, isolated subprocess execution for Python and JavaScript (Node.js) code.
Features auto-installation of missing modules cached in a global workspace directory.
"""
import os
import sys
import uuid
import re
import logging
import asyncio
import subprocess
import shutil
from typing import Tuple, List, Dict

def _find_bash_executable() -> str:
    # 1. Check Git directory first if on Windows (to prefer Git Bash over WSL)
    if os.name == 'nt':
        git_path = shutil.which("git")
        if git_path:
            git_dir = os.path.dirname(os.path.dirname(git_path))
            for candidate in (
                os.path.join(git_dir, "bin", "bash.exe"),
                os.path.join(git_dir, "usr", "bin", "bash.exe"),
                os.path.join(git_dir, "bin", "sh.exe")
            ):
                if os.path.exists(candidate):
                    return candidate
        
        # Look in standard program files location if git path check failed
        for prog_files in ("C:\\Program Files", "C:\\Program Files (x86)"):
            git_dir = os.path.join(prog_files, "Git")
            for candidate in (
                os.path.join(git_dir, "bin", "bash.exe"),
                os.path.join(git_dir, "usr", "bin", "bash.exe"),
                os.path.join(git_dir, "bin", "sh.exe")
            ):
                if os.path.exists(candidate):
                    return candidate

    # 2. Check PATH
    bash_path = shutil.which("bash")
    if bash_path:
        if os.name == 'nt' and "system32" in bash_path.lower():
            pass
        else:
            return bash_path
            
    # 3. Default fallback
    return "/bin/bash"

logger = logging.getLogger("app.services.code_sandbox")

# Define global persistent library paths
import tempfile
GLOBAL_LIBS_DIR = os.environ.get("SANDBOX_LIBS_DIR") or (
    os.path.join(tempfile.gettempdir(), "ochuko_sandbox_libs")
    if os.name == "nt"
    else "/app/sandbox_libs"
)
PYTHON_LIBS_DIR = os.path.join(GLOBAL_LIBS_DIR, "python_packages")
NODE_LIBS_DIR = os.path.join(GLOBAL_LIBS_DIR, "node_modules")

# Ensure persistent directories exist
os.makedirs(PYTHON_LIBS_DIR, exist_ok=True)
os.makedirs(NODE_LIBS_DIR, exist_ok=True)



def _run_subprocess_sync(cmd: List[str], cwd: str, env: dict, timeout_seconds: int) -> Tuple[int, str, str]:
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=cwd,
            env=env
        )
        stdout_bytes, stderr_bytes = proc.communicate(timeout=timeout_seconds)
        stdout_str = stdout_bytes.decode("utf-8", errors="replace")
        stderr_str = stderr_bytes.decode("utf-8", errors="replace")
        return proc.returncode, stdout_str, stderr_str
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        return -1, "", f"Execution Timeout (exceeded {timeout_seconds}s limit)"
    except Exception as e:
        return -1, "", str(e)


def _normalize_sandbox_code_paths(code: str) -> str:
    normalized = re.sub(r'(?i)/tmp/sandbox_[^/\s"\']+/data/?', '../data/', code)
    normalized = re.sub(r'(?i)/tmp/sandbox_[^/\s"\']+/src/?', './', normalized)
    normalized = re.sub(r'(?i)/tmp/sandbox_[^/\s"\']/?', '../', normalized)
    normalized = re.sub(r'(?i)/mnt/data/?', '../data/', normalized)
    normalized = re.sub(r'(?i)/workspace/?', '../data/', normalized)
    return normalized


async def mount_conversation_files(user_id: str, conversation_id: str, work_dir: str) -> List[str]:
    """
    Lists files uploaded by the user under uploads/{user_id}/{conversation_id}/
    in R2, downloads them, and saves them to the sandbox work_dir using
    their original filenames (stripping the unique UUID prefix).
    """
    import boto3
    from botocore.config import Config

    access_key = os.environ.get("R2_ACCESS_KEY_ID")
    secret_key = os.environ.get("R2_SECRET_ACCESS_KEY")
    endpoint = os.environ.get("R2_ENDPOINT")
    bucket = os.getenv("R2_BUCKET_NAME", "agent-ochuko-storage")

    if not all([access_key, secret_key, endpoint]):
        logger.warning("R2 credentials not configured; skipping conversation file mounting.")
        return []

    prefix = f"uploads/{user_id}/{conversation_id}/"
    mounted_files = []

    def _do_list_and_download():
        s3_client = boto3.client(
            "s3",
            endpoint_url=endpoint,
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            config=Config(signature_version="s3v4")
        )
        try:
            res = s3_client.list_objects_v2(Bucket=bucket, Prefix=prefix)
            if "Contents" not in res:
                return []

            for obj in res["Contents"]:
                key = obj["Key"]
                filename_part = key.split("/")[-1]
                if not filename_part:
                    continue
                # Extract original filename (skipping UUID prefix if structured as unique_id_name)
                # Structure is uploads/user_id/convo_id/{32_hex_chars}_{original_name}
                if len(filename_part) <= 33:
                    original_name = filename_part
                else:
                    original_name = filename_part[33:]

                target_path = os.path.join(work_dir, original_name)
                logger.info(f"Mounting conversation file from R2: {key} -> {target_path}")
                s3_client.download_file(bucket, key, target_path)
                mounted_files.append(original_name)
        except Exception as e:
            logger.error(f"Error mounting conversation files from R2: {e}", exc_info=True)
        return mounted_files

    return await asyncio.to_thread(_do_list_and_download)


# ── Sandbox navigation helpers (sandbox_ls / sandbox_read / sandbox_write) ────
# The model navigates its own conversation workspace on demand instead of the
# backend injecting file contents into every turn. Paths are resolved inside
# the conversation's data/ dir only (traversal-safe).

_SANDBOX_IGNORED_DIRS = {".git", "node_modules", ".venv", "__pycache__"}


def _resolve_sandbox_path(conversation_id: str, subpath: str = "") -> str:
    """Resolve a sandbox-relative path, refusing traversal outside data/."""
    data_dir = os.path.abspath(
        os.path.join(tempfile.gettempdir(), f"sandbox_{conversation_id}", "data")
    )
    target = os.path.abspath(os.path.join(data_dir, subpath or ""))
    if target != data_dir and not target.startswith(data_dir + os.sep):
        raise ValueError(f"Path escapes the sandbox: {subpath!r}")
    return target


async def sandbox_list_files(conversation_id: str, subpath: str = "") -> str:
    """Lists the conversation sandbox tree with sizes. Traversal-safe."""
    def _list():
        root = _resolve_sandbox_path(conversation_id, subpath)
        if not os.path.exists(root):
            return f"Sandbox path '{subpath or '/'}' does not exist yet."
        if os.path.isfile(root):
            return f"{subpath} · {os.path.getsize(root)} bytes"
        entries = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SANDBOX_IGNORED_DIRS]
            for f in filenames:
                full = os.path.join(dirpath, f)
                rel = os.path.relpath(full, root).replace("\\", "/")
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                entries.append(f"- {rel} ({size} bytes)")
        if not entries:
            return "Sandbox is empty. Use sandbox_write or execute_code to create files."
        header = f"Sandbox contents ({subpath or 'root'}):"
        return header + "\n" + "\n".join(entries[:100])
    return await asyncio.to_thread(_list)


async def sandbox_read_file(conversation_id: str, subpath: str, offset: int = 0, max_bytes: int = 4000) -> str:
    """Reads a slice of a sandbox text file. Returns metadata + content."""
    def _read():
        target = _resolve_sandbox_path(conversation_id, subpath)
        if not os.path.isfile(target):
            return f"sandbox_read error: '{subpath}' not found. Use sandbox_ls to list files."
        size = os.path.getsize(target)
        with open(target, "rb") as f:
            f.seek(max(0, offset))
            chunk = f.read(max(256, min(max_bytes, 16000)))
        try:
            text = chunk.decode("utf-8")
        except UnicodeDecodeError:
            return f"'{subpath}' is binary ({size} bytes) — use execute_code to inspect it."
        parts = [f"'{subpath}' · {size} bytes total · showing bytes {offset}–{offset + len(chunk)}"]
        if offset + len(chunk) < size:
            parts.append(f"[... {size - offset - len(chunk)} more bytes — call again with offset={offset + len(chunk)} ...]")
        parts.append(text)
        return "\n".join(parts)
    return await asyncio.to_thread(_read)


async def sandbox_write_file(conversation_id: str, subpath: str, content: str) -> str:
    """Writes a complete file into the sandbox data/ dir. Returns a one-line receipt."""
    def _write():
        target = _resolve_sandbox_path(conversation_id, subpath)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        data = content.encode("utf-8")
        with open(target, "wb") as f:
            f.write(data)
        preview = content.strip().replace("\n", " ")[:200]
        return f"WROTE {subpath} · {len(data)} bytes · starts: {preview!r}"
    return await asyncio.to_thread(_write)


async def execute_code_in_sandbox(
    code: str,
    language: str,
    conversation_id: str,
    user_id: str = "00000000-0000-0000-0000-000000000000",
    timeout_seconds: int = 45
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Executes Python or JavaScript code inside a secure local sandbox.
    Captures stdout, stderr, and uploads any generated files to R2 storage.
    Automatically catches missing module errors and installs/caches them.
    """
    language = language.lower().strip()
    
    # 1. Create segregated directories inside the workspace
    import tempfile
    tmp_base = tempfile.gettempdir()
    work_dir = os.path.abspath(os.path.join(tmp_base, f"sandbox_{conversation_id}")).replace("\\", "/")
    src_dir = os.path.join(work_dir, "src")
    data_dir = os.path.join(work_dir, "data")

    
    os.makedirs(src_dir, exist_ok=True)
    os.makedirs(data_dir, exist_ok=True)

    # Mount files: Download from Google Drive (primary), fall back to R2
    mounted_files = []
    if conversation_id and conversation_id != "00000000-0000-0000-0000-000000000000":
        try:
            from app.services.google_drive import download_google_drive_files
            google_files = await download_google_drive_files(user_id, conversation_id, data_dir)
            mounted_files.extend(google_files)
        except Exception as gd_err:
            logger.warning(f"Google Drive download failed: {gd_err}")
            
        # Mount from R2 as fallback / cache layer to data_dir
        try:
            r2_files = await mount_conversation_files(user_id, conversation_id, data_dir)
            mounted_files.extend(r2_files)
        except Exception as r2_err:
            logger.warning(f"R2 mount failed: {r2_err}")

    # Remove duplicates from mounted list
    mounted_files = list(set(mounted_files))

    # Record modification times of existing files inside data_dir before execution
    before_files = {}
    for root, dirs, files_in_dir in os.walk(data_dir):
        if any(ignored in root for ignored in (".git", "node_modules", ".venv", "__pycache__")):
            continue
        for file in files_in_dir:
            path = os.path.join(root, file)
            try:
                before_files[path] = os.path.getmtime(path)
            except OSError:
                pass
                
    # Copy files from data_dir to src_dir for backward compatibility with local path references
    for root, dirs, files_in_dir in os.walk(data_dir):
        if any(ignored in root for ignored in (".git", "node_modules", ".venv", "__pycache__")):
            continue
        for file in files_in_dir:
            data_file_path = os.path.join(root, file)
            rel_path = os.path.relpath(data_file_path, data_dir)
            src_file_path = os.path.join(src_dir, rel_path)
            os.makedirs(os.path.dirname(src_file_path), exist_ok=True)
            try:
                shutil.copy2(data_file_path, src_file_path)
            except Exception as copy_err:
                logger.warning(f"Failed to copy file {file} to src_dir for execution compatibility: {copy_err}")
    
    # Prepare clean environment variables (excluding sensitive keys)
    env = os.environ.copy()
    sensitive_keys = [
        "SUPABASE_KEY", "SUPABASE_SERVICE_KEY", "OPENAI_API_KEY", 
        "R2_SECRET_ACCESS_KEY", "R2_ACCESS_KEY_ID", "JWT_SECRET"
    ]
    for key in sensitive_keys:
        env.pop(key, None)
        
    env["PYTHONPATH"] = PYTHON_LIBS_DIR
    env["NODE_PATH"] = NODE_LIBS_DIR

    stdout_str = ""
    stderr_str = ""
    generated_files: List[Dict[str, str]] = []

    try:
        if language in ("bash", "shell", "sh"):
            # Bash/Shell execution path
            script_path = os.path.join(src_dir, "command.sh")
            normalized_code = _normalize_sandbox_code_paths(code)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(normalized_code)
                
            bash_executable = _find_bash_executable()
            ret_code, stdout_str, stderr_str = await asyncio.to_thread(
                _run_subprocess_sync,
                [bash_executable, "command.sh"],
                src_dir,
                env,
                timeout_seconds
            )
            if ret_code == -1 and "Timeout" in stderr_str:
                return "Execution Timeout (exceeded 45s limit)", []

        elif language == "javascript" or language == "js" or language == "node":
            # JS execution path
            script_path = os.path.join(src_dir, "script.js")
            normalized_code = _normalize_sandbox_code_paths(code)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(normalized_code)
                
            for attempt in range(3):
                ret_code, stdout_str, stderr_str = await asyncio.to_thread(
                    _run_subprocess_sync,
                    ["node", script_path],
                    src_dir,
                    env,
                    timeout_seconds
                )
                if ret_code == -1 and "Timeout" in stderr_str:
                    return "Execution Timeout (exceeded 45s limit)", []
                    
                if ret_code == 0:
                    break
                    
                # Auto-install missing node packages if possible
                if "Cannot find module" in stderr_str:
                    m = re.search(r"Cannot find module ['\"](.*?)['\"]", stderr_str)
                    if m:
                        missing_pkg = m.group(1)
                        if not missing_pkg.startswith((".", "/")):
                            logger.info(f"Auto-installing JS package: {missing_pkg}")
                            await asyncio.to_thread(
                                _run_subprocess_sync,
                                ["npm", "install", "--prefix", GLOBAL_LIBS_DIR, missing_pkg],
                                src_dir,
                                env,
                                60
                            )
                            continue
                break
        else:
            # Python execution path
            script_path = os.path.join(src_dir, "script.py")
            normalized_code = _normalize_sandbox_code_paths(code)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(normalized_code)
                
            for attempt in range(3):
                ret_code, stdout_str, stderr_str = await asyncio.to_thread(
                    _run_subprocess_sync,
                    [sys.executable, script_path],
                    src_dir,
                    env,
                    timeout_seconds
                )
                if ret_code == -1 and "Timeout" in stderr_str:
                    return "Execution Timeout (exceeded 45s limit)", []
                    
                if ret_code == 0:
                    break
                    
                # Auto-install missing Python packages if possible
                if "ModuleNotFoundError" in stderr_str or "ImportError" in stderr_str:
                    m = re.search(r"No module named ['\"](.*?)['\"]", stderr_str)
                    if m:
                        missing_pkg = m.group(1)
                        pkg_map = {
                            "yaml": "pyyaml",
                            "PIL": "Pillow",
                            "docx": "python-docx",
                            "fitz": "PyMuPDF",
                            "cv2": "opencv-python-headless",
                            "sklearn": "scikit-learn",
                            "bs4": "beautifulsoup4",
                        }
                        install_name = pkg_map.get(missing_pkg, missing_pkg)
                        
                        logger.info(f"Auto-installing Python package: {install_name}")
                        await asyncio.to_thread(
                            _run_subprocess_sync,
                            [sys.executable, "-m", "pip", "install", "--target", PYTHON_LIBS_DIR, install_name],
                            src_dir,
                            env,
                            60
                        )
                        continue
                break

        # Copy any newly created or modified files in src_dir back to data_dir for storage persistence
        for root, dirs, files_in_dir in os.walk(src_dir):
            if any(ignored in root for ignored in (".git", "node_modules", ".venv", "__pycache__")):
                continue
            for file in files_in_dir:
                if file in ("script.py", "script.js", "command.sh"):
                    continue
                src_file_path = os.path.join(root, file)
                rel_path = os.path.relpath(src_file_path, src_dir)
                dest_file_path = os.path.join(data_dir, rel_path)
                
                # Check if it is a new file or modified
                is_changed = False
                if not os.path.exists(dest_file_path):
                    is_changed = True
                else:
                    try:
                        is_changed = os.path.getmtime(src_file_path) > os.path.getmtime(dest_file_path)
                    except OSError:
                        is_changed = True
                        
                if is_changed:
                    os.makedirs(os.path.dirname(dest_file_path), exist_ok=True)
                    try:
                        shutil.copy2(src_file_path, dest_file_path)
                        logger.info(f"Copied execution output file {file} from src/ to data/: {dest_file_path}")
                    except Exception as copy_err:
                        logger.warning(f"Failed to copy execution output file {file} to data_dir: {copy_err}")

        # 2. Upload any created/generated files in the data directory to Google Drive and R2
        from app.api.v1.endpoints.chat import _upload_generated_file
        from app.services.supabase_admin import get_supabase_admin
        # Sync generated files to Google Drive first if available
        google_uploaded = []
        try:
            from app.services.google_drive import upload_to_google_drive
            google_uploaded = await upload_to_google_drive(user_id, conversation_id, data_dir)
        except Exception as gd_err:
            logger.warning(f"Google Drive sync skipped or unavailable: {gd_err}")
            google_uploaded = []

        
        for root, dirs, files_in_dir in os.walk(data_dir):
            # Skip scanning dependency and version control directories
            if any(ignored in root for ignored in (".git", "node_modules", ".venv", "__pycache__")):
                continue

            # Skip files from cloned git repos (check for .git in parent dirs)
            is_external_repo = False
            check_path = root
            while check_path != data_dir:
                if os.path.exists(os.path.join(check_path, ".git")):
                    is_external_repo = True
                    break
                check_path = os.path.dirname(check_path)
            if is_external_repo:
                continue  # Skip external repo files
            for file in files_in_dir:
                if file in ("script.py", "script.js", "command.sh"):
                    continue
                file_path = os.path.join(root, file)
                try:
                    mtime = os.path.getmtime(file_path)
                    # Only upload if the file is new or modified during this run
                    if file_path not in before_files or mtime > before_files[file_path]:
                        with open(file_path, "rb") as f:
                            file_bytes = f.read()

                        # Preserve the project-relative path (repo-style uploads):
                        # css/styles.css lands at generated/{conv}/css/styles.css so
                        # relative links between files keep working on the CDN.
                        rel_path = os.path.relpath(file_path, data_dir).replace("\\", "/")

                        # Auto-resolve MIME type via guess_type
                        import mimetypes
                        mime, _ = mimetypes.guess_type(file)
                        if not mime:
                            mime = "application/octet-stream"

                        # Upload to R2 for fast preview CDN
                        r2_url = await _upload_generated_file(
                            file_bytes=file_bytes,
                            filename=rel_path,
                            mime_type=mime,
                            conversation_id=conversation_id,
                            user_id=user_id
                        )

                        # Use Google Drive URL for client download / preview
                        download_url = r2_url
                        gd_match = next((gf for gf in google_uploaded if gf["filename"] == file), None)
                        if gd_match:
                            download_url = gd_match.get("download_url") or r2_url

                        generated_files.append({
                            "filename": rel_path,
                            "download_url": download_url,
                            "size_bytes": len(file_bytes)
                        })
                except Exception as upload_err:
                    logger.warning(f"Failed to upload sandbox file {file}: {upload_err}")

        # ── ZIP bundle if multiple new files were produced ────────────────────────
        if len(generated_files) > 1:
            import zipfile
            import io as _io

            zip_buf = _io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                for root, dirs, files_in_dir in os.walk(data_dir):
                    dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "__pycache__")]
                    for file in files_in_dir:
                        if file in ("script.py", "script.js", "command.sh"):
                            continue
                        file_path = os.path.join(root, file)
                        # arcname is relative to data_dir so the zip has a clean flat/nested structure
                        arcname = os.path.relpath(file_path, data_dir)
                        try:
                            zf.write(file_path, arcname=arcname)
                        except OSError as ze:
                            logger.warning("ZIP: skipping %s: %s", file, ze)

            zip_bytes = zip_buf.getvalue()
            if zip_bytes:
                try:
                    # Save zip file locally to data_dir so it gets synced/uploaded to Google Drive too
                    zip_file_path = os.path.join(data_dir, "project.zip")
                    with open(zip_file_path, "wb") as zf_file:
                        zf_file.write(zip_bytes)
                        
                    # Sync ZIP to Google Drive
                    try:
                        zip_google = await upload_to_google_drive(user_id, conversation_id, data_dir)
                    except Exception as gd_err:
                        logger.warning(f"Failed to upload ZIP to Google Drive: {gd_err}")
                        zip_google = []
                        
                    zip_url = await _upload_generated_file(
                        file_bytes=zip_bytes,
                        filename="project.zip",
                        mime_type="application/zip",
                        conversation_id=conversation_id,
                        user_id=user_id,
                    )
                    
                    download_url = zip_url
                    gd_match = next((gf for gf in zip_google if gf["filename"] == "project.zip"), None)
                    if gd_match:
                        download_url = gd_match.get("download_url") or zip_url
                        
                    generated_files.append({
                        "filename": "project.zip",
                        "download_url": download_url,
                        "size_bytes": len(zip_bytes),
                    })
                    logger.info(
                        "sandbox ZIP: %d files, %d bytes → %s",
                        len(generated_files) - 1, len(zip_bytes), download_url,
                    )
                except Exception as zip_err:
                    logger.warning("ZIP upload failed: %s", zip_err)

    except Exception as run_err:
        logger.error(f"Sandbox runner internal error: {run_err}", exc_info=True)
        stderr_str += f"\nSandbox internal runner error: {str(run_err)}"
        
    finally:
        # We do not delete the persistent conversation directory so that files and command state
        # carry over to subsequent turns. We only clean up the temporary script files.
        for temp_script in ("script.py", "script.js", "command.sh"):
            try:
                os.remove(os.path.join(src_dir, temp_script))
            except OSError:
                pass

    full_output = stdout_str
    if stderr_str:
        full_output += f"\n\n--- Standard Error ---\n{stderr_str}"

    if mounted_files:
        files_list = ", ".join(mounted_files)
        full_output = f"[Mounted conversation files: {files_list}]\n\n" + full_output
        
    return full_output, generated_files

