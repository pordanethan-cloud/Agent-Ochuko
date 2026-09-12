import pytest
from app.services.handle_intelligence import HandleIntelligence


def test_detect_platform():
    assert HandleIntelligence.detect_platform("https://www.linkedin.com/in/satyanadella") == "linkedin"
    assert HandleIntelligence.detect_platform("https://facebook.com/yann.lecun") == "facebook"
    assert HandleIntelligence.detect_platform("https://github.com/torvalds") == "github"
    assert HandleIntelligence.detect_platform("https://twitter.com/elonmusk") == "twitter"
    assert HandleIntelligence.detect_platform("https://x.com/karpathy") == "twitter"
    assert HandleIntelligence.detect_platform("unknown_random_string") == "generic"


def test_clean_handle():
    assert HandleIntelligence.clean_handle("@satyanadella") == "satyanadella"
    assert HandleIntelligence.clean_handle("https://www.linkedin.com/in/satyanadella/") == "satyanadella"
    assert HandleIntelligence.clean_handle("https://facebook.com/yann.lecun/") == "yann.lecun"
    assert HandleIntelligence.clean_handle("https://github.com/torvalds") == "torvalds"


@pytest.mark.asyncio
async def test_lookup_linkedin_profile():
    # Public figure profile lookup using Google Search Grounding bypass
    res = await HandleIntelligence.lookup_profile("https://www.linkedin.com/in/satyanadella", platform="linkedin")
    assert res.get("success") is True
    assert res.get("platform") == "linkedin"
    assert "Satya" in res.get("summary", "") or "Nadella" in res.get("summary", "")
    assert "Microsoft" in res.get("summary", "")


@pytest.mark.asyncio
async def test_lookup_facebook_profile():
    # Public figure profile lookup
    res = await HandleIntelligence.lookup_profile("https://facebook.com/yann.lecun", platform="facebook")
    assert res.get("success") is True
    assert res.get("platform") == "facebook"
    assert "Yann" in res.get("summary", "") or "LeCun" in res.get("summary", "")
