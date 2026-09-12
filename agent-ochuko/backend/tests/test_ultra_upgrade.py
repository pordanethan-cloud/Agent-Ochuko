"""Tests for the Ochuko Ultra upgrade: budgets, sandbox navigation, isolation."""
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.agent_config import get_max_output_tokens, _OUTPUT_TOKEN_BUDGETS
from app.core.skills import BASE_IDENTITY, ULTRA_IDENTITY, AGENT_CONDUCT, SKILLS


# ── Repo-style multi-file website uploads ────────────────────────────────────

def test_upload_relpath_preserves_project_structure():
    """Nested project files must keep their relative paths (repo-style keys)."""
    import tempfile
    data_dir = os.path.join(tempfile.gettempdir(), "relpath_test_conv", "data")
    nested = os.path.join(data_dir, "css", "styles.css")
    rel = os.path.relpath(nested, data_dir).replace("\\", "/")
    assert rel == "css/styles.css"

    deep = os.path.join(data_dir, "assets", "img", "hero.png")
    rel2 = os.path.relpath(deep, data_dir).replace("\\", "/")
    assert rel2 == "assets/img/hero.png"


def test_r2_public_url_encoding_keeps_slashes():
    """R2 URLs must encode path segments but keep / so relative links work."""
    from app.services.cloudflare_r2 import build_r2_public_url

    url = build_r2_public_url("https://pub-example.r2.dev/", "generated/conv1/css/styles.css")
    assert url == "https://pub-example.r2.dev/generated/conv1/css/styles.css"

    # Spaces / unicode in segment names are encoded, slashes intact
    url2 = build_r2_public_url("https://pub-example.r2.dev", "generated/conv1/my page/index.html")
    assert url2 == "https://pub-example.r2.dev/generated/conv1/my%20page/index.html"

    url3 = build_r2_public_url("https://pub-example.r2.dev", "generated/conv1/über/hero.svg")
    assert url3 == "https://pub-example.r2.dev/generated/conv1/%C3%BCber/hero.svg"


def test_website_project_contract_in_code_skill():
    """The code skill must mandate repo-style multi-file websites."""
    code_skill = SKILLS["code"]
    assert "WEBSITE PROJECT CONTRACT" in code_skill
    assert "index.html" in code_skill
    assert "css/styles.css" in code_skill
    assert "js/main.js" in code_skill
    assert "README.md" in code_skill
    assert "RELATIVE" in code_skill  # relative links contract
    assert "360px" in code_skill and "768px" in code_skill and "1280px" in code_skill


@pytest.fixture
def _config_cache():
    from app.core.config import _CONFIG_CACHE
    saved = dict(_CONFIG_CACHE)
    # Force in-memory defaults so tests are hermetic (no Azure App Config calls)
    _CONFIG_CACHE.clear()
    _CONFIG_CACHE["__use_defaults__"] = "1"
    yield _CONFIG_CACHE
    _CONFIG_CACHE.clear()
    _CONFIG_CACHE.update(saved)


@pytest.mark.asyncio
async def test_ultra_budget_is_enterprise_grade(_config_cache):
    _config_cache["MAX_OUTPUT_TOKENS_ULTRA"] = "32768"
    assert await get_max_output_tokens("ultra") == 32768
    # Phase 5: agent mode has its own dedicated MAX_OUTPUT_TOKENS_AGENT key
    _config_cache["MAX_OUTPUT_TOKENS_AGENT"] = "32768"
    assert await get_max_output_tokens("agent") == 32768


@pytest.mark.asyncio
async def test_mode_budget_mapping(_config_cache):
    _config_cache["MAX_OUTPUT_TOKENS_THINK"] = "32768"
    _config_cache["MAX_OUTPUT_TOKENS_SOLVE"] = "16384"
    _config_cache["MAX_OUTPUT_TOKENS_DISCUSS"] = "4096"
    assert await get_max_output_tokens("think") == 32768
    assert await get_max_output_tokens("solve") == 16384
    assert await get_max_output_tokens("discuss") == 4096


@pytest.mark.asyncio
async def test_budget_floor_and_garbage_tolerance(_config_cache):
    _config_cache["MAX_OUTPUT_TOKENS_SOLVE"] = "not-a-number"
    assert await get_max_output_tokens("solve") == 16384
    _config_cache["MAX_OUTPUT_TOKENS_SOLVE"] = "10"
    assert await get_max_output_tokens("solve") >= 1024  # floor


def test_ultra_identity_present_and_capped():
    words = len(ULTRA_IDENTITY.split())
    assert words > 20, "ULTRA_IDENTITY missing or empty"
    assert int(words * 1.3) <= 250, f"ULTRA_IDENTITY bloat: ~{int(words * 1.3)} est tokens"
    assert "Ochuko Ultra" in ULTRA_IDENTITY


def test_task_approach_is_general_identity_is_not():
    # The behavioral approach applies to EVERY mode via get_skill_prompt...
    from app.core.skills import get_skill_prompt
    prompt = get_skill_prompt("Explain quantum computing in detail.")
    assert "APPROACH TO TASKS" in prompt
    assert "never stubs, never truncated" in prompt
    # ...but the Ultra identity tokens stay exclusive to agent mode.
    assert "Ochuko Ultra" not in prompt
    assert "deep-autonomy tier" not in prompt


def test_file_creation_contract_in_code_skill():
    code_skill = SKILLS.get("code", "")
    assert "FILE CREATION CONTRACT" in code_skill
    assert "sandbox_ls" in code_skill and "sandbox_write" in code_skill


def test_base_identity_still_capped():
    # Phase 5: cap relaxed 500 → 600 to carry the enterprise-grade conduct contracts.
    assert int(len(BASE_IDENTITY.split()) * 1.3) <= 600


# ── Sandbox navigation helpers ────────────────────────────────────────────────

@pytest.fixture
def temp_convo(tmp_path, monkeypatch):
    """Redirect the sandbox root into a pytest tmp dir."""
    import app.services.code_sandbox as cs
    monkeypatch.setattr(cs.tempfile, "gettempdir", lambda: str(tmp_path))
    return "test-conversation-id"


@pytest.mark.asyncio
async def test_sandbox_write_read_roundtrip(temp_convo):
    from app.services.code_sandbox import sandbox_write_file, sandbox_read_file

    body = "print('hello')\n" * 50  # 750 bytes
    receipt = await sandbox_write_file(temp_convo, "app/main.py", body)
    assert receipt.startswith("WROTE app/main.py")
    assert "750 bytes" in receipt

    content = await sandbox_read_file(temp_convo, "app/main.py")
    assert "print('hello')" in content
    assert "750 bytes total" in content


@pytest.mark.asyncio
async def test_sandbox_read_offset_pagination(temp_convo):
    from app.services.code_sandbox import sandbox_write_file, sandbox_read_file

    body = "x" * 10000
    await sandbox_write_file(temp_convo, "big.txt", body)
    page1 = await sandbox_read_file(temp_convo, "big.txt", offset=0, max_bytes=4000)
    assert "4000" in page1 and "more bytes" in page1
    page2 = await sandbox_read_file(temp_convo, "big.txt", offset=4000, max_bytes=4000)
    assert "showing bytes 4000" in page2


@pytest.mark.asyncio
async def test_sandbox_traversal_blocked(temp_convo):
    from app.services.code_sandbox import sandbox_list_files

    with pytest.raises(ValueError):
        await sandbox_list_files(temp_convo, "../../../etc")
    with pytest.raises(ValueError):
        from app.services.code_sandbox import sandbox_write_file
        await sandbox_write_file(temp_convo, "..\\escape.txt", "nope")


@pytest.mark.asyncio
async def test_sandbox_ls_lists_tree(temp_convo):
    from app.services.code_sandbox import sandbox_write_file, sandbox_list_files

    await sandbox_write_file(temp_convo, "a.txt", "A")
    await sandbox_write_file(temp_convo, "src/deep/b.py", "B")
    listing = await sandbox_list_files(temp_convo)
    assert "a.txt" in listing and "src/deep/b.py" in listing
    assert "(1 bytes)" in listing


@pytest.mark.asyncio
async def test_sandbox_ls_ignores_noise_dirs(temp_convo):
    from app.services.code_sandbox import sandbox_write_file, sandbox_list_files, _resolve_sandbox_path

    await sandbox_write_file(temp_convo, "keep.txt", "K")
    noise = os.path.join(_resolve_sandbox_path(temp_convo), "node_modules")
    os.makedirs(noise, exist_ok=True)
    with open(os.path.join(noise, "pkg.js"), "w") as f:
        f.write("junk")
    listing = await sandbox_list_files(temp_convo)
    assert "keep.txt" in listing
    assert "pkg.js" not in listing


# ── Stdout capping (artifact isolation) ───────────────────────────────────────

def test_stdout_cap_logic():
    # Mirror of the inline cap in chat.py execute_code handler.
    exec_output = "line\n" * 5000  # ~30k chars
    _HEAD, _TAIL = 4000, 1000
    assert len(exec_output) > _HEAD + _TAIL + 64
    capped = exec_output[:_HEAD] + f"\n[... {len(exec_output) - _HEAD - _TAIL} chars truncated ...]\n" + exec_output[-_TAIL:]
    assert len(capped) < _HEAD + _TAIL + 200
    small = "short output"
    assert len(small) <= _HEAD + _TAIL + 64  # passes through uncapped
