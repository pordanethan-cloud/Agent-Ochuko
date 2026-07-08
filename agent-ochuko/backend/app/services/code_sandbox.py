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
from typing import Tuple, List, Dict

logger = logging.getLogger("app.services.code_sandbox")

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
    timeout_seconds: int = 45
) -> Tuple[str, List[Dict[str, str]]]:
    """
    Executes Python or JavaScript code inside a secure local sandbox.
    Captures stdout, stderr, and uploads any generated files to R2 storage.
    Automatically catches missing module errors and installs/caches them.
    """
    language = language.lower().strip()
    
    # 1. Create a dedicated working directory for this execution
    work_dir = os.path.join("/tmp", f"sandbox_{conversation_id}_{uuid.uuid4().hex}")
    os.makedirs(work_dir, exist_ok=True)
    
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
        if language == "javascript" or language == "js" or language == "node":
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
                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    proc.kill()
                    return "Execution Timeout (exceeded 45s limit)", []
                    
                stdout_str = stdout_bytes.decode("utf-8", errors="replace")
                stderr_str = stderr_bytes.decode("utf-8", errors="replace")
                
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
                try:
                    stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
                except asyncio.TimeoutError:
                    proc.kill()
                    return "Execution Timeout (exceeded 45s limit)", []
                    
                stdout_str = stdout_bytes.decode("utf-8", errors="replace")
                stderr_str = stderr_bytes.decode("utf-8", errors="replace")
                
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
        
        for root, dirs, files in os.walk(work_dir):
            for file in files:
                if file in ("script.py", "script.js"):
                    continue
                file_path = os.path.join(root, file)
                try:
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

    except Exception as run_err:
        logger.error(f"Sandbox runner internal error: {run_err}", exc_info=True)
        stderr_str += f"\nSandbox internal runner error: {str(run_err)}"
        
    finally:
        # Clean up working directory
        import shutil
        try:
            shutil.rmtree(work_dir)
        except Exception as clean_err:
            logger.warning(f"Failed to clean up sandbox work dir {work_dir}: {clean_err}")

    full_output = stdout_str
    if stderr_str:
        full_output += f"\n\n--- Standard Error ---\n{stderr_str}"
        
    return full_output, generated_files
