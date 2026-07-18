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
GLOBAL_LIBS_DIR = "/app/sandbox_libs"
PYTHON_LIBS_DIR = os.path.join(GLOBAL_LIBS_DIR, "python_packages")
NODE_LIBS_DIR = os.path.join(GLOBAL_LIBS_DIR, "node_modules")

# Ensure persistent directories exist
os.makedirs(PYTHON_LIBS_DIR, exist_ok=True)
os.makedirs(NODE_LIBS_DIR, exist_ok=True)


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
    work_dir = os.path.abspath(os.path.join("/tmp", f"sandbox_{conversation_id}")).replace("\\", "/")
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
            # Normalize /mnt/data and /workspace paths to relative data directory (../data/)
            # Use case-insensitive regex substitution to robustly handle capitalization variations
            normalized_code = re.sub(r'(?i)/mnt/data/?', '../data/', code)
            normalized_code = re.sub(r'(?i)/workspace/?', '../data/', normalized_code)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(normalized_code)
                
            bash_executable = _find_bash_executable()
            proc = await asyncio.create_subprocess_exec(
                bash_executable, "command.sh",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=src_dir
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout_seconds)
            except asyncio.TimeoutError:
                proc.kill()
                return "Execution Timeout (exceeded 45s limit)", []
                
            stdout_str = stdout_bytes.decode("utf-8", errors="replace")
            stderr_str = stderr_bytes.decode("utf-8", errors="replace")

        elif language == "javascript" or language == "js" or language == "node":
            # JS execution path
            script_path = os.path.join(src_dir, "script.js")
            # Normalize /mnt/data and /workspace paths to relative data directory (../data/)
            # Use case-insensitive regex substitution to robustly handle capitalization variations
            normalized_code = re.sub(r'(?i)/mnt/data/?', '../data/', code)
            normalized_code = re.sub(r'(?i)/workspace/?', '../data/', normalized_code)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(normalized_code)
                
            for attempt in range(3):
                proc = await asyncio.create_subprocess_exec(
                    "node", script_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=src_dir
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
            script_path = os.path.join(src_dir, "script.py")
            # Normalize /mnt/data and /workspace paths to relative data directory (../data/)
            # Use case-insensitive regex substitution to robustly handle capitalization variations
            normalized_code = re.sub(r'(?i)/mnt/data/?', '../data/', code)
            normalized_code = re.sub(r'(?i)/workspace/?', '../data/', normalized_code)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(normalized_code)
                
            for attempt in range(3):
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, script_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env,
                    cwd=src_dir
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
        from app.services.google_drive import upload_to_google_drive
        
        # Sync generated files to Google Drive first
        try:
            google_uploaded = await upload_to_google_drive(user_id, conversation_id, data_dir)
        except Exception as gd_err:
            logger.error(f"Failed to sync generated files to Google Drive: {gd_err}")
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
                            
                        # Auto-resolve MIME type via guess_type
                        import mimetypes
                        mime, _ = mimetypes.guess_type(file)
                        if not mime:
                            mime = "application/octet-stream"
                            
                        # Upload to R2 for fast preview CDN
                        r2_url = await _upload_generated_file(
                            file_bytes=file_bytes,
                            filename=file,
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
                            "filename": file,
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

