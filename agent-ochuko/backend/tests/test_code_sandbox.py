# tests/test_code_sandbox.py
import pytest
import os
import shutil
from app.services.code_sandbox import execute_code_in_sandbox

@pytest.mark.anyio
async def test_python_sandbox_math_and_print():
    code = """
a = 10
b = 20
print(f"SUM IS {a + b}")
"""
    output, files = await execute_code_in_sandbox(code, "python", "test-convo-id")
    assert "SUM IS 30" in output
    assert len(files) == 0

@pytest.mark.anyio
async def test_python_sandbox_file_creation(monkeypatch):
    # Mock _upload_generated_file to return a dummy URL
    async def mock_upload(file_bytes, filename, mime_type, conversation_id, user_id):
        return f"https://mockstorage.local/{conversation_id}/{filename}"
        
    monkeypatch.setattr("app.api.v1.endpoints.chat._upload_generated_file", mock_upload)

    code = """
with open("result.txt", "w") as f:
    f.write("hello from sandbox")
"""
    output, files = await execute_code_in_sandbox(code, "python", "test-convo-id")
    assert len(files) == 1
    assert files[0]["filename"] == "result.txt"
    assert "mockstorage.local/test-convo-id/result.txt" in files[0]["download_url"]
