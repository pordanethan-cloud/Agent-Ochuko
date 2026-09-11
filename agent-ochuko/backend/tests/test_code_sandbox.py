# tests/test_code_sandbox.py
import pytest
import os
import shutil
import tempfile
from unittest.mock import patch, MagicMock
from app.services.code_sandbox import execute_code_in_sandbox

def get_sandbox_dir(conversation_id: str) -> str:
    return os.path.abspath(os.path.join(tempfile.gettempdir(), f"sandbox_{conversation_id}")).replace("\\", "/")

@pytest.mark.asyncio
async def test_python_sandbox_math_and_print():
    import uuid
    conversation_id = f"test-convo-{uuid.uuid4()}"
    sandbox_dir = get_sandbox_dir(conversation_id)
    if os.path.exists(sandbox_dir):
        try:
            shutil.rmtree(sandbox_dir)
        except Exception:
            pass
    code = """
a = 10
b = 20
print(f"SUM IS {a + b}")
"""
    try:
        output, files = await execute_code_in_sandbox(code, "python", conversation_id)
        assert "SUM IS 30" in output
        assert len(files) == 0
    finally:
        if os.path.exists(sandbox_dir):
            try:
                shutil.rmtree(sandbox_dir)
            except Exception:
                pass

@pytest.mark.asyncio
async def test_python_sandbox_file_creation(monkeypatch):
    import uuid
    conversation_id = f"test-convo-{uuid.uuid4()}"
    sandbox_dir = get_sandbox_dir(conversation_id)
    if os.path.exists(sandbox_dir):
        try:
            shutil.rmtree(sandbox_dir)
        except Exception:
            pass

    # Mock _upload_generated_file to return a dummy URL
    async def mock_upload(file_bytes, filename, mime_type, conversation_id, user_id):
        return f"https://mockstorage.local/{conversation_id}/{filename}"
        
    monkeypatch.setattr("app.api.v1.endpoints.chat._upload_generated_file", mock_upload)

    code = """
with open("result.txt", "w") as f:
    f.write("hello from sandbox")
"""
    try:
        output, files = await execute_code_in_sandbox(code, "python", conversation_id)
        assert len(files) == 1
        assert files[0]["filename"] == "result.txt"
        assert f"mockstorage.local/{conversation_id}/result.txt" in files[0]["download_url"]
    finally:
        if os.path.exists(sandbox_dir):
            try:
                shutil.rmtree(sandbox_dir)
            except Exception:
                pass

@pytest.mark.asyncio
async def test_bash_sandbox_persistence_and_delta(monkeypatch):
    # Mock _upload_generated_file to return a dummy URL
    uploaded_files = []
    async def mock_upload(file_bytes, filename, mime_type, conversation_id, user_id):
        uploaded_files.append(filename)
        return f"https://mockstorage.local/{conversation_id}/{filename}"
        
    monkeypatch.setattr("app.api.v1.endpoints.chat._upload_generated_file", mock_upload)
    
    import uuid
    import asyncio
    conversation_id = str(uuid.uuid4())
    sandbox_dir = get_sandbox_dir(conversation_id)
    if os.path.exists(sandbox_dir):
        try:
            shutil.rmtree(sandbox_dir)
        except Exception:
            pass
        
    try:
        # Step 1: Create a file using bash
        code1 = "echo 'initial data' > step1.txt"
        output1, files1 = await execute_code_in_sandbox(code1, "bash", conversation_id)
        assert len(files1) == 1
        assert files1[0]["filename"] == "step1.txt"
        assert "step1.txt" in uploaded_files
        
        # Reset tracker
        uploaded_files.clear()
        
        # Step 2: Run a command checking if step1.txt exists, and create step2.txt
        code2 = """
        if [ -f step1.txt ]; then
            echo "step1 exists"
            echo "more data" > step2.txt
        fi
        """
        output2, files2 = await execute_code_in_sandbox(code2, "bash", conversation_id)
        assert "step1 exists" in output2
        assert len(files2) == 1
        assert files2[0]["filename"] == "step2.txt"
        assert "step2.txt" in uploaded_files
        assert "step1.txt" not in uploaded_files
        
    finally:
        await asyncio.sleep(0.5)
        if os.path.exists(sandbox_dir):
            for retry in range(5):
                try:
                    shutil.rmtree(sandbox_dir)
                    break
                except Exception:
                    await asyncio.sleep(0.2)


@pytest.mark.asyncio
async def test_sync_conversation_sandbox_workspace_local_scan():
    """Verifies that sync_conversation_sandbox_workspace accurately discovers local files in sandbox."""
    import uuid
    from app.services.code_sandbox import sync_conversation_sandbox_workspace, sandbox_write_file, sandbox_read_file
    conv_id = f"test-sync-{uuid.uuid4()}"
    sandbox_dir = get_sandbox_dir(conv_id)

    try:
        # Write a strategy document
        write_res = await sandbox_write_file(conv_id, "strategy.md", "# Scalping Strategy\nImportant setup rules.")
        assert "strategy.md" in write_res

        # Call workspace sync
        files = await sync_conversation_sandbox_workspace(conv_id, "test-user")
        assert any(f["filename"] == "strategy.md" for f in files)

        # Read back
        read_res = await sandbox_read_file(conv_id, "strategy.md")
        assert "Scalping Strategy" in read_res
    finally:
        if os.path.exists(sandbox_dir):
            try:
                shutil.rmtree(sandbox_dir)
            except Exception:
                pass


@pytest.mark.asyncio
async def test_sandbox_edit_and_read_lifecycle():
    """Verifies that sandbox_edit surgically updates existing files in the sandbox workspace."""
    import uuid
    from app.services.code_sandbox import sandbox_write_file, sandbox_edit_file, sandbox_read_file
    conv_id = f"test-edit-{uuid.uuid4()}"
    sandbox_dir = get_sandbox_dir(conv_id)

    try:
        await sandbox_write_file(conv_id, "manual range-scalping strategy.md", "# Manual Range Scalping\n\nRule 1: Enter on bounce.")
        edit_res = await sandbox_edit_file(
            conv_id,
            "manual range-scalping strategy.md",
            "# Manual Range Scalping",
            "**5-Line Summary: Scalp on key levels.**\n\n# Manual Range Scalping"
        )
        assert "EDITED manual range-scalping strategy.md" in edit_res

        content = await sandbox_read_file(conv_id, "manual range-scalping strategy.md")
        assert "5-Line Summary: Scalp on key levels." in content
        assert "Rule 1: Enter on bounce." in content
    finally:
        if os.path.exists(sandbox_dir):
            try:
                shutil.rmtree(sandbox_dir)
            except Exception:
                pass


@pytest.mark.asyncio
async def test_hosted_sites_r2_recovery_fallback():
    """Verifies that get_site and get_site_file recover from memory loss using R2 mock fallback."""
    from unittest.mock import MagicMock
    from app.services.hosted_sites_service import HostedSitesService, _MEMORY_HOSTED_SITES
    import json

    slug = "test-recovery-site-999"
    # Ensure memory is clear for this slug
    _MEMORY_HOSTED_SITES.pop(slug, None)

    site_record = {
        "id": "site-uuid-999",
        "slug": slug,
        "title": "Recovered Site",
        "html_content": "<h1>Persistent Content</h1>",
        "files": {"index.html": "<h1>Persistent Content</h1>", "style.css": "body { color: gold; }"},
        "is_public": True,
        "view_count": 0,
    }

    # Mock R2 client
    mock_s3 = MagicMock()
    mock_s3.get_object.return_value = {
        "Body": MagicMock(read=lambda: json.dumps(site_record).encode("utf-8"))
    }

    with patch("app.services.cloudflare_r2.get_r2_client", return_value=(mock_s3, "test-bucket", "https://pub.mock.r2.dev")):
        recovered = await HostedSitesService.get_site(slug, supabase_client=None)
        assert recovered is not None
        assert recovered["title"] == "Recovered Site"
        assert slug in _MEMORY_HOSTED_SITES

        # Test file retrieval from recovered site
        file_res = await HostedSitesService.get_site_file(slug, "style.css", supabase_client=None)
        assert file_res is not None
        assert "color: gold" in file_res["content"]


