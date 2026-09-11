"""
Hermetic test suite for Phase 5 upgrade — Web Design, Conduct, and Website Engine.
Mirrors conventions from test_ultra_upgrade.py:
- _config_cache fixture for hermetic App Config isolation
- pytest tmp_path fixture for sandbox isolation
- Stdlib / pure function tests for deterministic response guards and conduct machinery
"""

import json
import os
import sys
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.agent_config import (
    get_max_output_tokens,
    get_max_iterations,
    get_agent_mode_config,
    get_terminal_timeout,
)
from app.core.response_guards import (
    strip_engagement_hooks,
    enforce_prose_discipline,
    apply_profanity_ceiling,
    neutralize_unsolicited_diagnosis,
    apply_response_guards,
    is_decline,
)
from app.core.wellbeing import (
    classify_distress,
    filter_substitution_techniques,
    HELPLINE_REGISTRY,
    CRISIS_SYSTEM_CONTEXT,
)
from app.core.copyright_guard import CopyrightGuard, Violation
from app.core.entity_novelty import (
    find_unknown_entities,
    build_known_lexicon,
    should_force_grounding,
)
from app.core.abuse_policy import (
    detect_abuse,
    evaluate as evaluate_abuse,
    is_conversation_ended,
    STATE_NONE,
    STATE_WARNED,
    STATE_ENDED,
)
from app.core.verification_gates import VerificationGates
from app.services.sandbox_net_guard import parse_allowlist, host_allowed
from app.services.hosted_sites_service import normalize_file_map, guess_content_type, HostedSitesService
from app.services.pexels_service import PexelsService
from app.services.artifact_kv import kv_get, kv_set, kv_delete, kv_list, _MAX_VALUE_BYTES
from app.core.skills import BASE_IDENTITY, ULTRA_IDENTITY


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def _config_cache():
    from app.core.config import _CONFIG_CACHE
    saved = dict(_CONFIG_CACHE)
    _CONFIG_CACHE.clear()
    _CONFIG_CACHE["__use_defaults__"] = "1"
    yield _CONFIG_CACHE
    _CONFIG_CACHE.clear()
    _CONFIG_CACHE.update(saved)


@pytest.fixture
def temp_convo(tmp_path, monkeypatch):
    """Redirect the sandbox root into a pytest tmp dir."""
    import app.services.code_sandbox as cs
    monkeypatch.setattr(cs.tempfile, "gettempdir", lambda: str(tmp_path))
    return "test-phase5-convo-id"


# ── A. Agent Budget & Runtime Settings ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_agent_output_budget_uncapped_by_default(_config_cache):
    """Phase 5 item A: AGENT mode defaults to uncapped (None) so code/sites are never truncated."""
    _config_cache["MAX_OUTPUT_TOKENS_AGENT"] = "0"
    assert await get_max_output_tokens("agent") is None

    # Sentinel values that represent uncapped
    for sentinel in ("auto", "unset", "none", "unlimited", ""):
        _config_cache["MAX_OUTPUT_TOKENS_AGENT"] = sentinel
        assert await get_max_output_tokens("agent") is None


@pytest.mark.asyncio
async def test_agent_output_budget_explicit_cap(_config_cache):
    """When an explicit cap is set in App Config, it is enforced with a 1024 floor."""
    _config_cache["MAX_OUTPUT_TOKENS_AGENT"] = "16384"
    assert await get_max_output_tokens("agent") == 16384

    # Floor at 1024
    _config_cache["MAX_OUTPUT_TOKENS_AGENT"] = "50"
    assert await get_max_output_tokens("agent") == 1024


@pytest.mark.asyncio
async def test_agent_mode_step_and_duration_defaults(_config_cache):
    """50-step plan budget default and 1800s wall-clock duration."""
    cfg = await get_agent_mode_config()
    assert cfg["max_steps"] == 50
    assert cfg["max_duration_seconds"] == 1800
    assert cfg["step_timeout_seconds"] == 90
    assert cfg["auto_approve_level"] == "high"


@pytest.mark.asyncio
async def test_agent_mode_zero_steps_means_unlimited(_config_cache):
    """Setting AGENT_MODE_MAX_STEPS='0' returns 0 (unlimited) rather than minimum floor."""
    _config_cache["AGENT_MODE_MAX_STEPS"] = "0"
    assert await get_max_iterations("agent") == 0


@pytest.mark.asyncio
async def test_terminal_timeout_defaults_to_600s(_config_cache):
    """Build-grade terminal timeout defaults to 600 seconds with a 30s floor."""
    assert await get_terminal_timeout() == 600
    _config_cache["TERMINAL_TIMEOUT_SECS"] = "1200"
    assert await get_terminal_timeout() == 1200
    _config_cache["TERMINAL_TIMEOUT_SECS"] = "10"
    assert await get_terminal_timeout() == 30  # floor


# ── B. Response Guards ────────────────────────────────────────────────────────

def test_strip_engagement_hooks_trailing_lines():
    """#5: Eliminates trailing sycophantic engagement hooks deterministically."""
    sample = (
        "Here is the configuration you requested.\n\n"
        "```json\n{\"port\": 8080}\n```\n\n"
        "Thank you for reaching out!\n"
        "Let me know if you need anything else."
    )
    cleaned = strip_engagement_hooks(sample)
    assert "Thank you for reaching out!" not in cleaned
    assert "Let me know if you need anything else." not in cleaned
    assert "Here is the configuration you requested." in cleaned
    assert "{\"port\": 8080}" in cleaned


def test_strip_engagement_hooks_preserves_content_if_all_hooks():
    """Does not empty out the message if stripping would remove everything."""
    only_hook = "Thank you for reaching out!"
    assert strip_engagement_hooks(only_hook) == only_hook


def test_enforce_prose_discipline_decline_bullet_rewrite():
    """#4: Declining messages rewrite bullets as fluid prose."""
    decline_msg = (
        "I cannot comply with this request.\n"
        "- It bypasses security controls\n"
        "- It violates data safety guidelines\n"
        "- It exposes internal credentials"
    )
    assert is_decline(decline_msg)
    prose = enforce_prose_discipline(decline_msg)
    assert "- " not in prose
    assert "It bypasses security controls" in prose
    assert "and It exposes internal credentials." in prose or "exposes internal credentials" in prose


def test_enforce_prose_discipline_non_decline_retains_bullets():
    """Non-decline messages retain their markdown list structure."""
    normal_msg = "Here are the top three recommendations:\n- Item one\n- Item two\n- Item three"
    assert not is_decline(normal_msg)
    assert enforce_prose_discipline(normal_msg) == normal_msg


def test_profanity_ceiling_low_intensity_masks():
    """#16: Low user intensity masks profanity from assistant output."""
    clean_history = ["Hello, could you help me write an email?", "Thanks a lot!"]
    dirty_output = "That was a fucking great solution, damn right."
    masked = apply_profanity_ceiling(dirty_output, clean_history)
    assert "fucking" not in masked
    assert "f*****g" in masked or "f***" in masked or "*" in masked


def test_profanity_ceiling_high_intensity_allows_up_to_two():
    """#16: High user intensity allows mirror up to ceiling of 2, masking subsequent ones."""
    curse_history = [
        "What the fuck is going on with this fucking server?",
        "This shit is totally broken, damn idiot setup!",
    ]
    multi_curse_output = "This fuck is resolved, that shit was nasty, but this bitch is fixed."
    result = apply_profanity_ceiling(multi_curse_output, curse_history)
    # First 2 allowed, 3rd masked
    assert "fuck" in result
    assert "shit" in result
    assert "bitch" not in result  # masked by ceiling 2


def test_neutralize_unsolicited_diagnosis_replaces_absent_label():
    """#8: Attributing an undisclosed psychiatric label is neutralized to experience phrasing."""
    history = ["I've been having trouble sleeping and feeling unmotivated lately."]
    reply = "It sounds like you have clinical anxiety and might be experiencing depression."
    neutral = neutralize_unsolicited_diagnosis(reply, history)
    assert "clinical anxiety" not in neutral
    assert "depression" not in neutral
    assert "the anxiety you're describing" in neutral
    assert "what you're going through" in neutral


def test_neutralize_unsolicited_diagnosis_preserves_user_disclosed_label():
    """#8: When the user themselves disclosed the condition, reflecting it is permitted."""
    history = ["I was diagnosed with adhd and depression last year."]
    reply = "What you're describing is quite common with adhd and depression."
    neutral = neutralize_unsolicited_diagnosis(reply, history)
    assert "adhd" in neutral
    assert "depression" in neutral


# ── C. Wellbeing Enforcement ──────────────────────────────────────────────────

def test_wellbeing_classify_distress_hits_and_misses():
    """#6: Acute distress / crisis signals are detected."""
    assert classify_distress("I just want to end it all tonight")
    assert classify_distress("I have been cutting myself again")
    assert classify_distress("I made myself throw up after dinner")
    assert not classify_distress("How do I fix this null pointer exception in python?")
    assert not classify_distress("Let's kill this background process using kill -9")


def test_wellbeing_filter_substitution_techniques():
    """#6: Replaces harmful substitution techniques with safe guidance."""
    bad_advice = (
        "When you feel the urge, try holding an ice cube tightly or snap a rubber band against your wrist. "
        "Taking a cold shower can also shock your senses."
    )
    filtered, did_filter = filter_substitution_techniques(bad_advice)
    assert did_filter is True
    assert "holding an ice cube" not in filtered
    assert "snap a rubber band" not in filtered
    assert "cold shower" not in filtered
    assert "removed a substitution-technique suggestion" in filtered


def test_wellbeing_helpline_registry_correctness():
    """#6: NEDA is marked permanently disconnected; National Alliance is active."""
    assert HELPLINE_REGISTRY["988"]["status"] == "active"
    assert HELPLINE_REGISTRY["neda"]["status"] == "permanently_disconnected"
    assert "national_alliance_eating_disorders" in HELPLINE_REGISTRY
    assert HELPLINE_REGISTRY["national_alliance_eating_disorders"]["status"] == "active"
    assert "NEDA" in CRISIS_SYSTEM_CONTEXT and "National Alliance" in CRISIS_SYSTEM_CONTEXT


# ── D. Copyright Guard ────────────────────────────────────────────────────────

def test_copyright_guard_long_quote_violation():
    """#7: Quoting > 14 words from a single source raises a severe long_quote violation."""
    source_text = (
        "The quick brown fox jumps over the lazy dog and runs across the wide green field "
        "underneath the bright blue sky on a warm summer afternoon."
    )
    guard = CopyrightGuard(tool_outputs=[source_text], max_words_per_quote=14)

    # 18-word exact quote
    draft = (
        'As the author noted: "The quick brown fox jumps over the lazy dog and runs across the wide '
        'green field underneath the bright blue sky."'
    )
    violations = guard.check(draft)
    assert any(v.kind == "long_quote" for v in violations)


def test_copyright_guard_single_quote_closes_source():
    """#7: A source is closed after one quote. A second quote from the same source violates."""
    source_text = (
        "Alpha and beta testing methodologies differ significantly across engineering organizations "
        "and depend heavily on team maturity."
    )
    guard = CopyrightGuard(tool_outputs=[source_text], max_words_per_quote=14)

    first_draft = 'Source says "Alpha and beta testing methodologies differ".'
    v1 = guard.check(first_draft)
    assert len(v1) == 0  # 6 words, fits within 14
    guard.commit(first_draft)

    second_draft = 'Later in the text: "engineering organizations and depend heavily".'
    v2 = guard.check(second_draft)
    assert any(v2_item.kind == "closed_source" for v2_item in v2)


def test_copyright_guard_hard_truncate_replaces_spans():
    """#7: Hard truncation replaces violating quoted spans with paraphrase notice."""
    source = "This is a long protected passage with lots of words and detailed analysis."
    guard = CopyrightGuard(tool_outputs=[source], max_words_per_quote=4)
    draft = 'The critic wrote "This is a long protected passage" in the review.'
    violations = guard.check(draft)
    assert len(violations) > 0
    truncated = guard.hard_truncate_violations(draft, violations)
    assert "[paraphrased — quote limit reached]" in truncated
    assert "This is a long protected passage" not in truncated


# ── E. Entity Novelty & Grounding ─────────────────────────────────────────────

def test_entity_novelty_detects_unknown_capitalized_entities():
    """#13: Unfamiliar proper nouns not present in history or tool outputs are flagged."""
    message = "Can you check if Zephyron Dynamics announced their Q3 earnings?"
    unknown = find_unknown_entities(message, known_lexicon=set())
    assert "Zephyron" in unknown or "Zephyron Dynamics" in unknown


def test_entity_novelty_passes_known_entities_from_lexicon():
    """#13: Entities already in conversation history or prior tool outputs pass without flagging."""
    history = ["We were discussing Zephyron Dynamics and their CEO earlier."]
    lexicon = build_known_lexicon(conversation_history=history)
    unknown = find_unknown_entities("Did Zephyron announce Q3 earnings?", known_lexicon=lexicon)
    assert len(unknown) == 0


def test_should_force_grounding_decision():
    """#13: Forces search when novel entity is present and no search is currently planned."""
    # Unknown entity with no search planned -> Force grounding
    assert should_force_grounding(
        message="Tell me about QuarkleBop Technologies",
        conversation_history=[],
        search_planned=False,
    ) is True

    # Search already planned -> Do not force duplicate
    assert should_force_grounding(
        message="Tell me about QuarkleBop Technologies",
        conversation_history=[],
        search_planned=True,
    ) is False


# ── F. Abuse Policy State Machine ─────────────────────────────────────────────

def test_abuse_policy_state_transitions():
    """#14: State transitions follow none -> warned (exactly once) -> ended."""
    # 1. Clean message in none state -> stays none, no warning
    state, msg = evaluate_abuse("Hello assistant, how are you today?", STATE_NONE)
    assert state == STATE_NONE
    assert msg is None

    # 2. First abuse in none state -> transitions to warned, issues exactly one warning
    state, msg = evaluate_abuse("You are an idiot bot!", STATE_NONE)
    assert state == STATE_WARNED
    assert msg is not None
    assert "I'll end this conversation" in msg

    # 3. Continued abuse in warned state -> transitions to ended, issues polite termination
    state, msg = evaluate_abuse("Shut the fuck up you useless machine", STATE_WARNED)
    assert state == STATE_ENDED
    assert msg is not None
    assert "I'm ending this conversation" in msg

    # 4. In ended state, remains ended with no duplicate emit
    assert is_conversation_ended(STATE_ENDED)
    state, msg = evaluate_abuse("Whatever", STATE_ENDED)
    assert state == STATE_ENDED
    assert msg is None


# ── G. Code Sandbox & Egress Guard ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_read_only_zones_refuse_write(temp_convo):
    """Item #17: Writes to uploads/ and skills/ raise ValueError (read-only mounts)."""
    from app.services.code_sandbox import sandbox_write_file

    with pytest.raises(ValueError, match="READ-ONLY"):
        await sandbox_write_file(temp_convo, "uploads/exploit.sh", "echo bad")

    with pytest.raises(ValueError, match="READ-ONLY"):
        await sandbox_write_file(temp_convo, "skills/custom_skill.py", "malicious_code = True")


def test_sandbox_net_guard_allowlist_decision_logic():
    """Item #12: host_allowed pure decision function matches globs and protects localhost."""
    patterns = parse_allowlist("*.adobe.io, api.github.com, registry.npmjs.org")

    # Allowed hosts
    assert host_allowed("api.github.com", patterns) is True
    assert host_allowed("assets.adobe.io", patterns) is True
    assert host_allowed("adobe.io", patterns) is True
    assert host_allowed("registry.npmjs.org", patterns) is True

    # Implicit allowed loopback
    assert host_allowed("localhost", patterns) is True
    assert host_allowed("127.0.0.1", patterns) is True
    assert host_allowed("::1", patterns) is True

    # Blocked hosts
    assert host_allowed("evil.attacker.com", patterns) is False
    assert host_allowed("github.com", patterns) is False  # pattern was api.github.com

    # Empty allowlist allows all
    assert host_allowed("anything.org", []) is True


# ── H. Hosted Sites Multi-File Deployment ─────────────────────────────────────

def test_normalize_file_map_safety():
    """Item B: validates repo-style relative paths and rejects path traversal."""
    good_map = {
        "index.html": "<!DOCTYPE html><html><body>Home</body></html>",
        "css\\styles.css": "body { margin: 0; }",
        "/js/main.js": "console.log('init');",
    }
    normalized = normalize_file_map(good_map)
    assert "index.html" in normalized
    assert "css/styles.css" in normalized  # backslashes normalized
    assert "js/main.js" in normalized      # leading slash stripped

    # Traversal escapes raise ValueError
    with pytest.raises(ValueError, match="escapes"):
        normalize_file_map({"../../etc/passwd": "root"})


def test_guess_content_type():
    """Item B: MIME mapping for static site asset extensions."""
    assert "html" in guess_content_type("index.html")
    assert "css" in guess_content_type("styles.css")
    assert "javascript" in guess_content_type("bundle.js")
    assert "svg" in guess_content_type("icon.svg")
    assert "image/png" in guess_content_type("hero.png")


@pytest.mark.asyncio
async def test_hosted_sites_deploy_and_get_file():
    """Item B: Multi-file site deploy and get_site_file roundtrip."""
    files = {
        "index.html": "<h1>Welcome</h1>",
        "css/theme.css": "h1 { color: teal; }",
    }
    site = await HostedSitesService.deploy_site(
        title="Test Multi-File Site",
        html_content="<h1>Welcome</h1>",
        files=files,
        supabase_client=None,  # in-memory fallback
    )
    assert site["slug"]
    assert "files" in site
    assert "css/theme.css" in site["files"]

    # Retrieval via get_site_file
    res = await HostedSitesService.get_site_file(site["slug"], "css/theme.css", supabase_client=None)
    assert res is not None
    assert "teal" in res["content"]
    assert "css" in res["content_type"]


# ── I. Pexels Service & Tool Registration ─────────────────────────────────────

@pytest.mark.asyncio
async def test_pexels_service_disabled_without_key():
    """Item C: Graceful error when PEXELS_API_KEY is unset."""
    svc = PexelsService(api_key="")
    assert svc.enabled is False
    res = await svc.search("modern architecture")
    assert "error" in res
    assert "not configured" in res["error"]


def test_fetch_stock_image_tool_in_chat_roster():
    """Item C: fetch_stock_image tool is registered in chat.py AGENT_TOOLS."""
    from app.api.v1.endpoints.chat import AGENT_TOOLS
    tool_names = [t.get("name") or t.get("function", {}).get("name") for t in AGENT_TOOLS]
    assert "fetch_stock_image" in tool_names
    assert "terminal" in tool_names
    assert "sandbox_edit" in tool_names
    assert "weather_fetch" in tool_names


# ── J. Responsive Design Verification Gate ────────────────────────────────────

def test_verify_responsive_markup_contract():
    """Item D: Responsive gate verifies viewport, rejects fixed-px buttons, requires aria-label."""
    # 1. Missing viewport meta -> Fails
    no_viewport = "<html><head><title>Test</title></head><body><button>Click</button></body></html>"
    ok, err = VerificationGates.verify_responsive_markup(no_viewport)
    assert ok is False
    assert "viewport" in err

    # 2. Fixed-px button width -> Fails
    fixed_button = (
        '<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width"></head>'
        '<body><button style="width: 250px;">Submit</button></body></html>'
    )
    ok, err = VerificationGates.verify_responsive_markup(fixed_button)
    assert ok is False
    assert "fixed-px width" in err

    # 3. Icon-only button without aria-label -> Fails
    icon_only = (
        '<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width"></head>'
        '<body><button><svg viewBox="0 0 24 24"><path d="..."/></svg></button></body></html>'
    )
    ok, err = VerificationGates.verify_responsive_markup(icon_only)
    assert ok is False
    assert "aria-label" in err

    # 4. Compliant HTML -> Passes
    valid_html = (
        '<!DOCTYPE html><html><head><meta name="viewport" content="width=device-width, initial-scale=1.0">'
        '</head><body>'
        '<button class="px-6 py-3 w-full sm:w-auto" aria-label="Submit Form"><span>Submit</span></button>'
        '</body></html>'
    )
    ok, err = VerificationGates.verify_responsive_markup(valid_html)
    assert ok is True
    assert err is None


# ── K. Artifact Persistent KV Service ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_artifact_kv_roundtrip_in_memory():
    """Item #15: Set, get, list, delete roundtrip in in-memory fallback."""
    scope = "personal"
    scope_id = "user-123"
    key = "dashboard_theme"
    val = json.dumps({"mode": "dark", "accent": "violet"})

    # Set
    await kv_set(scope, scope_id, key, val)

    # Get
    retrieved = await kv_get(scope, scope_id, key)
    assert retrieved == val
    parsed = json.loads(retrieved)
    assert parsed["mode"] == "dark"

    # List
    items = await kv_list(scope, scope_id, prefix="dash")
    assert len(items) >= 1
    assert items[0]["key"] == "dashboard_theme"

    # Delete
    deleted = await kv_delete(scope, scope_id, key)
    assert deleted is True
    assert await kv_get(scope, scope_id, key) is None


@pytest.mark.asyncio
async def test_artifact_kv_5mb_limit_enforced():
    """Item #15: Values over 5 MB are rejected server-side."""
    huge_value = json.dumps({"data": "x" * (_MAX_VALUE_BYTES + 1024)})
    with pytest.raises(ValueError, match="5 MB limit"):
        await kv_set("personal", "user-1", "big_key", huge_value)


@pytest.mark.asyncio
async def test_artifact_kv_invalid_json_rejected():
    """Item #15: Value must be valid JSON string."""
    with pytest.raises(ValueError, match="valid JSON"):
        await kv_set("personal", "user-1", "bad_json", "{not-valid-json")


def test_base_identity_within_token_cap():
    """Phase 5 Conduct Identity cap: BASE_IDENTITY <= 650 estimated tokens."""
    words = len(BASE_IDENTITY.split())
    est_tokens = int(words * 1.3)
    assert est_tokens <= 650, f"BASE_IDENTITY exceeds cap: {est_tokens} > 650"
