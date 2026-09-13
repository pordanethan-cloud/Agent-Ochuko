# tests/test_workstation_books_alias.py
"""Regression tests: 'books folder in documents' / 'documents/BOOKS' must resolve to ~/Documents/BOOKS."""
import os
import tempfile
import pytest
from app.connectors.workstation_mcp import WorkstationMCP

HOST_BOOKS = os.path.join(os.path.expanduser("~"), "Documents", "BOOKS")


@pytest.mark.skipif(not os.path.isdir(HOST_BOOKS), reason="host ~/Documents/BOOKS not present")
@pytest.mark.asyncio
async def test_books_natural_phrase_resolves_to_host():
    with tempfile.TemporaryDirectory() as ws:
        # Poison the workspace with a same-named relative dir: alias must still win for NL phrases
        os.makedirs(os.path.join(ws, "documents", "books"), exist_ok=True)
        mcp = WorkstationMCP(workspace_root=ws)
        assert os.path.normcase(mcp._resolve_safe_path("books folder in documents")) == os.path.normcase(
            HOST_BOOKS
        )


@pytest.mark.skipif(not os.path.isdir(HOST_BOOKS), reason="host ~/Documents/BOOKS not present")
@pytest.mark.asyncio
async def test_documents_slash_alias_resolves_to_host():
    with tempfile.TemporaryDirectory() as ws:
        os.makedirs(os.path.join(ws, "documents", "BOOKS"), exist_ok=True)
        mcp = WorkstationMCP(workspace_root=ws)
        # HOST wins when no exact workspace file exists
        assert os.path.normcase(mcp._resolve_safe_path("documents/BOOKS")) == os.path.normcase(HOST_BOOKS)
        # Exact workspace file wins (agent's own file takes precedence)
        ws_file = os.path.join(ws, "documents", "BOOKS", "local.txt")
        with open(ws_file, "w") as f:
            f.write("local")
        assert os.path.normcase(mcp._resolve_safe_path("documents/BOOKS/local.txt")) == os.path.normcase(ws_file)


@pytest.mark.skipif(not os.path.isdir(HOST_BOOKS), reason="host ~/Documents/BOOKS not present")
@pytest.mark.asyncio
async def test_books_listing_reads_host_folder():
    with tempfile.TemporaryDirectory() as ws:
        mcp = WorkstationMCP(workspace_root=ws)
        listing = await mcp.list_directory(path="books folder in documents")
        # list_directory returns entries without echoing the resolved path;
        # verify by resolved path + recognizable content instead.
        assert mcp._resolve_safe_path("books folder in documents") == HOST_BOOKS or os.path.normcase(
            mcp._resolve_safe_path("books folder in documents")
        ) == os.path.normcase(HOST_BOOKS)
        assert "MY_READING_PLAN" in listing or ".pdf" in listing
        read = await mcp.read_file(path="documents/BOOKS/MY_READING_PLAN.md", length=500)
        assert "Reading Roadmap" in read
