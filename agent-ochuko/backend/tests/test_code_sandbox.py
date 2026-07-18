# tests/test_code_sandbox.py
import pytest
import os
import shutil
from app.services.code_sandbox import execute_code_in_sandbox

@pytest.mark.anyio
async def test_python_sandbox_math_and_print():
    import uuid
    conversation_id = f"test-convo-{uuid.uuid4()}"
    sandbox_dir = f"/tmp/sandbox_{conversation_id}"
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

@pytest.mark.anyio
async def test_python_sandbox_file_creation(monkeypatch):
    import uuid
    conversation_id = f"test-convo-{uuid.uuid4()}"
    sandbox_dir = f"/tmp/sandbox_{conversation_id}"
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

@pytest.mark.anyio
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
    # Ensure starting clean
    sandbox_dir = f"/tmp/sandbox_{conversation_id}"
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
        assert "step1.txt" not in uploaded_files  # delta upload: step1.txt was not modified, so it shouldn't be uploaded again!
        
    finally:
        # Give Windows a moment to release file handles, then clean up
        await asyncio.sleep(0.5)
        if os.path.exists(sandbox_dir):
            for retry in range(5):
                try:
                    shutil.rmtree(sandbox_dir)
                    break
                except Exception:
                    await asyncio.sleep(0.2)
