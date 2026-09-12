"""
tests/test_delivery_gates.py
────────────────────────────
Delivery-integrity gates added after the "Problems encountered today" review:

1. Gate 1 — THINK-mode tool roster hygiene: no phantom tools advertised to the
   model; unregistered tool calls get explicit re-plan feedback.
2. Gate 2 — verify-after-write: verify_written_file + verify_relative_links.
3. Gates 3+4 — prompt-layer delivery evidence + scope disclosure contracts.
4. Gate 5 — hosted-site deploy preview health-check (bundle integrity +
   preview_verified read-back).
"""
import os
import sys
import pytest
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.verification_gates import VerificationGates
from app.core.skills import SKILLS
from app.services.hosted_sites_service import HostedSitesService

_CHAT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "app", "api", "v1", "endpoints", "chat.py",
)


def _read_chat_code() -> str:
    with open(_CHAT_PATH, "r", encoding="utf-8") as f:
        return f.read()


# ── Gate 2: verify_written_file ───────────────────────────────────────────────

def test_verify_written_file_passes_for_real_nonempty_file(tmp_path):
    target = tmp_path / "index.html"
    target.write_text("<h1>hello</h1>", encoding="utf-8")
    ok, err = VerificationGates.verify_written_file(str(target))
    assert ok is True and err is None


def test_verify_written_file_fails_for_missing_file(tmp_path):
    ok, err = VerificationGates.verify_written_file(str(tmp_path / "ghost.html"))
    assert ok is False and "does not exist" in err


def test_verify_written_file_fails_for_empty_file(tmp_path):
    target = tmp_path / "empty.html"
    target.write_text("", encoding="utf-8")
    ok, err = VerificationGates.verify_written_file(str(target))
    assert ok is False and "empty" in err


# ── Gate 2: verify_relative_links ─────────────────────────────────────────────

def _write_site(root, with_css: bool = True):
    (root / "index.html").write_text(
        '<html><head><link rel="stylesheet" href="./css/styles.css">'
        '<script src="https://cdn.tailwindcss.com"></script>'
        '<a href="#top">Top</a><a href="https://example.com">Ext</a></head>'
        '<body id="top"><script src="./js/main.js"></script></body></html>',
        encoding="utf-8",
    )
    (root / "js").mkdir(exist_ok=True)
    (root / "js" / "main.js").write_text("console.log('x');", encoding="utf-8")
    if with_css:
        (root / "css").mkdir(exist_ok=True)
        (root / "css" / "styles.css").write_text("body { margin: 0; }", encoding="utf-8")


def test_verify_relative_links_passes_when_all_targets_exist(tmp_path):
    _write_site(tmp_path, with_css=True)
    ok, err = VerificationGates.verify_relative_links(str(tmp_path / "index.html"))
    assert ok is True and err is None


def test_verify_relative_links_fails_when_target_never_written(tmp_path):
    # The exact review failure: page written, css/styles.css write failed.
    _write_site(tmp_path, with_css=False)
    ok, err = VerificationGates.verify_relative_links(str(tmp_path / "index.html"))
    assert ok is False and "styles.css" in err


def test_verify_relative_links_ignores_external_and_anchors(tmp_path):
    (tmp_path / "solo.html").write_text(
        '<html><body><a href="#section">S</a>'
        '<img src="data:image/png;base64,AAA">'
        '<a href="mailto:x@y.z">m</a>'
        '<script src="//cdn.example.com/lib.js"></script></body></html>',
        encoding="utf-8",
    )
    ok, err = VerificationGates.verify_relative_links(str(tmp_path / "solo.html"))
    assert ok is True and err is None


def test_verify_relative_links_fails_for_missing_file(tmp_path):
    ok, err = VerificationGates.verify_relative_links(str(tmp_path / "missing.html"))
    assert ok is False


# ── Gate 5: hosted-site preview health-check ──────────────────────────────────

@pytest.mark.asyncio
async def test_deploy_site_reports_preview_verified():
    files = {
        "index.html": '<html><head><link rel="stylesheet" href="./css/theme.css"></head>'
                      "<body><h1>Hi</h1></body></html>",
        "css/theme.css": "h1 { color: teal; }",
    }
    with patch(
        "app.services.hosted_sites_service._mirror_files_to_r2",
        new=AsyncMock(return_value={}),
    ):
        result = await HostedSitesService.deploy_site(
            title="Gate5 Verified Site", html_content="", files=files
        )
    assert result["preview_verified"] is True
    assert result["integrity_warnings"] == []


@pytest.mark.asyncio
async def test_deploy_site_flags_unbundled_link_targets():
    files = {
        "index.html": '<html><head><link rel="stylesheet" href="./css/missing.css">'
                      '<a href="strategy.html">Strategy</a></head><body></body></html>',
    }
    with patch(
        "app.services.hosted_sites_service._mirror_files_to_r2",
        new=AsyncMock(return_value={}),
    ):
        result = await HostedSitesService.deploy_site(
            title="Gate5 Broken Links", html_content="", files=files
        )
    assert result["preview_verified"] is True  # entry serves; warnings inform the caller
    joined = " | ".join(result["integrity_warnings"])
    assert "css/missing.css" in joined
    assert "strategy.html" in joined


@pytest.mark.asyncio
async def test_deploy_site_warns_on_empty_entry():
    # An explicitly empty index.html in the file map must surface a warning
    # (bundle_html would otherwise wrap empty html_content in a shell).
    files = {"index.html": "   "}
    with patch(
        "app.services.hosted_sites_service._mirror_files_to_r2",
        new=AsyncMock(return_value={}),
    ):
        result = await HostedSitesService.deploy_site(
            title="Gate5 Blank Entry", html_content="", files=files
        )
    assert any("empty" in w.lower() for w in result["integrity_warnings"])
    assert result["preview_verified"] is False


# ── Gates 3+4: prompt-layer contracts ─────────────────────────────────────────

def test_code_skill_carries_delivery_evidence_contract():
    code_skill = SKILLS.get("code", "")
    assert "DELIVERY EVIDENCE CONTRACT" in code_skill
    assert "[Verification] OK" in code_skill
    assert "preview_verified" in code_skill


def test_code_skill_carries_scope_change_disclosure():
    code_skill = SKILLS.get("code", "")
    assert "SCOPE CHANGE DISCLOSURE" in code_skill
    assert "FIRST line" in code_skill


# ── Gate 1: THINK-mode roster hygiene (static checks) ─────────────────────────

def test_think_mode_rule_no_longer_advertises_phantom_deploy_site():
    chat_code = _read_chat_code()
    rule_line = next(
        line for line in chat_code.splitlines()
        if "If creating or modifying files or projects" in line
    )
    assert "Never reference `deploy_site`" in rule_line
    assert "`sandbox_write`" in rule_line


def test_unknown_tool_branch_gives_replan_feedback():
    chat_code = _read_chat_code()
    assert "NOT available in this environment and was NOT executed" in chat_code
    assert "state the blocker plainly instead of claiming completion" in chat_code
    # Old bare message must be gone.
    assert 'tool_outputs.append(f"Unknown tool name: {t_name}")' not in chat_code

