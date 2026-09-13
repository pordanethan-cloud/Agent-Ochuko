# tests/test_trusted_sources.py
"""
Trusted-source ranking for grounded search: trusted on-topic domains are
promoted to the front of results (Gemini grounding + Tavily paths), and
sports/score queries get news-recency treatment. Pure post-ranking — the
engine's relative order is otherwise preserved.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.api.v1.endpoints.chat import (
    _search_categories,
    _domain_of,
    rerank_results_by_trust,
)


def test_sports_query_detection():
    assert "sports" in _search_categories("Olise's goals this season")
    assert "sports" in _search_categories("who won the game last night")
    assert "sports" in _search_categories("Premier League standings")
    assert "sports" not in _search_categories("how to bake sourdough bread")
    assert "business" in _search_categories("Nigerian inflation rate 2026")
    assert "stats" in _search_categories("Nigeria population statistics")


def test_domain_extraction():
    assert _domain_of("https://www.bbc.co.uk/sport/football") == "bbc.co.uk"
    assert _domain_of("https://amp.cnn.com/cnn/2026/story") == "cnn.com"
    assert _domain_of("https://api.espn.com:443/v1") == "espn.com"
    assert _domain_of("https://user@site.co.za/page") == "site.co.za"
    assert _domain_of("not a url") == ""


def test_trusted_sources_promoted_to_front():
    results = [
        {"title": "Random blog", "url": "https://bavarianfootballworks.com/olise-goals"},
        {"title": "Forum thread", "url": "https://reddit.com/r/fcbayern/comments/x"},
        {"title": "Sky Sports", "url": "https://www.skysports.com/football/news/olise"},
        {"title": "Aggregator", "url": "https://some-aggregator.net/goals"},
        {"title": "UEFA", "url": "https://www.uefa.com/uefachampionsleague/news/"},
    ]
    ranked = rerank_results_by_trust(results, "Olise goals champions league")

    # Trusted on-topic domains first (Tier 0 official league/source uefa before Tier 1 skysports)
    assert ranked[0]["url"] == "https://www.uefa.com/uefachampionsleague/news/"
    assert ranked[1]["url"] == "https://www.skysports.com/football/news/olise"
    # Untrusted keep their original relative order after the promoted block
    untrusted = [r["url"] for r in ranked[2:]]
    assert untrusted == [
        "https://bavarianfootballworks.com/olise-goals",
        "https://reddit.com/r/fcbayern/comments/x",
        "https://some-aggregator.net/goals",
    ]


def test_livescore_ranked_first_for_live_matches():
    results = [
        {"title": "ABC News", "url": "https://abcnews.go.com/Sports/story?id=999"},
        {"title": "BBC Sport", "url": "https://www.bbc.com/sport/football/live/123"},
        {"title": "UEFA Official", "url": "https://www.uefa.com/match/456"},
        {"title": "LiveScore", "url": "https://www.livescore.com/en/football/2026-09-12/arsenal-vs-chelsea/"},
        {"title": "Sky Sports", "url": "https://www.skysports.com/football/arsenal-vs-chelsea"},
        {"title": "Goal Blog", "url": "https://www.goal.com/en/news/live/789"},
    ]
    ranked = rerank_results_by_trust(results, "Arsenal vs Chelsea live score")
    # LiveScore (Tier 0) must be promoted strictly ahead of official leagues (Tier 1), journalism (Tier 2), and broadcast blogs like ABC (Tier 3)
    assert ranked[0]["url"] == "https://www.livescore.com/en/football/2026-09-12/arsenal-vs-chelsea/"
    assert ranked[1]["url"] == "https://www.uefa.com/match/456"
    assert ranked[2]["url"] == "https://www.bbc.com/sport/football/live/123"
    assert ranked[3]["url"] == "https://www.skysports.com/football/arsenal-vs-chelsea"
    assert ranked[4]["url"] == "https://abcnews.go.com/Sports/story?id=999"
    assert ranked[5]["url"] == "https://www.goal.com/en/news/live/789"


def test_off_topic_trusted_not_promoted():
    # Business domains are NOT trusted for a sports query — a niche sports blog
    # with the exact answer must not be pushed behind an irrelevant bank site.
    results = [
        {"title": "Match report", "url": "https://bavarianfootballworks.com/report"},
        {"title": "Bank analytics", "url": "https://forbes.com/markets/notes"},
    ]
    ranked = rerank_results_by_trust(results, "Olise brace highlights")
    assert ranked[0]["url"] == "https://bavarianfootballworks.com/report"


def test_wikipedia_promoted_for_general_queries():
    results = [
        {"title": "Blog", "url": "https://randomblog.net/history-of-lagos"},
        {"title": "Wikipedia", "url": "https://en.wikipedia.org/wiki/Lagos"},
    ]
    ranked = rerank_results_by_trust(results, "history of Lagos")
    assert ranked[0]["url"] == "https://en.wikipedia.org/wiki/Lagos"


def test_no_results_and_empty_query_safe():
    assert rerank_results_by_trust([], "anything") == []
    results = [{"title": "A", "url": "https://example.com"}]
    assert rerank_results_by_trust(results, "")[0]["title"] == "A"
    assert rerank_results_by_trust([{"title": "No URL"}], "query")[0]["title"] == "No URL"
