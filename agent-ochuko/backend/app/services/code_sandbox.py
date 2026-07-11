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

async def _stream_process_output(proc: asyncio.subprocess.Process):
    """
    Reads stdout and stderr concurrently, yielding (stream_name, line) tuples
    as they arrive. Replaces the blocking proc.communicate() call.
    """
    async def _read_stream(stream, name):
        while True:
            line = await stream.readline()
            if not line:
                break
            yield (name, line.decode("utf-8", errors="replace").rstrip("\n"))

    stdout_gen = _read_stream(proc.stdout, "stdout")
    stderr_gen = _read_stream(proc.stderr, "stderr")

    async def _drain(gen, queue):
        async for item in gen:
            await queue.put(item)
        await queue.put(None)  # sentinel

    queue: asyncio.Queue = asyncio.Queue()
    t1 = asyncio.create_task(_drain(stdout_gen, queue))
    t2 = asyncio.create_task(_drain(stderr_gen, queue))

    done_count = 0
    while done_count < 2:
        item = await queue.get()
        if item is None:
            done_count += 1
            continue
        yield item

    await asyncio.gather(t1, t2)
    await proc.wait()

# Define global persistent library paths
GLOBAL_LIBS_DIR = "/app/sandbox_libs"
PYTHON_LIBS_DIR = os.path.join(GLOBAL_LIBS_DIR, "python_packages")
NODE_LIBS_DIR = os.path.join(GLOBAL_LIBS_DIR, "node_modules")

# Ensure persistent directories exist
os.makedirs(PYTHON_LIBS_DIR, exist_ok=True)
os.makedirs(NODE_LIBS_DIR, exist_ok=True)

async def execute_code_in_sandbox(
    code: str,
    language: str,
    conversation_id: str,
    user_id: str = "00000000-0000-0000-0000-000000000000",
    timeout_seconds: int = 45
):
    """
    Executes Python or JavaScript code inside a secure local sandbox.
    Captures stdout, stderr, and uploads any generated files to R2 storage.
    Automatically catches missing module errors and installs/caches them.
    Now an async generator that yields streaming events.
    """
    language = language.lower().strip()
    
    # 1. Create a dedicated working directory for this execution
    # Use conversation_id directly to persist file state across multiple turns
    work_dir = os.path.abspath(os.path.join("/tmp", f"sandbox_{conversation_id}")).replace("\\", "/")
    os.makedirs(work_dir, exist_ok=True)

    # Record modification times of existing files before execution
    before_files = {}
    for root, dirs, files_in_dir in os.walk(work_dir):
        if any(ignored in root for ignored in (".git", "node_modules", ".venv", "__pycache__")):
            continue
        for file in files_in_dir:
            path = os.path.join(root, file)
            try:
                before_files[path] = os.path.getmtime(path)
            except OSError:
                pass
    
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
            script_path = os.path.join(work_dir, "command.sh")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            bash_executable = _find_bash_executable()
            proc = await asyncio.create_subprocess_exec(
                bash_executable, "command.sh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=work_dir
            )
            stdout_lines, stderr_lines = [], []
            try:
                async for stream_name, line in asyncio.wait_for(_stream_process_output(proc), timeout=timeout_seconds):
                    if stream_name == "stdout":
                        stdout_lines.append(line)
                    else:
                        stderr_lines.append(line)
                    yield {"type": "sandbox_line", "stream": stream_name, "line": line}
            except asyncio.TimeoutError:
                proc.kill()
                yield {"type": "sandbox_line", "stream": "stderr", "line": "Execution Timeout (exceeded 45s limit)"}
                stdout_str = "\n".join(stdout_lines)
                stderr_str = "\n".join(stderr_lines) + "\nExecution Timeout (exceeded 45s limit)"
                yield {"type": "sandbox_result", "stdout": stdout_str, "files": []}
                return

            stdout_str = "\n".join(stdout_lines)
            stderr_str = "\n".join(stderr_lines)

        elif language == "javascript" or language == "js" or language == "node":
            # JS execution path
            script_path = os.path.join(work_dir, "script.js")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            for attempt in range(3):
                proc = await asyncio.create_subprocess_exec(
                    "node", script_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=work_dir
                )
                stdout_lines, stderr_lines = [], []
                try:
                    async for stream_name, line in asyncio.wait_for(_stream_process_output(proc), timeout=timeout_seconds):
                        if stream_name == "stdout":
                            stdout_lines.append(line)
                        else:
                            stderr_lines.append(line)
                        yield {"type": "sandbox_line", "stream": stream_name, "line": line}
                except asyncio.TimeoutError:
                    proc.kill()
                    yield {"type": "sandbox_line", "stream": "stderr", "line": "Execution Timeout (exceeded 45s limit)"}
                    stdout_str = "\n".join(stdout_lines)
                    stderr_str = "\n".join(stderr_lines) + "\nExecution Timeout (exceeded 45s limit)"
                    yield {"type": "sandbox_result", "stdout": stdout_str, "files": []}
                    return

                stdout_str = "\n".join(stdout_lines)
                stderr_str = "\n".join(stderr_lines)

                if proc.returncode == 0:
                    break

                # Auto-install missing node packages if possible
                if "Cannot find module" in stderr_str:
                    m = re.search(r"Cannot find module ['\"](.*?)['\"]", stderr_str)
                    if m:
                        missing_pkg = m.group(1)
                        # Avoid trying to install relative paths/local imports
                        if not missing_pkg.startswith((".", "/")):
                            logger.info(f"Auto-installing JS package: {missing_pkg}")
                            install_proc = await asyncio.create_subprocess_exec(
                                "npm", "install", "--prefix", GLOBAL_LIBS_DIR, missing_pkg,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )
                            await install_proc.communicate()
                            continue
                break
        else:
            # Python execution path
            script_path = os.path.join(work_dir, "script.py")
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(code)

            for attempt in range(3):
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, script_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=work_dir
                )
                stdout_lines, stderr_lines = [], []
                try:
                    async for stream_name, line in asyncio.wait_for(_stream_process_output(proc), timeout=timeout_seconds):
                        if stream_name == "stdout":
                            stdout_lines.append(line)
                        else:
                            stderr_lines.append(line)
                        yield {"type": "sandbox_line", "stream": stream_name, "line": line}
                except asyncio.TimeoutError:
                    proc.kill()
                    yield {"type": "sandbox_line", "stream": "stderr", "line": "Execution Timeout (exceeded 45s limit)"}
                    stdout_str = "\n".join(stdout_lines)
                    stderr_str = "\n".join(stderr_lines) + "\nExecution Timeout (exceeded 45s limit)"
                    yield {"type": "sandbox_result", "stdout": stdout_str, "files": []}
                    return

                stdout_str = "\n".join(stdout_lines)
                stderr_str = "\n".join(stderr_lines)

                if proc.returncode == 0:
                    break

                # Auto-install missing Python packages if possible
                if "ModuleNotFoundError" in stderr_str:
                    m = re.search(r"No module named ['\"](.*?)['\"]", stderr_str)
                    if m:
                        missing_pkg = m.group(1)
                        # Map common module imports to their actual PyPI package names
                        pkg_map = {"yaml": "pyyaml", "PIL": "Pillow", "docx": "python-docx"}
                        install_name = pkg_map.get(missing_pkg, missing_pkg)

                        logger.info(f"Auto-installing Python package: {install_name}")
                        install_proc = await asyncio.create_subprocess_exec(
                            sys.executable, "-m", "pip", "install", "--target", PYTHON_LIBS_DIR, install_name,
                            stdout=asyncio.subprocess.PIPE,
                            stderr=asyncio.subprocess.PIPE
                        )
                        await install_proc.communicate()
                        continue
                break

        # 2. Upload any created/generated files in the working directory to R2
        from app.api.v1.endpoints.chat import _upload_generated_file
        from app.services.supabase_admin import get_supabase_admin
        
        # Get active user_id context from thread if possible (fallback to system/default)
        user_id = "00000000-0000-0000-0000-000000000000"
        
        for root, dirs, files_in_dir in os.walk(work_dir):
            # Skip scanning dependency and version control directories
            if any(ignored in root for ignored in (".git", "node_modules", ".venv", "__pycache__")):
                continue
            
            # Skip files from cloned git repos (check for .git in parent dirs)
            is_external_repo = False
            check_path = root
            while check_path != work_dir:
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
                            
                        # Auto-resolve MIME type via guess_type
                        import mimetypes
                        mime, _ = mimetypes.guess_type(file)
                        if not mime:
                            mime = "application/octet-stream"
                            
                        r2_url = await _upload_generated_file(
                            file_bytes=file_bytes,
                            filename=file,
                            mime_type=mime,
                            conversation_id=conversation_id,
                            user_id=user_id
                        )
                        generated_files.append({
                            "filename": file,
                            "download_url": r2_url,
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
                for root, dirs, files_in_dir in os.walk(work_dir):
                    dirs[:] = [d for d in dirs if d not in (".git", "node_modules", ".venv", "__pycache__")]
                    for file in files_in_dir:
                        if file in ("script.py", "script.js", "command.sh"):
                            continue
                        file_path = os.path.join(root, file)
                        # arcname is relative to work_dir so the zip has a clean flat/nested structure
                        arcname = os.path.relpath(file_path, work_dir)
                        try:
                            zf.write(file_path, arcname=arcname)
                        except OSError as ze:
                            logger.warning("ZIP: skipping %s: %s", file, ze)

            zip_bytes = zip_buf.getvalue()
            if zip_bytes:
                try:
                    zip_url = await _upload_generated_file(
                        file_bytes=zip_bytes,
                        filename="project.zip",
                        mime_type="application/zip",
                        conversation_id=conversation_id,
                        user_id=user_id,
                    )
                    generated_files.append({
                        "filename": "project.zip",
                        "download_url": zip_url,
                        "size_bytes": len(zip_bytes),
                    })
                    logger.info(
                        "sandbox ZIP: %d files, %d bytes → %s",
                        len(generated_files) - 1, len(zip_bytes), zip_url,
                    )
                except Exception as zip_err:
                    logger.warning("ZIP upload failed: %s", zip_err)
                    # Non-fatal — individual files were already uploaded successfully

    except Exception as run_err:
        logger.error(f"Sandbox runner internal error: {run_err}", exc_info=True)
        stderr_str += f"\nSandbox internal runner error: {str(run_err)}"
        
    finally:
        # We do not delete the persistent conversation directory so that files and command state
        # carry over to subsequent turns. We only clean up the temporary script files.
        for temp_script in ("script.py", "script.js", "command.sh"):
            try:
                os.remove(os.path.join(work_dir, temp_script))
            except OSError:
                pass

    full_output = stdout_str
    if stderr_str:
        full_output += f"\n\n--- Standard Error ---\n{stderr_str}"

    yield {"type": "sandbox_result", "stdout": full_output, "files": generated_files}
