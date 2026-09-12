import os
import json
import asyncio
import logging
import re
import uuid
import base64
import httpx
import shutil
import mimetypes
from html.parser import HTMLParser
from typing import List, Dict, Any, Optional
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from datetime import datetime, timezone
from app.core.jwt_validator import verify_jwt

from app.core.config import get_config
from app.core import model_router
from openai import AsyncAzureOpenAI
from app.services.supabase_admin import get_supabase_admin
from app.services.cloudflare_r2 import download_file_bytes
from app.services.queue_dispatcher import enqueue_job
from google import genai
from google.genai import types as genai_types
from app.core.verification_gates import verification_gates
from app.core.circuit_breaker import create_turn_circuit_breaker
from app.core.prompt_defense import prompt_defense
from app.core.reflexion_engine import create_reflexion_engine
from app.core.agent_tools import AGENT_TOOLS
from app.core.category_gate import route_tools as _route_tools
from app.core.memory_guard import check_pii, apply_memory_edit, describe_memory_version_conflict

logger = logging.getLogger("app.api.v1.endpoints.chat")
router = APIRouter()

# _OCHUKO_RULE removed — identity, tone, and capability instructions are now
# generated per-request by app.core.skills (skill-based prompt system).
# This eliminates ~350 tokens of overhead on every single request.

# Instruction injected into the system prompt for THINK/SOLVE modes only.
# Tells the model to show reasoning inside <thinking> tags before the answer.
# The backend strips these out, emits them as thinking_delta SSE events, and
# the frontend renders them in a collapsible panel — no new model required.
_THINKING_INSTRUCTION = (
    "\n\nREASONING MANDATE (THINK MODE):\n"
    "Before formulating your response, perform thorough step-by-step reasoning enclosed in <thinking>...</thinking> tags:\n"
    "<thinking>\n"
    "Break down the user's intent, evaluate potential edge cases, fact check assumptions, identify which tools to invoke, and outline your execution strategy.\n"
    "</thinking>\n"
    "CRITICAL AUTONOMOUS TOOL EXECUTION MANDATE:\n"
    "1. DO NOT output passive instructions telling the user what steps to take in the app UI, how to click buttons, or ask them to manually run commands or approve actions when you have tools available. YOU ARE AN AUTONOMOUS AGENT: intelligently decide which tools are needed and execute them directly.\n"
    "2. If computation, data parsing, algorithmic simulation, financial modeling, or graphing is required: immediately call `execute_code` in the sandbox and deliver real computed figures and outputs — NEVER return dead code snippets for the user to run themselves.\n"
    "3. If real-time facts, comparative benchmarks, or market info are needed: immediately call `search_web` or `deep_research`.\n"
    "4. If interactive UI widgets, calculators, or dynamic tables are needed: call `visualize__show_widget`.\n"
    "5. If creating or modifying files or projects: call `sandbox_write` or `deploy_site`.\n"
    "6. If the user asks to zip, package, or download the project, repository, or website files: NEVER output Python script code into chat for the user to run. Instead, execute code in the sandbox using `execute_code` to produce `project.zip` so a downloadable archive is generated directly for the user.\n"
    "7. After the closing </thinking> tag, you MUST ALWAYS provide the complete, detailed, polished final response with the actual findings and deliverables."
)

_THINK_OPEN_RE = re.compile(r"<(?:thinking|think|reasoning)>", re.IGNORECASE)
_THINK_CLOSE_RE = re.compile(r"</(?:thinking|think|reasoning)?>", re.IGNORECASE)

# Initialize OpenAI client lazily (so we don't crash at startup if config isn't loaded yet)
_openai_client: Optional[AsyncAzureOpenAI] = None


def get_openai_client() -> AsyncAzureOpenAI:
    global _openai_client
    if _openai_client is None:
        endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
        api_key = os.getenv("AZURE_OPENAI_API_KEY")
        api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2025-03-01-preview")

        if not endpoint or not api_key:
            raise HTTPException(
                status_code=500,
                detail="Azure OpenAI credentials are not properly configured on the server."
            )

        _openai_client = AsyncAzureOpenAI(
            azure_endpoint=endpoint,
            api_key=api_key,
            api_version=api_version
        )
    return _openai_client

async def _perform_open_websearch_fallback(query: str) -> tuple:
    """
    Fallback search using local open-websearch daemon/CLI.
    Queries the open-websearch daemon on http://127.0.0.1:3210.
    If the daemon is not running, attempts to start it in the background using `open-websearch serve`.
    """
    import subprocess
    import json
    import shutil
    import httpx

    daemon_url = "http://127.0.0.1:3210"
    daemon_running = False
    
    # 1. Check if daemon is running by querying /health
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            res = await client.get(f"{daemon_url}/health")
            if res.status_code == 200:
                daemon_running = True
    except Exception:
        pass

    if not daemon_running:
        logger.info("open-websearch daemon is not running. Starting it in background...")
        npx_path = shutil.which("npx")
        if npx_path:
            try:
                cmd = [npx_path, "open-websearch", "serve"]
                if os.name == 'nt':
                    subprocess.Popen(cmd, creationflags=subprocess.CREATE_NO_WINDOW, shell=True)
                else:
                    subprocess.Popen(cmd, start_new_session=True)
                
                # Wait up to 3 seconds for boot
                for _ in range(6):
                    await asyncio.sleep(0.5)
                    try:
                        async with httpx.AsyncClient(timeout=0.5) as client:
                            res = await client.get(f"{daemon_url}/health")
                            if res.status_code == 200:
                                daemon_running = True
                                logger.info("open-websearch daemon successfully started and ready")
                                break
                    except Exception:
                        pass
            except Exception as start_err:
                logger.error("Failed to start open-websearch daemon: %s", start_err)

    # 2. Perform the search query
    # If the daemon is running, query it via HTTP (POST /search).
    if daemon_running:
        try:
            logger.info("Querying open-websearch daemon: POST %s/search", daemon_url)
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(
                    f"{daemon_url}/search",
                    json={"query": query, "limit": 6, "engines": ["duckduckgo", "brave", "bing"]}
                )
                if res.status_code == 200:
                    json_data = res.json()
                    results = json_data.get("results", []) or json_data.get("data", {}).get("results", [])
                    if results:
                        search_chunks = []
                        sources = []
                        seen_urls = set()
                        for r in results:
                            title = r.get("title", "") or r.get("url", "")
                            url = r.get("url", "")
                            desc = r.get("description", "")
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                sources.append({"title": title, "url": url})
                                search_chunks.append(f"Source: {title}\nURL: {url}\nContent: {desc}")
                        google_context = "\n\n".join(search_chunks)
                        return google_context, sources
        except Exception as http_err:
            logger.warning("HTTP query to open-websearch daemon failed: %s. Falling back to CLI...", http_err)

    # CLI fallback (using npx)
    logger.info("Executing open-websearch via CLI subprocess...")
    npx_path = shutil.which("npx")
    if not npx_path:
        raise RuntimeError("npx not found in path")

    def _run_cli():
        cmd = [
            npx_path, "open-websearch", "search", query,
            "--limit", "6",
            "--engines", "duckduckgo,brave,bing",
            "--json"
        ]
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=25,
            shell=True if os.name == 'nt' else False
        )
        if proc.returncode == 0:
            stdout_text = proc.stdout or ""
            start_idx = stdout_text.find('{')
            if start_idx != -1:
                json_data = json.loads(stdout_text[start_idx:])
                results = json_data.get("data", {}).get("results", []) or json_data.get("results", [])
                if results:
                    search_chunks = []
                    sources = []
                    seen_urls = set()
                    for r in results:
                        title = r.get("title", "") or r.get("url", "")
                        url = r.get("url", "")
                        desc = r.get("description", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            sources.append({"title": title, "url": url})
                            search_chunks.append(f"Source: {title}\nURL: {url}\nContent: {desc}")
                    google_context = "\n\n".join(search_chunks)
                    return google_context, sources
        raise RuntimeError(f"CLI search failed with status {proc.returncode}")

    try:
        return await asyncio.to_thread(_run_cli)
    except Exception as e:
        logger.error("All open-websearch search methods failed: %s", e)
        raise e


# ── Time-aware search helpers ─────────────────────────────────────────────────
# Queries mentioning live/current data get the current year appended so search
# engines return fresh results, and every search context carries the execution
# date so the synthesising model can reason about recency.

_TIME_SENSITIVE_RE = re.compile(
    r"\b(latest|current|today|now|recent|this\s+(?:year|month|week)|"
    r"news|breaking|price|prices|rate|rates|update|updated|trending|2024|2025|2026|2027)\b",
    re.IGNORECASE,
)

# Relative date phrases that must resolve to explicit calendar dates before
# hitting a search engine — "yesterday night game" is useless to an index,
# "Champions League results September 9 2026" is not.
_RELATIVE_DATE_RE = re.compile(
    r"\b(yesterday(?:'s)?|last night|last evening|tonight|this morning|this afternoon|this evening)\b",
    re.IGNORECASE,
)


def _resolve_relative_dates(query: str) -> str:
    """Rewrites relative date phrases into explicit calendar dates (WAT)."""
    from datetime import timedelta
    q = (query or "").strip()
    if not _RELATIVE_DATE_RE.search(q):
        return q

    now = datetime.now(timezone(timedelta(hours=1)))
    today_str = now.strftime("%B %d, %Y")
    yesterday_str = (now - timedelta(days=1)).strftime("%B %d, %Y")

    def _sub(m: "re.Match[str]") -> str:
        phrase = m.group(0).lower()
        if phrase.startswith("yesterday") or "last night" in phrase or "last evening" in phrase:
            return yesterday_str
        return today_str

    return _RELATIVE_DATE_RE.sub(_sub, q)


def _time_aware_query(query: str) -> str:
    """Resolve relative dates, then append the current year to time-sensitive
    queries for freshness."""
    q = _resolve_relative_dates(query)
    current_year = datetime.now(timezone.utc).year
    if _TIME_SENSITIVE_RE.search(q) and str(current_year) not in q:
        return f"{q} {current_year}"
    return q


def _search_time_header() -> str:
    """Header prepended to every search context so the model knows 'now' and enforces temporal integrity."""
    from datetime import timedelta
    now = datetime.now(timezone(timedelta(hours=1)))
    return (
        f"[TEMPORAL ANCHOR & RECENCY MANDATE]\n"
        f"- Real-time timestamp: {now.strftime('%A, %B %d, %Y at %I:%M %p')} (WAT)\n"
        f"- Current calendar year: {now.year}\n"
        f"- TEMPORAL CONFLICT RULE: If sources conflict regarding dates, scores, rosters, prices, or status, strictly prioritize documents explicitly timestamped {now.year}. Disregard outdated historical articles from prior years.\n"
        f"- FACTUAL DENSITY RULE: Focus on exact numbers, verified scores, dates, statistics, and discrete entities. Do NOT write conversational filler or generic introductory recaps."
    )


# ── Trusted-source ranking ────────────────────────────────────────────────────
# The engine (Gemini grounding / Tavily) returns results in its own order with
# no source-quality weighting, so thin aggregator pages outrank wires and
# official bodies. We stable-sort trusted domains to the front; relative order
# of everything else is preserved (trusted results are promoted, never buried).

# Dedicated live score platforms & official league data (Tier 0 — ranks ABOVE everything else)
_SPORTS_PRIORITY_TIER_0: set = {
    "livescore.com", "livescores.com", "flashscore.com", "flashscore.co.uk",
    "sofascore.com", "fotmob.com", "whoscored.com", "premierleague.com",
    "uefa.com", "fifa.com", "bundesliga.com", "laliga.com", "legaseriea.it",
    "rfeb.es", "nba.com", "nfl.com", "mlb.com", "nhl.com", "olympics.com",
}

# Authoritative sports journalism & major broadcast desks (Tier 1)
_SPORTS_PRIORITY_TIER_1: set = {
    "skysports.com", "bbc.com", "bbc.co.uk", "espn.com", "espn.co.uk",
    "theathletic.com", "tntsports.co.uk", "reuters.com", "apnews.com",
}

# General sports news, transfer portals, and TV network blogs (Tier 2 — ranks below dedicated live scores)
_SPORTS_PRIORITY_TIER_2: set = {
    "nbcsports.com", "cbssports.com", "foxsports.com", "transfermarkt.com",
    "dazn.com", "goal.com", "eurosport.com", "sportsnet.ca", "bleacherreport.com",
}

_TRUSTED_SOURCE_DOMAINS: Dict[str, set] = {
    "sports": _SPORTS_PRIORITY_TIER_0 | _SPORTS_PRIORITY_TIER_1 | _SPORTS_PRIORITY_TIER_2,
    "news": {
        "reuters.com", "apnews.com", "bbc.com", "bbc.co.uk", "aljazeera.com",
        "cnn.com", "nytimes.com", "theguardian.com", "washingtonpost.com",
        "dw.com", "france24.com", "economist.com", "ft.com", "bloomberg.com",
    },
    "business": {
        "bloomberg.com", "ft.com", "wsj.com", "forbes.com", "cnbc.com",
        "reuters.com", "economist.com", "marketwatch.com", "investing.com",
        "morningstar.com", "sec.gov", "imf.org",
    },
    "tech": {
        "techcrunch.com", "theverge.com", "wired.com", "arstechnica.com",
        "engadget.com", "zdnet.com", "venturebeat.com", "reuters.com",
        "bbc.com", "nature.com", "ieee.org",
    },
    "stats": {
        "statista.com", "data.worldbank.org", "oecd.org", "imf.org",
        "ourworldindata.org", "census.gov", "europa.eu", "un.org",
    },
    "general": {
        "wikipedia.org", "britannica.org", "britannica.com", "mozilla.org",
        "github.com", "stackoverflow.com", "python.org", "docs.microsoft.com",
        "learn.microsoft.com", "developer.mozilla.org",
    },
}

_SEARCH_CATEGORY_RES: Dict[str, "re.Pattern"] = {
    "sports": re.compile(
        r"\b(score|scores|goal|goals|scorer|scorers|match|matches|game|games|"
        r"standings|fixtures?|league|cup|braces?|hat[\s-]?trick|highlights?|"
        r"transfer|transfers|lineup|line-ups?|injur\w+|nfl|nba|mlb|nhl|fifa|uefa|"
        r"premier\s+league|la\s+liga|bundesliga|serie\s+a|ligue\s+1|champions\s+league|"
        r"europa\s+league|cricket|tennis|formula\s*1|f1|olympics?|world\s+cup|"
        r"liverpool|chelsea|arsenal|man\s+utd|man\s+city|manchester\s+united|manchester\s+city|"
        r"tottenham|spurs|aston\s+villa|newcastle|everton|west\s+ham|fulham|brighton|"
        r"wolves|wolverhampton|brentford|crystal\s+palace|nottingham\s+forest|bournemouth|"
        r"leicester|ipswich|southampton|hull|hull\s+city|leeds|barcelona|barca|real\s+madrid|"
        r"atletico|bayern|dortmund|psg|juventus|inter\s+milan|ac\s+milan|napoli|roma|"
        r"lakers|celtics|warriors|bulls|heat|chiefs|eagles|cowboys|yankees|dodgers)\b",
        re.IGNORECASE,
    ),
    "business": re.compile(
        r"\b(stock|stocks|share|shares|market|markets|ipo|earnings|revenue|"
        r"inflation|interest\s+rate|interest\s+rates|fed|ecb|forex|exchange\s+rate|"
        r"crypto|bitcoin|ethereum|merger|acquisition|valuation|gdp|unemployment|"
        r"economy|economic)\b",
        re.IGNORECASE,
    ),
    "tech": re.compile(
        r"\b(iphone|ipad|android|macbook|windows\s+11|llm|gpt|gemini|"
        r"openai|anthropic|startup|seed\s+round|series\s+[ab]|funding|gadget|"
        r"firmware|os\s+update|gpu|cpu|processor|developer|api|framework)\b",
        re.IGNORECASE,
    ),
    "stats": re.compile(
        r"\b(statistics|stats|statistic|percentage|percent|demographics|"
        r"market\s+size|population|census|survey|per\s+capita|average)\b",
        re.IGNORECASE,
    ),
}

# Multi-part public suffixes for registrable-domain extraction.
_MULTIPART_TLDS = {
    "co.uk", "org.uk", "gov.uk", "ac.uk", "co.jp", "co.za", "com.au",
    "com.br", "co.in", "com.ng", "co.ke", "com.mx", "co.kr", "com.tr",
    "co.nz", "org.nz", "com.sg", "com.ar",
}


def _search_categories(query: str) -> set:
    """Detects query categories (sports/business/tech/stats) via regex — <0.1ms."""
    cats = set()
    q = query or ""
    for cat, rx in _SEARCH_CATEGORY_RES.items():
        if rx.search(q):
            cats.add(cat)
    return cats


def _domain_of(url: str) -> str:
    """Extracts the registrable domain ('https://amp.bbc.co.uk/x' -> 'bbc.co.uk')."""
    try:
        netloc = (urlsplit(url).netloc or "").lower()
        netloc = netloc.split("@")[-1].split(":")[0]
        if netloc.startswith("www."):
            netloc = netloc[4:]
        labels = netloc.split(".")
        if len(labels) >= 3 and ".".join(labels[-2:]) in _MULTIPART_TLDS:
            return ".".join(labels[-3:])
        if len(labels) >= 2:
            return ".".join(labels[-2:])
        return netloc
    except Exception:
        return ""


def rerank_results_by_trust(results: List[Dict[str, Any]], query: str, url_key: str = "url") -> List[Dict[str, Any]]:
    """
    Stable-sorts search results so trusted, on-topic domains come first.
    Dedicated live score providers (livescore.com, flashscore.com, official leagues) rank in Tier 0
    for sports queries, strictly above broadcast/cable news portals like nbcsports.com (Tier 2).
    """
    if not results:
        return results
    cats = _search_categories(query)

    def _domain_tier(d: str) -> int:
        if "sports" in cats:
            if d in _SPORTS_PRIORITY_TIER_0:
                return 0  # Dedicated live scores & official leagues (LiveScore, FlashScore)
            if d in _SPORTS_PRIORITY_TIER_1:
                return 1  # Sky Sports, BBC Sport, ESPN
            if d in _SPORTS_PRIORITY_TIER_2:
                return 2  # NBC Sports, CBS Sports, TV blogs
        for cat in cats:
            if d in _TRUSTED_SOURCE_DOMAINS.get(cat, set()):
                return 3
        if d in _TRUSTED_SOURCE_DOMAINS.get("general", set()):
            return 4
        return 5

    def _rank(idx_item):
        idx, item = idx_item
        d = _domain_of(item.get(url_key, "") or "")
        return (_domain_tier(d), idx)

    decorated = sorted(enumerate(results), key=_rank)
    return [item for _, item in decorated]


async def _perform_tavily_search(query: str) -> tuple:
    """
    Primary retrieval via the Tavily Search API (advanced depth).

    Unlike snippet-only metasearch, Tavily advanced returns page-level content
    extracts per result plus an optional synthesized answer — this is what
    closes the quality gap vs enterprise-grade grounded search.

    Returns (google_context, sources) in the same shape as the Gemini grounding
    path. Raises RuntimeError when TAVILY_API_KEY is missing or the call fails,
    so callers can cascade to the Gemini/open-websearch fallbacks.
    """
    api_key = os.getenv("TAVILY_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY is not configured.")

    payload: Dict[str, Any] = {
        "api_key": api_key,
        "query": _time_aware_query(query),
        "search_depth": "advanced",
        "include_answer": True,
        "include_raw_content": False,
        "max_results": 8,
    }
    # News-class queries get recency filtering (last 30 days). Sports queries
    # are inherently current-events (scores, transfers) — include them.
    if _TIME_SENSITIVE_RE.search(query) or _search_categories(query):
        payload["topic"] = "news"
        payload["days"] = 30

    async with httpx.AsyncClient(timeout=20.0) as client:
        res = await client.post("https://api.tavily.com/search", json=payload)
        res.raise_for_status()
        data = res.json()

    results = data.get("results", []) or []
    # Promote trusted, on-topic sources (wires, official bodies) to the front.
    results = rerank_results_by_trust(results, query)
    sources: List[Dict[str, str]] = []
    chunks: List[str] = []
    seen_urls: set = set()
    for r in results:
        url = r.get("url", "")
        if not url or url in seen_urls:
            continue
        seen_urls.add(url)
        title = r.get("title", "") or url
        content = (r.get("content", "") or "").strip()
        published = r.get("published_date", "") or ""
        sources.append({"title": title, "url": url})
        chunk = f"Source: {title}\nURL: {url}"
        if published:
            chunk += f"\nPublished: {published}"
        chunk += f"\nContent: {content}"
        chunks.append(chunk)

    context_parts = [_search_time_header(), f"Search Query: {query}"]
    tavily_answer = (data.get("answer", "") or "").strip()
    if tavily_answer:
        context_parts.append(f"VERIFIED LIVE FACTS & EVIDENCE:\n{tavily_answer}")
    context_parts.append(
        "GROUNDING SNIPPETS & SOURCES:\n" + ("\n\n".join(chunks) if chunks else "No live web results found.")
    )
    google_context = "\n\n".join(context_parts)
    return google_context, sources[:20]


# ── fetch_url: full-page reader (free, no paid API) ───────────────────────────
# High-fidelity lever: after search_web surfaces a promising result, read the
# actual page content instead of synthesising from thin snippets.

class _HTMLTextExtractor(HTMLParser):
    """Stdlib HTMLParser that extracts readable text, skipping script/style."""
    _SKIP_TAGS = {"script", "style", "noscript", "template", "svg", "head"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._chunks: List[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self._SKIP_TAGS:
            self._skip_depth += 1
        elif tag in ("p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article"):
            self._chunks.append("\n")

    def handle_endtag(self, tag):
        if tag in self._SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data):
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data.strip())

    def get_text(self) -> str:
        import re as _re
        text = " ".join(self._chunks)
        return _re.sub(r"\n{3,}", "\n\n", _re.sub(r"[ \t]{2,}", " ", text)).strip()


def _html_to_text(html: str) -> str:
    """Converts raw HTML to clean readable text (stdlib only, no new deps)."""
    extractor = _HTMLTextExtractor()
    try:
        extractor.feed(html)
    except Exception:
        pass
    return extractor.get_text()


async def _perform_fetch_url(url: str) -> str:
    """
    Fetches a web page and returns clean, token-safe text content.

    Returns a string suitable for direct injection into the tool-output
    context. Never raises to the model context — errors degrade to a
    graceful one-line notice the model can act on.
    """
    url = (url or "").strip()
    if not url:
        return "fetch_url error: no URL provided."
    if not url.startswith(("http://", "https://")):
        return f"fetch_url error: '{url[:100]}' is not a valid http(s) URL."

    # 1. Intercept YouTube URLs for rich transcript & timed speech extraction
    try:
        from app.services.youtube_intelligence import YouTubeIntelligence
        if YouTubeIntelligence.contains_youtube_link(url):
            yt_res = await YouTubeIntelligence.process_youtube_url(url)
            if yt_res.get("success"):
                return yt_res.get("formatted_context", "")
            return f"fetch_url (YouTube): {yt_res.get('error', 'Could not retrieve video transcript')}"
    except Exception as yt_err:
        logger.warning(f"fetch_url YouTube interception error: {yt_err}")

    # 2. Intercept LinkedIn / Facebook URLs to bypass login authwalls via Google Search Grounding
    try:
        if "linkedin.com/in/" in url or "facebook.com/" in url:
            from app.services.handle_intelligence import HandleIntelligence
            platform = "linkedin" if "linkedin.com" in url else "facebook"
            prof_res = await HandleIntelligence.lookup_profile(url, platform=platform)
            if prof_res.get("success"):
                return prof_res.get("summary", "")
            return f"fetch_url ({platform.capitalize()}): {prof_res.get('error', 'Could not resolve profile')}"
    except Exception as prof_err:
        logger.warning(f"fetch_url Profile interception error: {prof_err}")

    try:
        async with httpx.AsyncClient(
            timeout=20.0,
            follow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0 (compatible; AgentOchuko/1.0; +https://ochuko.ai)"},
        ) as client:
            res = await client.get(url)
            res.raise_for_status()
    except Exception as e:
        logger.warning("fetch_url failed for %.120s: %s", url, e)
        return f"fetch_url error: could not retrieve {url[:200]} ({type(e).__name__})."

    content_type = res.headers.get("content-type", "")
    if "html" in content_type or "xml" in content_type or "text/plain" in content_type:
        body = res.text
    else:
        return f"fetch_url error: unsupported content type '{content_type or 'unknown'}' at {url[:200]}."

    if "html" in content_type:
        body = _html_to_text(body)

    _MAX_PAGE_TEXT = 12000
    if len(body) > _MAX_PAGE_TEXT:
        body = body[:_MAX_PAGE_TEXT] + "\n\n[... page content truncated ...]"
    if not body.strip():
        return f"fetch_url: retrieved {url[:200]} but no readable text was found (page may be JS-rendered)."

    retrieved_date = _search_time_header().split(".")[0]
    return f"Content from {url} ({retrieved_date}):\n\n{body}"


async def _perform_google_search(
    query: str,
    synthesis_deployment: str = "",
    history: List[Dict[str, Any]] = None,
    return_raw: bool = False,
) -> Dict[str, Any]:
    """
    Three-tier hybrid search pipeline:

    Phase 0 — Tavily Retrieval (primary, when TAVILY_API_KEY is configured)
        Advanced-depth search with page-level content extracts, recency
        filtering for news-class queries, and date-stamped context.

    Phase 1 — Google Retrieval (Gemini 2.5 Flash, google-genai SDK)
        Triggers the Google Search grounding tool to pull live web snippets
        and source metadata. Gemini is used ONLY for retrieval — it is the
        lightest, fastest path to real-time Google results.

    Phase 1-fallback — open-websearch daemon/CLI (DuckDuckGo/Brave/Bing)

    Phase 2 — Azure Synthesis (Azure OpenAI Responses API, async)
        The raw retrieved context is packaged into a system prompt and forwarded
        to the Azure OpenAI deployment for accurate, structured synthesis.

    Returns { "answer": str, "sources": [{"title": str, "url": str}] }
    """
    google_api_key = os.getenv("GOOGLE_API_KEY")
    if not google_api_key and not os.getenv("TAVILY_API_KEY"):
        raise RuntimeError("No web search provider configured (set GOOGLE_API_KEY or TAVILY_API_KEY).")

    # ── Phase 1: Google Grounding via Gemini 2.5 Flash ────────────────────
    # Run the synchronous google-genai call off the event loop thread
    def _google_retrieval_phase() -> tuple:
        keys = []
        for var_name in ["GOOGLE_API_KEY", "GEMINI_API_KEY", "GEMINI_API_KEY_2", "GEMINI_API_KEY_3", "GEMINI_API_KEY_4"]:
            key = os.getenv(var_name)
            if key and key.strip() and key not in keys:
                keys.append(key.strip())
        
        if not keys:
            raise RuntimeError("No Google/Gemini API keys configured in environment.")

        history_context = ""
        if history:
            history_context = "Recent conversation context:\n"
            for msg in history[-5:]:
                role = "User" if msg.get("role") == "user" else "Assistant"
                content = msg.get("content", "")
                if "[Google Search Result for:" in content:
                    parts = content.split("[Google Search Result for:")
                    content = parts[0].strip()
                history_context += f"{role}: {content}\n"
            history_context += "\n"

        sports_instruction = ""
        if "sports" in _search_categories(query):
            sports_instruction = (
                "\nSPORTS GROUNDING MANDATE:\n"
                "- Search for live scores, match fixtures, and results on dedicated live score platforms (LiveScore, FlashScore, official league sites).\n"
                "- CRITICAL FOR GOALLESS MATCHES: If a match is in progress or completed and reported as 'goalless', 'deadlocked', or '0-0', the exact score IS 0 - 0. Never say 'score is unavailable' when a game is goalless.\n"
                "- Extract exact home and away team names, numeric score (e.g. 0-0, 2-1), match clock/status, and all goal/card events."
            )

        gemini_query = (
            f"{_search_time_header()}\n\n"
            f"{history_context}"
            f"Target Query: {query}\n\n"
            "INSTRUCTION: Search Google for the target query, strictly resolving any ambiguous pronouns ('they', 'their', 'it') from the conversation context into concrete entity names. "
            "Retrieve and extract dense, verified, factual details: exact scores, statistics, names, key events, and publication dates. "
            f"{sports_instruction}\n"
            "Do NOT write conversational filler, introductory pleasantries, or generic recaps."
        )

        last_exc = None
        for idx, key in enumerate(keys):
            try:
                g_client = genai.Client(api_key=key)
                g_response = g_client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=gemini_query,
                    config=genai_types.GenerateContentConfig(
                        tools=[genai_types.Tool(google_search=genai_types.GoogleSearch())],
                        temperature=0.1,  # near-zero: we want faithful retrieval, not creativity
                    ),
                )

                search_chunks: List[str] = []
                sources: List[Dict[str, str]] = []
                seen_urls: set = set()

                if g_response.candidates and g_response.candidates[0].grounding_metadata:
                    metadata = g_response.candidates[0].grounding_metadata

                    # Build deduplicated source list from grounding_chunks
                    for chunk in (getattr(metadata, "grounding_chunks", []) or []):
                        web = getattr(chunk, "web", None)
                        if web:
                            url = getattr(web, "uri", "") or ""
                            title = getattr(web, "title", "") or url
                            if url and url not in seen_urls:
                                seen_urls.add(url)
                                sources.append({"title": title, "url": url})

                    # Extract actual text segments from grounding_supports (preferred)
                    for support in (getattr(metadata, "grounding_supports", []) or []):
                        segment = getattr(support, "segment", None)
                        text = (getattr(segment, "text", "") or "").strip()
                        if text:
                            search_chunks.append(text)

                # Fallback: if grounding_supports is empty, format source titles as context
                if not search_chunks and sources:
                    for s in sources[:6]:
                        search_chunks.append(f"Source: {s['title']}\nURL: {s['url']}")

                google_context_chunks = "\n\n".join(search_chunks[:14]) if search_chunks else ""
                
                # Format as grounded evidence blocks rather than a pre-chewed essay
                gemini_text = (getattr(g_response, "text", "") or "").strip()
                context_parts = [_search_time_header(), f"Search Query: {query}"]
                if gemini_text:
                    context_parts.append(f"VERIFIED LIVE FACTS & EVIDENCE:\n{gemini_text}")
                if google_context_chunks:
                    context_parts.append(f"GROUNDING SNIPPETS & SUPPORTS:\n{google_context_chunks}")
                if not gemini_text and not google_context_chunks:
                    context_parts.append("No live web results found.")

                google_context = "\n\n".join(context_parts)
                # Promote trusted sources to the front of the source list.
                sources = rerank_results_by_trust(sources, query)
                return google_context, sources[:20]  # Increased cap: frontend de-duplicates across iterations
            except Exception as e:
                logger.warning("Google search failed with key index %d: %s", idx, e)
                last_exc = e
                continue

        raise last_exc or RuntimeError("All Gemini API keys failed.")

    # ── Phase 0: Tavily retrieval (primary — page-level content depth) ────
    try:
        google_context, sources = await _perform_tavily_search(query)
        logger.info("Tavily retrieval succeeded for query: %.80s", query)
    except Exception as tavily_err:
        logger.info("Tavily retrieval unavailable (%s). Falling back to Gemini grounding...", tavily_err)
        try:
            google_context, sources = await asyncio.to_thread(_google_retrieval_phase)
        except Exception as google_err:
            logger.warning("Primary Google search retrieval failed: %s. Attempting open-websearch fallback...", google_err)
            try:
                google_context, sources = await _perform_open_websearch_fallback(query)
                logger.info("Successfully retrieved search results using open-websearch fallback")
            except Exception as fallback_err:
                logger.error("Fallback open-websearch also failed: %s. Reverting to empty context.", fallback_err)
                google_context = "Google web search was unavailable. Fallback to your built-in search or training knowledge to answer."
                sources = []

    if return_raw:
        return {
            "google_context": google_context,
            "sources": sources,
            "answer": google_context
        }

    # ── Phase 2: Azure OpenAI Responses API Synthesis (async) ─────────────
    # The Google context is injected into the system prompt so Azure OpenAI
    # synthesises a grounded, cited answer — never raw Gemini output.
    deploy = (
        synthesis_deployment
        or os.getenv("SOLVE_MODEL_DEPLOYMENT")
        or os.getenv("AZURE_OPENAI_SOLVE_DEPLOYMENT")
        or "gpt-5.6-luna"
    )

    system_prompt = (
        "You are an elite real-time intelligence assistant. "
        "Your task is to answer the user's question accurately using the live web grounding evidence below.\n\n"
        "FACTUAL DENSITY & ANTI-FLUFF RULES:\n"
        "1. Lead immediately with the direct answer, exact figures, scores, dates, status, and concrete facts. Do NOT write boilerplate introductory recaps or generic summaries.\n"
        "2. If the user asks for a live score, match update, or team name (e.g. 'Liverpool', 'Chelsea'): state the exact current score, minute/status, and key events in the very first sentence.\n"
        "   - LIVE STATUS ACCURACY: If a match is in progress, state the active clock or half (e.g. '45\\' + 3\\'', 'HT', 'LIVE — second half', '68\\''). NEVER report 'FT' (Full Time) for an ongoing match.\n"
        "   - GOALLESS MATCHES: If a game is in progress or completed and reported as 'goalless' or 'no goals yet', the score IS 0 - 0. NEVER state 'live score is unavailable' when a game is goalless.\n"
        "   - SPORTS SCOREBOARD CARD: Whenever a live match, completed game, or upcoming fixture is discussed, ALWAYS include a ```sports_card JSON block (or invoke render_sports_card) with home_team, away_team, home_score (use 0 if goalless), away_score (use 0 if goalless), status, competition, and the FULL events list (goals, yellow/red cards, substitutions).\n"
        "3. Prioritize information timestamped with the current calendar year. Disregard outdated historical articles if they conflict with live data.\n"
        "4. Use bullet points or concise data blocks for multi-item facts or statistics.\n"
        "5. Cite every factual claim using [n](url) markers corresponding to the sources below.\n\n"
        "--- LIVE WEB GROUNDING EVIDENCE ---\n"
        f"{google_context}\n"
        "--- END LIVE WEB EVIDENCE ---"
    )

    try:
        az_client = get_openai_client()
        
        # Build input messages: system prompt + history + current query
        input_messages = [{"role": "system", "content": system_prompt}]
        if history:
            for msg in history:
                role = msg.get("role")
                content = msg.get("content", "")
                if role == "assistant" and "[Google Search Result for:" in content:
                    parts = content.split("[Google Search Result for:")
                    content = parts[0].strip()
                input_messages.append({"role": role, "content": content})
        input_messages.append({"role": "user", "content": query})

        az_response = await az_client.responses.create(
            model=deploy,
            input=[normalize_responses_message(m) for m in input_messages],
        )

        answer: str = az_response.output_text or ""
        
        # Extract token usage or calculate fallback estimate if 0/None
        prompt_tokens = 0
        completion_tokens = 0
        if az_response and hasattr(az_response, "usage") and az_response.usage:
            prompt_tokens = getattr(az_response.usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(az_response.usage, "completion_tokens", 0) or 0
            
        est_input = sum(len(m.get("content", "")) for m in input_messages) // 4
        est_output = len(answer) // 4
        prompt_tokens = prompt_tokens if prompt_tokens > 0 else max(50, est_input)
        completion_tokens = completion_tokens if completion_tokens > 0 else max(10, est_output)

        return {
            "answer": answer,
            "sources": sources,
            "tokens_input": prompt_tokens,
            "tokens_output": completion_tokens,
            "model": deploy,
        }
    except Exception as e:
        import traceback
        print("--- CHAT AZURE SYNTHESIS PHASE ERROR ---")
        traceback.print_exc()
        print("-----------------------------------------")
        raise



async def _perform_parallel_searches(
    queries: List[str],
    deployment: str,
    history: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Fan-out parallel search: runs up to 6 queries concurrently using asyncio.gather,
    merges the returned contexts, and deduplicates sources.

    Returns a dict with:
      - "merged_context": str  — combined Google context from all queries
      - "sources":        list — deduplicated [{title, url}] across all queries
      - "query_count":    int  — number of sub-queries that succeeded
    """
    queries = queries[:6]  # hard cap
    if not queries:
        return {"merged_context": "No queries provided.", "sources": [], "query_count": 0}

    tasks = [
        _perform_google_search(
            q,
            synthesis_deployment=deployment,
            history=history,
            return_raw=True,
        )
        for q in queries
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    merged_parts: List[str] = []
    seen_urls: set = set()
    all_sources: List[Dict[str, str]] = []
    succeeded = 0

    for q, result in zip(queries, results):
        if isinstance(result, Exception):
            logger.warning("Parallel search sub-query failed for '%s': %s", q, result)
            merged_parts.append(f"[Sub-query '{q}' failed: {result}]")
            continue
        succeeded += 1
        ctx = result.get("google_context", "") or result.get("answer", "")
        if ctx:
            merged_parts.append(f"--- Results for: {q} ---\n{ctx}")
        for src in result.get("sources", []):
            url = src.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_sources.append(src)

    merged_context = "\n\n".join(merged_parts) if merged_parts else "No results returned."
    return {
        "merged_context": merged_context,
        "sources": all_sources[:30],  # cap total sources at 30
        "query_count": succeeded,
    }


async def _enqueue_image_gen(user_id: str, conversation_id: str, prompt: str, style: str = "") -> str:
    """
    Creates a pending image_gen job row in Supabase and dispatches it to the
    Azure Queue Storage. Returns the new job_id.
    """
    supabase = get_supabase_admin()
    job_data = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "type": "image_gen",
        "status": "pending",
        "input_metadata": {"prompt": prompt, "style": style or "photorealistic"},
    }
    job_res = supabase.table("jobs").insert(job_data).execute()
    if not job_res.data:
        raise RuntimeError("Failed to create image_gen job row in database.")
    job_id: str = job_res.data[0]["id"]

    # enqueue_job is synchronous — run it off the event loop thread
    await asyncio.to_thread(
        enqueue_job,
        job_id=job_id,
        job_type="image_gen",
        input_metadata={"prompt": prompt, "style": style or "photorealistic"},
        user_id=user_id,
    )
    logger.info("Enqueued image_gen job %s for user %s — prompt: %.60s", job_id, user_id, prompt)
    return job_id


async def mock_stream_generator():
    """Fallback mock generator to verify connection if OpenAI is unavailable."""
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "Scaffolding "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "working! "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "Phase 1 "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "SSE Stream "}}) + "\n\n"
    yield "data: " + json.dumps({"type": "content_block_delta", "delta": {"text": "verified."}}) + "\n\n"
    yield "data: [DONE]\n\n"


def normalize_responses_message(msg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalizes a message dictionary to be strictly compliant with Azure OpenAI
    Responses API (EasyInputMessageParam).
    
    Ensures:
      - Valid role: 'system', 'developer', 'user', 'assistant'
      - Content is either a string OR a list of valid parts:
        * 'input_text' (for user/system/developer)
        * 'input_image' with {'image_url': '...', 'detail': 'auto'}
        * 'input_file'
      - Pure text part lists are collapsed into clean unified strings.
      - Converts legacy 'type': 'text' -> 'input_text' / collapsed string.
      - Converts legacy 'type': 'image_url' -> 'input_image'.
    """
    role = msg.get("role", "user")
    if role not in ("user", "assistant", "system", "developer"):
        role = "user"
    
    raw_content = msg.get("content", "")
    
    if isinstance(raw_content, str):
        return {"role": role, "content": raw_content}
        
    if isinstance(raw_content, list):
        # Check if list contains any media attachments
        has_media = any(
            isinstance(part, dict) and part.get("type") in ("image_url", "input_image", "input_file")
            for part in raw_content
        )
        
        if not has_media:
            # Collapse text parts into a single string for maximum compatibility
            texts = []
            for part in raw_content:
                if isinstance(part, str):
                    texts.append(part)
                elif isinstance(part, dict):
                    texts.append(str(part.get("text", "")))
                else:
                    texts.append(str(part))
            return {"role": role, "content": "\n\n".join(t for t in texts if t)}
            
        norm_parts = []
        for part in raw_content:
            if isinstance(part, str):
                norm_parts.append({"type": "input_text", "text": part})
            elif isinstance(part, dict):
                p_type = part.get("type", "")
                if p_type in ("text", "input_text"):
                    norm_parts.append({"type": "input_text", "text": str(part.get("text", ""))})
                elif p_type in ("image_url", "input_image"):
                    img_val = part.get("image_url", "")
                    if isinstance(img_val, dict):
                        img_url_str = img_val.get("url", "")
                    else:
                        img_url_str = str(img_val or "")
                    norm_parts.append({
                        "type": "input_image",
                        "image_url": img_url_str,
                        "detail": part.get("detail", "auto")
                    })
                elif p_type == "input_file":
                    norm_parts.append(part)
                else:
                    text_val = part.get("text") or str(part)
                    norm_parts.append({"type": "input_text", "text": text_val})
        return {"role": role, "content": norm_parts}
        
    return {"role": role, "content": str(raw_content or "")}


async def build_llm_context(conversation_id: str) -> List[Dict[str, Any]]:
    """
    Builds the context for the LLM by fetching non-archived messages from the database.
    This automatically includes the summary message (if compaction ran) and recent active turns.

    Token efficiency:
    - Summary messages are included as-is (they replace archived turns).
    - Raw Google Search Result blocks embedded in historical messages are stripped;
      only the clean synthesised answer text is retained. Search context is not
      useful as conversational history — it was relevant only at call time.
    - [Tool Output for ...] system messages from the agent loop are also stripped
      to avoid replaying raw tool outputs as permanent history.
    """
    supabase = get_supabase_admin()
    try:
        def fetch_msgs():
            return (
                supabase.table("messages")
                .select("role, content, is_summary, content_parts")
                .eq("conversation_id", conversation_id)
                .eq("is_archived_msg", False)
                .order("created_at", desc=False)
                .execute()
            )
        response = await asyncio.to_thread(fetch_msgs)
        db_messages = response.data or []

        formatted_messages: List[Dict[str, Any]] = []

        # Inject persisted conversation memory (agent_memory JSONB) as a leading
        # system message so remembered user facts/preferences are always in context.
        try:
            def fetch_memory():
                return (
                    supabase.table("conversations")
                    .select("agent_memory")
                    .eq("id", conversation_id)
                    .single()
                    .execute()
                )
            mem_res = await asyncio.to_thread(fetch_memory)
            agent_memory = (mem_res.data or {}).get("agent_memory") or {}
            if isinstance(agent_memory, dict) and agent_memory:
                mem_lines = [f"- {k}: {v}" for k, v in agent_memory.items()]
                formatted_messages.append({
                    "role": "system",
                    "content": "[Conversation Memory — durable user facts & preferences]:\n" + "\n".join(mem_lines),
                })
        except Exception as mem_err:
            logger.debug("agent_memory injection skipped: %s", mem_err)

        for msg in db_messages:
            role = msg.get("role")
            content = msg.get("content") or ""
            is_summary = msg.get("is_summary", False)
            content_parts = msg.get("content_parts") or {}

            # System messages from the agent loop (tool outputs) are ephemeral context,
            # not conversational history — skip them to save tokens.
            # BUT: do NOT skip if it is a summary message.
            if role == "system" and not is_summary:
                continue

            # For summary messages, include them verbatim — they represent compacted history.
            if is_summary:
                formatted_messages.append({"role": role, "content": content})
                continue

            # Strip raw [Google Search Result for: ...] blocks from historical assistant messages.
            # These were only relevant at search time; re-sending them bloats the context window.
            if role == "assistant" and "[Google Search Result for:" in content:
                # Keep only the synthesised portion before the raw block
                content = content.split("[Google Search Result for:")[0].strip()

            # Also strip [Executed Tool: ...] annotation lines appended during agent loops
            if role == "assistant" and "[Executed Tool:" in content:
                content = content.split("[Executed Tool:")[0].strip()

            if content:  # Only include non-empty messages
                if role == "user" and isinstance(content_parts, dict) and content_parts.get("attachments"):
                    image_atts = [
                        att for att in content_parts.get("attachments", [])
                        if att.get("url") and (
                            att.get("mime_type", "").startswith("image/") or
                            os.path.splitext(att.get("filename", "").lower())[1]
                            in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".tiff", ".avif"}
                        )
                    ]
                    if image_atts:
                        multimodal_content = [{"type": "input_text", "text": content}]
                        for att in image_atts:
                            img_src = att.get("url", "")
                            try:
                                key = None
                                for marker in ["uploads/", "generated/"]:
                                    if marker in img_src:
                                        key = marker + img_src.split(marker, 1)[1]
                                        break
                                if key:
                                    b = await download_file_bytes(key, "UPLOADS")
                                    if b:
                                        b64 = base64.b64encode(b).decode("ascii")
                                        mime = att.get("mime_type") or "image/png"
                                        img_src = f"data:{mime};base64,{b64}"
                            except Exception:
                                pass
                            multimodal_content.append({
                                "type": "input_image",
                                "image_url": img_src,
                                "detail": "auto"
                            })
                        formatted_messages.append({"role": role, "content": multimodal_content})
                        continue

                formatted_messages.append({"role": role, "content": content})

        return formatted_messages
    except Exception as e:
        logger.error(f"Failed to build LLM context for conversation {conversation_id}: {e}")
        return []


async def compact_conversation_history(conversation_id: str) -> Optional[str]:
    """
    Checks if the conversation history needs compaction.
    If the active message count (non-summary, non-archived) exceeds 14,
    it compresses the older messages (retaining the last 6 turns active)
    into a concise summary and archives the original turns.
    Returns the summary text if compaction occurred, else None.
    """
    supabase = get_supabase_admin()
    try:
        # Fetch active messages
        def get_active():
            return (
                supabase.table("messages")
                .select("id, role, content, is_summary")
                .eq("conversation_id", conversation_id)
                .eq("is_archived_msg", False)
                .order("created_at", desc=False)
                .execute()
            )
        res = await asyncio.to_thread(get_active)
        messages = res.data or []
        
        # Count non-summary active messages
        active_count = sum(1 for m in messages if not m.get("is_summary"))
        if active_count <= 60:
            return None

        # Compact all messages up to the last 20 messages
        to_summarize = messages[:-20]
        if not to_summarize:
            return None

        logger.info(f"Compacting {len(to_summarize)} messages for conversation {conversation_id}")

        history_lines = []
        for msg in to_summarize:
            role = msg.get("role")
            content = msg.get("content") or ""
            if msg.get("is_summary"):
                history_lines.append(f"[Previous Summary of earlier turns]:\n{content}")
            else:
                history_lines.append(f"{role.upper()}: {content}")
        history_text = "\n\n".join(history_lines)

        # Call OpenAI to generate summary
        client = get_openai_client()
        deploy = (
            os.getenv("SOLVE_MODEL_DEPLOYMENT")
            or os.getenv("AZURE_OPENAI_SOLVE_DEPLOYMENT")
            or "gpt-5.6-luna"
        )
        
        system_prompt = (
            "You are a helpful assistant. Provide a highly robust, comprehensive 'Deep Briefing' of the conversation history so far. "
            "It must act as a detailed briefing document for a new developer agent taking over the session. "
            "Include:\n"
            "- Key Goal / Objective\n"
            "- Decisions made, design patterns chosen, and user preferences\n"
            "- Exact names/paths of files created, modified, or discussed\n"
            "- Core context facts and exact logic constraints\n"
            "Format the output as clear, structured markdown headers/points. Do NOT omit details or generalize."
        )

        az_response = await client.responses.create(
            model=deploy,
            input=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": history_text}
            ]
        )
        summary = (az_response.output_text or "").strip()
        if not summary:
            return None

        # Insert new summary message and archive old ones in database
        def persist_compaction():
            # 1. Insert summary message
            summary_msg = {
                "conversation_id": conversation_id,
                "role": "assistant",
                "is_summary": True,
                "content": f"Summary of earlier conversation:\n{summary}",
            }
            supabase.table("messages").insert(summary_msg).execute()

            # 2. Archive old messages
            ids_to_archive = [m["id"] for m in to_summarize]
            supabase.table("messages").update({"is_archived_msg": True}).in_("id", ids_to_archive).execute()

            # 3. Update last_compacted_at
            now_str = datetime.now(timezone.utc).isoformat()
            supabase.table("conversations").update({"last_compacted_at": now_str}).eq("id", conversation_id).execute()

        await asyncio.to_thread(persist_compaction)
        logger.info(f"Compaction complete for conversation {conversation_id}. Created summary: {summary}")
        return summary

    except Exception as e:
        logger.error(f"Failed to compact conversation history: {e}", exc_info=True)
        return None


def _is_effort_param_error(err_text: str) -> bool:
    """
    Detects API rejection of the reasoning effort parameter (400-class).
    Used for one-shot degradation: retry the request without the reasoning
    parameter instead of failing the whole turn.
    """
    t = (err_text or "").lower()
    return (
        "reasoning" in t
        or "effort" in t
        or "unknown parameter" in t
        or "unsupported parameter" in t
        or ("unrecognized" in t and "parameter" in t)
        or "invalid parameter" in t
    )


async def chat_stream_generator(
    messages: List[Dict[str, Any]],
    deployment: str,
    system_prompt: str,
    routing_mode: str,
    routing_reason: str,
    conversation_id: str,
    user_id: str,
    mode: str,
    estimated_tokens: int,
    previous_response_id: Optional[str] = None,
    user_timezone: Optional[str] = None,
    viewport: Optional[str] = None,  # "mobile" | "desktop" | None
    compaction_summary: Optional[str] = None,
    reasoning_effort: Optional[str] = None,  # GPT-5.6 reasoning effort tier
    complexity: Optional[str] = None,        # Rule-classified complexity tier
    workstation_access_enabled: bool = False,
    review_policy: Optional[str] = None,
):
    """
    Streams a response from the Azure OpenAI Responses API (ADR-002).

    Uses client.responses.stream() — the current-generation interface.
    Accepts `previous_response_id` for stateful multi-turn: when provided,
    Azure maintains conversation state server-side and only the new user
    message needs to be sent (no full message history resend).

    Emits SSE events:
      - routing_info:        model deployment and routing mode metadata
      - search_activity:     step-by-step status while Google search runs
      - image_gen_queued:    when AI decides to generate an image
      - content_block_delta: incremental text chunk
      - response_id:         the response ID to persist and pass on next turn
      - [DONE]:              stream termination signal
    """
    client = get_openai_client()

    # Emit routing metadata so frontend knows which model was used
    yield (
        "data: "
        + json.dumps({
            "type": "routing_info",
            "deployment": deployment,
            "routing_mode": routing_mode,
            "complexity": complexity,
            "reasoning_effort": reasoning_effort,
        })
        + "\n\n"
    )

    # Emit conversation_id so frontend knows the real UUID of the conversation
    yield (
        "data: "
        + json.dumps({
            "type": "conversation_id",
            "conversation_id": conversation_id,
        })
        + "\n\n"
    )

    if compaction_summary:
        yield (
            "data: "
            + json.dumps({
                "type": "context_compacted",
                "summary": compaction_summary,
            })
            + "\n\n"
        )

    try:
        # Skills module generates the full system prompt (identity + task skill).
        # Inject the current datetime/day-of-week context into the system prompt so the model is aware of the exact date and day.
        from zoneinfo import ZoneInfo
        from datetime import timedelta
        
        local_now = None
        tz_label = "WAT"
        if user_timezone:
            try:
                tz = ZoneInfo(user_timezone)
                local_now = datetime.now(tz)
                tz_label = user_timezone
            except Exception as tz_err:
                logger.warning(f"Failed to load user timezone '{user_timezone}': {tz_err}")
                
        if local_now is None:
            # Fallback to WAT (UTC+1)
            tz = timezone(timedelta(hours=1))
            local_now = datetime.now(tz)
            
        datetime_context = (
            f"\n\n[System Context: Current User Time is {local_now.strftime('%I:%M %p')}, "
            f"Date is {local_now.strftime('%A, %B %d, %Y')} ({tz_label}).\n"
            f"TEMPORAL CONFLICT MANDATE: The current calendar year is {local_now.year}. When evaluating web search results or real-time events, strictly prioritize documents timestamped {local_now.year} over historical data. Never confuse prior years or past seasons with current events.\n"
            f"FACTUAL DENSITY MANDATE: When synthesizing web search results, lead directly with verified facts, exact scores, metrics, names, and dates. Avoid excessive introductory summaries and conversational padding.]"
        )
        full_system = system_prompt + datetime_context
        if routing_mode in ("think", "solve"):
            full_system = full_system + _THINKING_INSTRUCTION
        # Agent mode carries the exclusive Ultra identity on top of the general
        # skill prompt (which already includes the general TASK_APPROACH).
        # NOTE: the router maps agent requests to think — gate on the request mode.
        if mode == "agent":
            from app.core.skills import ULTRA_IDENTITY
            full_system = full_system + "\n\n" + ULTRA_IDENTITY

        # ─── AGENT MODE AUTONOMOUS ORCHESTRATION ───────────────────────────
        if mode == "agent":
            from app.core.agent_task_models import AgentTask
            from app.core.agent_task_manager import AgentTaskManager
            from app.core.agent_config import get_agent_mode_config

            last_user_goal = ""
            if messages:
                for m in reversed(messages):
                    if m.get("role") == "user":
                        c = m.get("content", "")
                        if isinstance(c, str):
                            last_user_goal = c
                        elif isinstance(c, list):
                            last_user_goal = " ".join(
                                p.get("text", "") if isinstance(p, dict) else str(p)
                                for p in c
                                if not isinstance(p, dict) or p.get("type") in ("text", "input_text")
                            )
                        # Unwrap full pasted content body from between ``` fences if present
                        pasted_full = re.search(r"\[Pasted Content:[^\]]*\]\s*```(?:[a-zA-Z0-9_-]*\n)?([\s\S]*?)```", last_user_goal, flags=re.IGNORECASE)
                        if pasted_full:
                            prefix = last_user_goal[:pasted_full.start()].strip()
                            body = pasted_full.group(1).strip()
                            last_user_goal = f"{prefix} {body}".strip() if prefix else body
                        else:
                            pasted_single = re.search(r"\[Pasted Content:\s*([^\]]+)\]", last_user_goal, flags=re.IGNORECASE)
                            if pasted_single:
                                last_user_goal = pasted_single.group(1).strip()
                        break

            is_greeting = bool(re.match(
                r"^\s*(hello|hi|hey|good\s+(?:morning|afternoon|evening|day)|greetings|"
                r"who\s+are\s+you|what\s+can\s+you\s+do|how\s+are\s+you|help|thanks|thank\s+you|"
                r"sup|yo|testing|test)\b[!?.]*\s*$",
                (last_user_goal or "").strip(),
                re.IGNORECASE,
            ))

            # Only spin up autonomous multi-step orchestrator for non-greeting tasks
            if not is_greeting:
                agent_cfg = await get_agent_mode_config()
                if review_policy:
                    agent_cfg["review_policy"] = review_policy
                    if review_policy == "always_ask":
                        agent_cfg["auto_approve_level"] = "medium"
                    elif review_policy == "always_proceed":
                        agent_cfg["auto_approve_level"] = "high"
                if workstation_access_enabled:
                    agent_cfg["workstation_access_enabled"] = True
                task = AgentTask(
                    conversation_id=conversation_id,
                    user_id=user_id,
                    goal=last_user_goal or "Execute autonomous task",
                    max_duration_seconds=agent_cfg.get("max_duration_seconds", 300),
                )
                manager = AgentTaskManager(
                    task=task,
                    openai_client=client,
                    deployment=deployment,
                    nano_deployment=deployment,
                    config=agent_cfg,
                    supabase_client=get_supabase_admin(),
                )
                # Initialize plan and stream execution
                await manager.init_plan(history=messages[:-1] if len(messages) > 1 else None)
                async for sse_event in manager.execute_plan_stream(
                    search_fn=_perform_google_search,
                    deep_research_fn=_perform_parallel_searches,
                ):
                    yield sse_event

                yield "data: [DONE]\n\n"
                return

        # Pre-loop agent task planning for complex multi-step goals
        try:
            from app.core.agent_planner import generate_plan, format_plan_for_system_prompt
            last_user_msg = ""
            if messages:
                for m in reversed(messages):
                    if m.get("role") == "user":
                        c = m.get("content", "")
                        if isinstance(c, str):
                            last_user_msg = c
                        elif isinstance(c, list):
                            last_user_msg = " ".join(
                                p.get("text", "") if isinstance(p, dict) else str(p)
                                for p in c
                                if not isinstance(p, dict) or p.get("type") in ("text", "input_text")
                            )
                        break
            if last_user_msg:
                # ── Auto-Detect YouTube URLs & Pre-fetch Transcript Context ──
                try:
                    from app.services.youtube_intelligence import YouTubeIntelligence
                    if YouTubeIntelligence.contains_youtube_link(last_user_msg):
                        yield (
                            "data: "
                            + json.dumps({
                                "type": "search_activity",
                                "status": "searching",
                                "label": "Extracting YouTube video details & transcript...",
                            })
                            + "\n\n"
                        )
                        yt_res = await YouTubeIntelligence.process_youtube_url(last_user_msg)
                        if yt_res.get("success"):
                            full_system += f"\n\n[ATTACHED YOUTUBE VIDEO CONTEXT]:\n{yt_res.get('formatted_context', '')}\n"
                            yield (
                                "data: "
                                + json.dumps({
                                    "type": "search_activity",
                                    "status": "done",
                                    "label": f"Extracted transcript for '{yt_res.get('title', 'YouTube Video')}' ({yt_res.get('word_count', 0)} words)",
                                })
                                + "\n\n"
                            )
                except Exception as yt_err:
                    logger.warning("Auto YouTube transcript pre-fetch skipped: %s", yt_err)

                # ── Auto-Detect LinkedIn / Facebook Profile URLs ──
                try:
                    from app.services.handle_intelligence import HandleIntelligence
                    if "linkedin.com/in/" in last_user_msg or "facebook.com/" in last_user_msg:
                        platform = "linkedin" if "linkedin.com" in last_user_msg else "facebook"
                        yield (
                            "data: "
                            + json.dumps({
                                "type": "search_activity",
                                "status": "searching",
                                "label": f"Bypassing authwall & extracting {platform.capitalize()} profile...",
                            })
                            + "\n\n"
                        )
                        prof_res = await HandleIntelligence.lookup_profile(last_user_msg, platform=platform)
                        if prof_res.get("success"):
                            full_system += f"\n\n[VERIFIED {platform.upper()} PROFILE CONTEXT]:\n{prof_res.get('summary', '')}\n"
                            yield (
                                "data: "
                                + json.dumps({
                                    "type": "search_activity",
                                    "status": "done",
                                    "label": f"Extracted verified {platform.capitalize()} profile for {prof_res.get('name', 'User')}",
                                })
                                + "\n\n"
                            )
                except Exception as prof_err:
                    logger.warning("Auto profile lookup pre-fetch skipped: %s", prof_err)

                plan_text = await generate_plan(
                    user_message=last_user_msg,
                    conversation_history=messages[:-1] if len(messages) > 1 else None,
                    openai_client=client,
                    nano_deployment=deployment,
                )
                if plan_text:
                    full_system += format_plan_for_system_prompt(plan_text)
                    logger.info("Injected execution plan into system prompt for user message: %.60s", last_user_msg)
                    # Surface the plan in the UI (collapsible execution-plan block)
                    yield (
                        "data: "
                        + json.dumps({"type": "agent_plan", "plan": plan_text})
                        + "\n\n"
                    )
        except Exception as plan_err:
            logger.warning("Task planning skipped (non-fatal): %s", plan_err)

        # State tracking for thinking-block extraction
        thinking_buffer = ""
        in_thinking_block = False
        accumulated_thinking = ""
        accumulated_image_jobs = []
        accumulated_files = []

        # State tracking for thinking-block extraction and agent loop
        thinking_buffer = ""
        in_thinking_block = False
        accumulated_thinking = ""
        accumulated_image_jobs = []
        accumulated_files = []
        accumulated_widgets = []  # [{type, title, mode, code, widget_type}] — persisted to content_parts
        accumulated_display_cards = []  # [{card_type, payload, summary}] — Phase 6 display cards

        assistant_content = ""
        response_id = None
        prompt_tokens = 0
        completion_tokens = 0
        stream_failed = False
        error_message = ""

        # We construct a mutable copy of the messages for agent iterations
        local_messages = list(messages)
        iteration = 0
        from app.core.agent_config import get_max_iterations, get_max_output_tokens
        max_iterations = await get_max_iterations(routing_mode)
        # Phase 5: max_iterations == 0 means UNLIMITED steps (agent mode).
        # The wall-clock / error circuit breaker still applies; the step loop
        # uses a large sentinel so duration, not step count, is the ceiling.
        effective_max_iterations = max_iterations if max_iterations > 0 else 100000
        output_budget = await get_max_output_tokens(routing_mode)
        logger.info(
            "Agent loop budget: mode=%s iterations=%s output_tokens=%s",
            routing_mode,
            "unlimited" if max_iterations == 0 else max_iterations,
            "uncapped" if output_budget is None else output_budget,
        )
        circuit_breaker = create_turn_circuit_breaker(max_steps=effective_max_iterations)
        reflexion = create_reflexion_engine(max_attempts=max_iterations if max_iterations > 0 else 3)
        active_tool_step = 0

        while iteration < effective_max_iterations:
            current_tool_calls = []
            current_stream_failed = False
            current_error_message = ""
            
            try:
                circuit_breaker.record_step(f"Turn iteration {iteration + 1}")
            except Exception as cb_err:
                logger.warning(f"Circuit breaker budget threshold: {cb_err}")

            is_final_step = (iteration == effective_max_iterations - 1)
            
            from app.core.widget_tools import WIDGET_TOOLS
            stream_kwargs: Dict[str, Any] = {
                "model": deployment,
            }
            # Phase 5: when the budget is uncapped (None) omit the parameter
            # entirely so the model uses its full generation budget.
            if output_budget is not None:
                stream_kwargs["max_output_tokens"] = output_budget
            if reasoning_effort:
                # GPT-5.6 family: reasoning effort derived from the
                # rule-classified complexity tier (Responses API shape).
                stream_kwargs["reasoning"] = {"effort": reasoning_effort}
            # ── Phase 6: Category Gate — dynamic tool schema pruning ──────────
            # On iteration 0, classify intent and load ONLY the matching category
            # of tool schemas. Conversational turns ("none") pass tools=None,
            # eliminating schema tokens entirely. Mid-loop iterations always get
            # the full roster so the agent can use any tool freely.
            _last_user_content_for_gate = ""
            if messages:
                for _gm in reversed(messages):
                    if _gm.get("role") == "user":
                        _c = _gm.get("content", "")
                        _last_user_content_for_gate = _c if isinstance(_c, str) else " ".join(
                            p.get("text", "") if isinstance(p, dict) else str(p)
                            for p in _c
                            if isinstance(p, (str, dict))
                        )
                        break
            _gate_category, _gated_tools = _route_tools(
                _last_user_content_for_gate, AGENT_TOOLS, iteration=iteration, mode=mode
            )
            if is_final_step:
                # Final step: force tool_choice=none regardless of category
                stream_kwargs["tool_choice"] = "none"
                if _gated_tools:
                    stream_kwargs["tools"] = _gated_tools
            elif _gate_category == "none":
                # Pure conversational — skip tool schemas entirely
                stream_kwargs["tool_choice"] = "none"
            else:
                stream_kwargs["tools"] = _gated_tools
                stream_kwargs["tool_choice"] = "auto"

            # We use stateful multi-turn only on iteration 0 when previous_response_id is set
            if iteration == 0 and previous_response_id:
                stream_kwargs["previous_response_id"] = previous_response_id
                user_messages = [m for m in messages if m.get("role") == "user"]
                target_msgs = user_messages[-1:] if user_messages else messages
                stream_kwargs["input"] = [normalize_responses_message(m) for m in target_msgs]
            else:
                # Send full accumulated messages for loop turns
                raw_input_list = [{"role": "system", "content": full_system}] + local_messages
                stream_kwargs["input"] = [normalize_responses_message(m) for m in raw_input_list]

            try:
                async with client.responses.stream(**stream_kwargs) as stream:
                    try:
                        async for event in stream:
                            # 1. Text delta
                            if event.type == "response.output_text.delta":
                                chunk = event.delta
                                if in_thinking_block:
                                    thinking_buffer += chunk
                                    close_match = _THINK_CLOSE_RE.search(thinking_buffer)
                                    if close_match:
                                        thought_chunk = thinking_buffer[:close_match.start()]
                                        if thought_chunk:
                                            accumulated_thinking += thought_chunk
                                            yield (
                                                "data: "
                                                + json.dumps({"type": "thinking_delta", "delta": {"text": thought_chunk}})
                                                + "\n\n"
                                            )
                                        yield "data: " + json.dumps({"type": "thinking_done"}) + "\n\n"
                                        in_thinking_block = False
                                        after = thinking_buffer[close_match.end():].lstrip("\n")
                                        thinking_buffer = ""
                                        if after:
                                            assistant_content += after
                                            yield (
                                                "data: "
                                                + json.dumps({"type": "content_block_delta", "delta": {"text": after}})
                                                + "\n\n"
                                            )
                                    else:
                                        # Flush safe text while watching for partial closing tags like "</t"
                                        if "</" in thinking_buffer:
                                            partial_idx = thinking_buffer.rfind("</")
                                            safe_part = thinking_buffer[:partial_idx]
                                            thinking_buffer = thinking_buffer[partial_idx:]
                                            if safe_part:
                                                accumulated_thinking += safe_part
                                                yield (
                                                    "data: "
                                                    + json.dumps({"type": "thinking_delta", "delta": {"text": safe_part}})
                                                    + "\n\n"
                                                )
                                        else:
                                            accumulated_thinking += thinking_buffer
                                            yield (
                                                "data: "
                                                + json.dumps({"type": "thinking_delta", "delta": {"text": thinking_buffer}})
                                                + "\n\n"
                                            )
                                            thinking_buffer = ""
                                else:
                                    thinking_buffer += chunk
                                    open_match = _THINK_OPEN_RE.search(thinking_buffer)
                                    if open_match:
                                        before = thinking_buffer[:open_match.start()]
                                        if before:
                                            assistant_content += before
                                            yield (
                                                "data: "
                                                + json.dumps({"type": "content_block_delta", "delta": {"text": before}})
                                                + "\n\n"
                                            )
                                        yield "data: " + json.dumps({"type": "thinking_start"}) + "\n\n"
                                        in_thinking_block = True
                                        thinking_buffer = thinking_buffer[open_match.end():]
                                    else:
                                        if "<" in thinking_buffer:
                                            partial_idx = thinking_buffer.rfind("<")
                                            flush = thinking_buffer[:partial_idx]
                                            thinking_buffer = thinking_buffer[partial_idx:]
                                            if flush:
                                                assistant_content += flush
                                                yield (
                                                    "data: "
                                                    + json.dumps({"type": "content_block_delta", "delta": {"text": flush}})
                                                    + "\n\n"
                                                )
                                        else:
                                            assistant_content += thinking_buffer
                                            yield (
                                                "data: "
                                                + json.dumps({"type": "content_block_delta", "delta": {"text": thinking_buffer}})
                                                + "\n\n"
                                            )
                                            thinking_buffer = ""


                            # 2. Tool calls
                            elif event.type == "response.output_item.done":
                                item = getattr(event, "item", None)
                                if item is not None and getattr(item, "type", None) == "function_call":
                                    t_id = getattr(item, "id", None) or f"call_{len(current_tool_calls)}_{iteration}"
                                    t_name = getattr(item, "name", None)
                                    t_args = getattr(item, "arguments", "{}")
                                    current_tool_calls.append({
                                        "id": t_id,
                                        "name": t_name,
                                        "arguments": t_args
                                    })

                        # Flush any remaining buffer at the end of the stream
                        if thinking_buffer:
                            if in_thinking_block:
                                accumulated_thinking += thinking_buffer
                                yield (
                                    "data: "
                                    + json.dumps({"type": "thinking_delta", "delta": {"text": thinking_buffer}})
                                    + "\n\n"
                                )
                                yield "data: " + json.dumps({"type": "thinking_done"}) + "\n\n"
                                in_thinking_block = False
                            else:
                                assistant_content += thinking_buffer
                                yield (
                                    "data: "
                                    + json.dumps({"type": "content_block_delta", "delta": {"text": thinking_buffer}})
                                    + "\n\n"
                                )
                            thinking_buffer = ""
                    except Exception as iter_err:
                        # One-shot degradation: if the deployment rejects the
                        # reasoning effort parameter before producing anything,
                        # drop it and retry the same iteration without it.
                        _err_text = str(iter_err).lower()
                        if (
                            reasoning_effort
                            and not assistant_content
                            and not accumulated_thinking
                            and not current_tool_calls
                            and _is_effort_param_error(_err_text)
                        ):
                            logger.warning(
                                "Reasoning effort '%s' rejected by %s — retrying without the reasoning parameter: %s",
                                reasoning_effort, deployment, iter_err,
                            )
                            reasoning_effort = None
                            continue
                        current_stream_failed = True
                        current_error_message = str(iter_err)
                        logger.error(f"Error during stream iteration: {iter_err}")

                    # Check if the generated content contains an Azure content filter safety refusal
                    lower_content = assistant_content.lower()
                    refusal_indicators = [
                        "cannot assist with",
                        "cannot fulfill",
                        "i'm sorry, but i cannot",
                        "i am sorry, but i cannot",
                        "assist with that request",
                        "assist with this request"
                    ]
                    if any(indicator in lower_content for indicator in refusal_indicators):
                        logger.warning("Detected Azure OpenAI safety refusal in assistant content stream.")
                        current_stream_failed = True
                        current_error_message = "Content safety guardrails triggered."
                        # Strip the refusal message from the accumulated content to keep it clean
                        for indicator in refusal_indicators:
                            pos = lower_content.find(indicator)
                            if pos != -1:
                                sorry_pos = lower_content.find("i'm sorry")
                                if sorry_pos != -1:
                                    assistant_content = assistant_content[:sorry_pos].strip()
                                else:
                                    assistant_content = assistant_content[:pos].strip()
                                break

                    if not current_stream_failed:
                        try:
                            final_response = await stream.get_final_response()
                            response_id = final_response.id if final_response else None
                            if response_id:
                                yield (
                                    "data: "
                                    + json.dumps({"type": "response_id", "response_id": response_id})
                                    + "\n\n"
                                )
                            if final_response and hasattr(final_response, "usage") and final_response.usage:
                                prompt_tokens += getattr(final_response.usage, "prompt_tokens", 0) or 0
                                completion_tokens += getattr(final_response.usage, "completion_tokens", 0) or 0
                        except Exception as final_err:
                            logger.warning(f"Could not retrieve final response or tokens: {final_err}")
                            if not assistant_content and not current_tool_calls:
                                current_stream_failed = True
                                current_error_message = str(final_err)

            except Exception as stream_init_err:
                # One-shot degradation: a 400 rejecting the reasoning effort
                # parameter surfaces at stream init before any content — retry
                # the same iteration without the parameter.
                _err_text = str(stream_init_err).lower()
                if (
                    reasoning_effort
                    and not assistant_content
                    and not accumulated_thinking
                    and not current_tool_calls
                    and _is_effort_param_error(_err_text)
                ):
                    logger.warning(
                        "Reasoning effort '%s' rejected by %s at stream init — retrying without the reasoning parameter: %s",
                        reasoning_effort, deployment, stream_init_err,
                    )
                    reasoning_effort = None
                    continue
                current_stream_failed = True
                current_error_message = str(stream_init_err)
                logger.error(f"Error initializing stream: {stream_init_err}")

            if current_stream_failed:
                stream_failed = True
                error_message = current_error_message
                break

            # If the model generated tool calls, execute them and continue the loop!
            if current_tool_calls:
                # Add assistant message with tool calls to local history
                tool_calls_desc = "".join(
                    f"\n\n[Executed Tool: {tc['name']} with arguments: {tc['arguments']}]"
                    for tc in current_tool_calls
                )
                local_messages.append({
                    "role": "assistant",
                    "content": (assistant_content or "") + tool_calls_desc
                })

                # Execute all tool calls in this turn
                tool_outputs = []
                paused_for_user_input = False
                for tc in current_tool_calls:
                    t_name = tc["name"]
                    t_args_str = tc["arguments"]
                    
                    # Increment tool step counter and emit dynamic agent step event
                    active_tool_step += 1
                    expected_total_steps = max(len(current_tool_calls), active_tool_step)
                    step_label = f"Executing {t_name}..."

                    try:
                        args = json.loads(t_args_str or "{}")
                        if t_name == "search_web":
                            q = args.get("query", "")
                            step_label = f"Searching web for: {q}" if q else "Searching web for information..."
                        elif t_name == "fetch_url":
                            u = args.get("url", "")
                            step_label = f"Reading page: {u[:60]}" if u else "Reading web page..."
                        elif t_name == "youtube_transcript":
                            step_label = "Extracting YouTube video transcript & details..."
                        elif t_name == "lookup_handle":
                            step_label = "Looking up profile via Google Search Grounding..."
                        elif t_name == "memory_save":
                            step_label = "Saving to conversation memory..."
                        elif t_name == "memory_recall":
                            step_label = "Recalling conversation memory..."
                        elif t_name == "sandbox_ls":
                            step_label = "Listing sandbox files..."
                        elif t_name == "sandbox_read":
                            p = args.get("path", "")
                            step_label = f"Reading {p[:50]}" if p else "Reading sandbox file..."
                        elif t_name == "sandbox_write":
                            p = args.get("path", "")
                            step_label = f"Writing {p[:50]}" if p else "Writing sandbox file..."
                        elif t_name == "sandbox_edit":
                            p = args.get("path", "")
                            step_label = f"Editing {p[:50]}" if p else "Editing sandbox file..."
                        elif t_name == "memory_edit":
                            k = args.get("key", "")
                            step_label = f"Patching memory '{k[:30]}'..." if k else "Patching memory..."
                        elif t_name == "execute_code":
                            code_text = args.get("code", "").lower()
                            if any(kw in code_text for kw in ["fitz", "pdf", "docx", "signature", "document"]):
                                step_label = "Extracting document graphics & updating signatory..."
                            elif any(kw in code_text for kw in ["plot", "matplotlib", "df", "pandas"]):
                                step_label = "Processing data & generating chart..."
                            else:
                                step_label = "Running Python code in sandbox..."
                        elif t_name == "generate_image":
                            step_label = "Synthesizing image with FLUX..."
                        elif t_name == "fetch_stock_image":
                            step_label = "Searching stock photos..."
                        elif t_name == "terminal":
                            cmd = args.get("command", "")
                            step_label = f"Running terminal: {cmd[:50]}" if cmd else "Running terminal command..."
                        elif t_name == "weather_fetch":
                            loc = args.get("location", "")
                            step_label = f"Checking weather for {loc[:40]}..." if loc else "Checking weather..."
                        elif t_name == "ask_user_input":
                            step_label = "Requesting user input options..."
                        elif t_name == "end_conversation":
                            step_label = "Ending conversation..."
                        elif t_name.startswith("render_"):
                            step_label = f"Displaying {t_name.replace('render_', '').replace('_', ' ')}..."
                    except Exception:
                        pass

                    yield (
                        "data: "
                        + json.dumps({
                            "type": "agent_step",
                            "step": active_tool_step,
                            "max_steps": expected_total_steps,
                            "label": step_label,
                        })
                        + "\n\n"
                    )

                    if t_name == "search_web":
                        try:
                            args = json.loads(t_args_str or "{}")
                            query = args.get("query", "")
                            if query:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Searching the web for: {query}",
                                    })
                                    + "\n\n"
                                )
                                search_result = await _perform_google_search(
                                    query,
                                    synthesis_deployment=deployment,
                                    history=local_messages,
                                    return_raw=True,
                                )
                                sources = search_result.get("sources", [])
                                google_context = search_result.get("google_context", "")

                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "done",
                                        "label": f"Found {len(sources)} source(s)",
                                        "sources": sources,
                                    })
                                    + "\n\n"
                                )
                                # Cap raw search context injected into local loop history.
                                # Full context is still used for this turn's synthesis,
                                # but we store a condensed version to avoid token bloat on
                                # subsequent iterations. The sources list is always complete.
                                _MAX_SEARCH_CTX = 8000
                                if len(google_context) > _MAX_SEARCH_CTX:
                                    truncated_ctx = google_context[:_MAX_SEARCH_CTX]
                                    # Trim to last complete sentence/line boundary
                                    last_nl = truncated_ctx.rfind('\n')
                                    if last_nl > 1000:
                                        truncated_ctx = truncated_ctx[:last_nl]
                                    google_context_for_history = (
                                        truncated_ctx
                                        + f"\n\n[... search result truncated for context efficiency — "
                                        f"{len(sources)} source(s) retrieved in total ...]"
                                    )
                                else:
                                    google_context_for_history = google_context

                                tool_outputs.append(google_context_for_history)
                            else:
                                tool_outputs.append("Search query was empty.")
                        except Exception as e:
                            logger.error(f"Agent search_web failed: {e}")
                            tool_outputs.append(f"Web search error: {str(e)}")

                    elif t_name == "deep_research":
                        try:
                            args = json.loads(t_args_str or "{}")
                            sub_queries: List[str] = args.get("queries", [])
                            if sub_queries:
                                # Emit one search_activity event per sub-query so UI shows progress
                                for q in sub_queries:
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "search_activity",
                                            "status": "searching",
                                            "label": f"Researching: {q}",
                                        })
                                        + "\n\n"
                                    )

                                research_result = await _perform_parallel_searches(
                                    sub_queries,
                                    deployment=deployment,
                                    history=local_messages,
                                )
                                merged_ctx = research_result.get("merged_context", "")
                                all_sources = research_result.get("sources", [])
                                q_count = research_result.get("query_count", 0)

                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "done",
                                        "label": f"Deep research complete — {q_count}/{len(sub_queries)} queries succeeded, {len(all_sources)} source(s)",
                                        "sources": all_sources,
                                    })
                                    + "\n\n"
                                )

                                # Cap merged context for history injection (larger budget than single search)
                                _MAX_RESEARCH_CTX = 12000
                                if len(merged_ctx) > _MAX_RESEARCH_CTX:
                                    truncated = merged_ctx[:_MAX_RESEARCH_CTX]
                                    last_nl = truncated.rfind("\n")
                                    if last_nl > 4000:
                                        truncated = truncated[:last_nl]
                                    merged_ctx_for_history = (
                                        truncated
                                        + f"\n\n[... research context truncated — "
                                        f"{q_count} queries, {len(all_sources)} sources total ...]"
                                    )
                                else:
                                    merged_ctx_for_history = merged_ctx

                                tool_outputs.append(merged_ctx_for_history)
                            else:
                                tool_outputs.append("deep_research: queries list was empty.")
                        except Exception as e:
                            logger.error(f"Agent deep_research failed: {e}")
                            tool_outputs.append(f"Deep research error: {str(e)}")

                    elif t_name == "fetch_url":
                        try:
                            args = json.loads(t_args_str or "{}")
                            target_url = args.get("url", "")
                            if target_url:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Reading page: {target_url[:80]}",
                                    })
                                    + "\n\n"
                                )
                                page_text = await _perform_fetch_url(target_url)
                                tool_outputs.append(page_text)
                            else:
                                tool_outputs.append("fetch_url error: no URL provided.")
                        except Exception as e:
                            logger.error(f"Agent fetch_url failed: {e}")
                            tool_outputs.append(f"fetch_url error: {str(e)}")

                    elif t_name == "youtube_transcript":
                        try:
                            args = json.loads(t_args_str or "{}")
                            url_or_id = args.get("url_or_id") or args.get("url") or ""
                            if url_or_id:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": "Extracting YouTube video details & transcript...",
                                    })
                                    + "\n\n"
                                )
                                from app.services.youtube_intelligence import YouTubeIntelligence
                                yt_res = await YouTubeIntelligence.process_youtube_url(url_or_id)
                                if yt_res.get("success"):
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "search_activity",
                                            "status": "done",
                                            "label": f"Extracted transcript for '{yt_res.get('title', 'YouTube Video')}' ({yt_res.get('word_count', 0)} words)",
                                        })
                                        + "\n\n"
                                    )
                                    tool_outputs.append(yt_res.get("formatted_context", ""))
                                else:
                                    tool_outputs.append(f"youtube_transcript error: {yt_res.get('error', 'Could not retrieve video transcript')}")
                            else:
                                tool_outputs.append("youtube_transcript error: url_or_id is required.")
                        except Exception as e:
                            logger.error(f"Agent youtube_transcript failed: {e}")
                            tool_outputs.append(f"youtube_transcript error: {str(e)}")

                    elif t_name == "lookup_handle":
                        try:
                            args = json.loads(t_args_str or "{}")
                            handle_or_url = args.get("handle_or_url") or args.get("handle") or ""
                            plat = args.get("platform", "auto")
                            if handle_or_url:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Looking up profile for: {handle_or_url[:60]}",
                                    })
                                    + "\n\n"
                                )
                                from app.services.handle_intelligence import HandleIntelligence
                                prof_res = await HandleIntelligence.lookup_profile(handle_or_url, platform=plat)
                                if prof_res.get("success"):
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "search_activity",
                                            "status": "done",
                                            "label": f"Retrieved profile on {prof_res.get('platform', plat).capitalize()}",
                                        })
                                        + "\n\n"
                                    )
                                    tool_outputs.append(prof_res.get("summary", ""))
                                else:
                                    tool_outputs.append(f"lookup_handle error: {prof_res.get('error', 'Could not retrieve profile')}")
                            else:
                                tool_outputs.append("lookup_handle error: handle_or_url is required.")
                        except Exception as e:
                            logger.error(f"Agent lookup_handle failed: {e}")
                            tool_outputs.append(f"lookup_handle error: {str(e)}")

                    elif t_name == "memory_save":
                        try:
                            args = json.loads(t_args_str or "{}")
                            mem_key = (args.get("key", "") or "").strip()[:80]
                            mem_value = (args.get("value", "") or "").strip()[:500]
                            if_version = args.get("if_version")  # optional int
                            if mem_key and mem_value:
                                # ── Privacy gate (deterministic, not prompt-based) ──
                                is_clean, pii_reason = check_pii(mem_key, mem_value)
                                if not is_clean:
                                    tool_outputs.append(f"memory_save blocked: {pii_reason}")
                                else:
                                    def _save_memory():
                                        current = (
                                            supabase.table("conversations")
                                            .select("agent_memory")
                                            .eq("id", conversation_id)
                                            .single()
                                            .execute()
                                        )
                                        mem = (current.data or {}).get("agent_memory") or {}
                                        if not isinstance(mem, dict):
                                            mem = {}
                                        # ── Optimistic concurrency check ──
                                        if if_version is not None:
                                            entry = mem.get(mem_key)
                                            current_version = 0
                                            if isinstance(entry, dict):
                                                current_version = entry.get("_version", 0)
                                            if current_version != if_version:
                                                # Return conflict descriptor for in-loop merge
                                                current_val = entry.get("value", "") if isinstance(entry, dict) else str(entry or "")
                                                return describe_memory_version_conflict(
                                                    mem_key, if_version, current_version, current_val
                                                )
                                        # Resolve current version and bump
                                        existing = mem.get(mem_key)
                                        prev_version = 0
                                        if isinstance(existing, dict):
                                            prev_version = existing.get("_version", 0)
                                        mem[mem_key] = {"value": mem_value, "_version": prev_version + 1}
                                        supabase.table("conversations").update(
                                            {"agent_memory": mem}
                                        ).eq("id", conversation_id).execute()
                                        return mem
                                    result = await asyncio.to_thread(_save_memory)
                                    if isinstance(result, dict) and result.get("conflict"):
                                        tool_outputs.append(
                                            f"memory_save conflict: {json.dumps(result)}"
                                        )
                                    else:
                                        tool_outputs.append(f"Memory saved: '{mem_key}' = {mem_value}")
                            else:
                                tool_outputs.append("memory_save error: both key and value are required.")
                        except Exception as e:
                            logger.error(f"Agent memory_save failed: {e}")
                            tool_outputs.append(f"memory_save error: {str(e)}")

                    elif t_name == "memory_recall":
                        try:
                            args = json.loads(t_args_str or "{}")
                            mem_key = (args.get("key", "") or "").strip()

                            def _recall_memory():
                                row = (
                                    supabase.table("conversations")
                                    .select("agent_memory")
                                    .eq("id", conversation_id)
                                    .single()
                                    .execute()
                                )
                                return (row.data or {}).get("agent_memory") or {}

                            mem = await asyncio.to_thread(_recall_memory)
                            if not isinstance(mem, dict) or not mem:
                                tool_outputs.append(
                                    "No memories saved for this conversation yet. "
                                    "Use memory_save to persist durable user facts and preferences."
                                )
                            elif mem_key:
                                tool_outputs.append(
                                    f"Memory '{mem_key}': {mem.get(mem_key, '(not found)')}"
                                )
                            else:
                                lines = [f"- {k}: {v}" for k, v in mem.items()]
                                tool_outputs.append("Saved memories:\n" + "\n".join(lines))
                        except Exception as e:
                            logger.error(f"Agent memory_recall failed: {e}")
                            tool_outputs.append(f"memory_recall error: {str(e)}")

                    elif t_name == "memory_edit":
                        try:
                            args = json.loads(t_args_str or "{}")
                            mem_key = (args.get("key", "") or "").strip()[:80]
                            old_str = args.get("old_str", "")
                            new_str = (args.get("new_str", "") or "").strip()[:500]
                            if_version = args.get("if_version")
                            if not mem_key or not old_str:
                                tool_outputs.append("memory_edit error: key and old_str are required.")
                            else:
                                # PII gate on new_str
                                is_clean, pii_reason = check_pii(mem_key, new_str)
                                if not is_clean:
                                    tool_outputs.append(f"memory_edit blocked: {pii_reason}")
                                else:
                                    def _edit_memory():
                                        current = (
                                            supabase.table("conversations")
                                            .select("agent_memory")
                                            .eq("id", conversation_id)
                                            .single()
                                            .execute()
                                        )
                                        mem = (current.data or {}).get("agent_memory") or {}
                                        if not isinstance(mem, dict):
                                            return {"error": "No memory store found."}
                                        entry = mem.get(mem_key)
                                        if entry is None:
                                            return {"error": f"Key '{mem_key}' not found in memory."}
                                        # Support both versioned dict and plain string storage
                                        if isinstance(entry, dict):
                                            current_version = entry.get("_version", 0)
                                            current_value = entry.get("value", "")
                                        else:
                                            current_version = 0
                                            current_value = str(entry)
                                        # Optimistic concurrency check
                                        if if_version is not None and current_version != if_version:
                                            return describe_memory_version_conflict(
                                                mem_key, if_version, current_version, current_value
                                            )
                                        # Apply surgical edit
                                        success, patched = apply_memory_edit(current_value, old_str, new_str)
                                        if not success:
                                            return {"error": patched}
                                        mem[mem_key] = {"value": patched, "_version": current_version + 1}
                                        supabase.table("conversations").update(
                                            {"agent_memory": mem}
                                        ).eq("id", conversation_id).execute()
                                        return {"success": True, "key": mem_key, "new_value": patched}
                                    result = await asyncio.to_thread(_edit_memory)
                                    if result.get("conflict"):
                                        tool_outputs.append(f"memory_edit conflict: {json.dumps(result)}")
                                    elif result.get("error"):
                                        tool_outputs.append(f"memory_edit error: {result['error']}")
                                    else:
                                        tool_outputs.append(
                                            f"Memory '{mem_key}' patched: '{old_str}' → '{new_str}'"
                                        )
                        except Exception as e:
                            logger.error(f"Agent memory_edit failed: {e}")
                            tool_outputs.append(f"memory_edit error: {str(e)}")

                    elif t_name == "sandbox_ls":
                        try:
                            from app.services.code_sandbox import sandbox_list_files
                            args = json.loads(t_args_str or "{}")
                            listing = await sandbox_list_files(conversation_id, (args.get("subpath", "") or "").strip())
                            tool_outputs.append(listing)
                        except Exception as e:
                            logger.error(f"Agent sandbox_ls failed: {e}")
                            tool_outputs.append(f"sandbox_ls error: {str(e)}")

                    elif t_name == "sandbox_read":
                        try:
                            from app.services.code_sandbox import sandbox_read_file
                            args = json.loads(t_args_str or "{}")
                            target = (args.get("path", "") or "").strip()
                            if target:
                                content = await sandbox_read_file(
                                    conversation_id,
                                    target,
                                    offset=int(args.get("offset", 0) or 0),
                                    max_bytes=int(args.get("max_bytes", 4000) or 4000),
                                )
                                tool_outputs.append(content)
                            else:
                                tool_outputs.append("sandbox_read error: 'path' is required.")
                        except Exception as e:
                            logger.error(f"Agent sandbox_read failed: {e}")
                            tool_outputs.append(f"sandbox_read error: {str(e)}")

                    elif t_name == "sandbox_write":
                        try:
                            from app.services.code_sandbox import sandbox_write_file, _resolve_sandbox_path
                            args = json.loads(t_args_str or "{}")
                            target = (args.get("path", "") or "").strip()
                            content = args.get("content", "")
                            if target and content:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Writing file: {target[:80]}",
                                    })
                                    + "\n\n"
                                )
                                receipt = await sandbox_write_file(conversation_id, target, content)
                                # Upload to R2 so the user gets a downloadable artifact card.
                                # Preserve the sandbox-relative path so multi-file
                                # projects keep working relative links on the CDN.
                                try:
                                    from app.services.code_sandbox import _resolve_sandbox_path
                                    import mimetypes
                                    full_path = _resolve_sandbox_path(conversation_id, target)
                                    rel_upload = os.path.relpath(full_path, _resolve_sandbox_path(conversation_id)).replace("\\", "/")
                                    mime = mimetypes.guess_type(full_path)[0] or "text/plain"
                                    with open(full_path, "rb") as fh:
                                        data = fh.read()
                                    r2_url = await _upload_generated_file(
                                        file_bytes=data,
                                        filename=rel_upload,
                                        mime_type=mime,
                                        conversation_id=conversation_id,
                                        user_id=user_id,
                                    )
                                    accumulated_files.append({
                                        "filename": rel_upload,
                                        "download_url": r2_url,
                                        "size_bytes": len(data),
                                    })
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "generated_files",
                                            "files": [accumulated_files[-1]],
                                        })
                                        + "\n\n"
                                    )
                                except Exception as up_err:
                                    logger.warning(f"sandbox_write R2 upload skipped: {up_err}")
                                tool_outputs.append(receipt)
                            else:
                                tool_outputs.append("sandbox_write error: both 'path' and 'content' are required.")
                        except Exception as e:
                            logger.error(f"Agent sandbox_write failed: {e}")
                            tool_outputs.append(f"sandbox_write error: {str(e)}")

                    elif t_name == "sandbox_edit":
                        try:
                            from app.services.code_sandbox import sandbox_edit_file, _resolve_sandbox_path
                            args = json.loads(t_args_str or "{}")
                            target = (args.get("path", "") or "").strip()
                            old_str = args.get("old_str", "")
                            new_str = args.get("new_str", "")
                            if target and old_str:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Updating file: {target[:80]}",
                                    })
                                    + "\n\n"
                                )
                                receipt = await sandbox_edit_file(conversation_id, target, old_str, new_str)
                                # Upload to R2 so the user gets a downloadable artifact card and working preview link.
                                try:
                                    import mimetypes
                                    full_path = _resolve_sandbox_path(conversation_id, target)
                                    rel_upload = os.path.relpath(full_path, _resolve_sandbox_path(conversation_id)).replace("\\", "/")
                                    mime = mimetypes.guess_type(full_path)[0] or "text/plain"
                                    with open(full_path, "rb") as fh:
                                        data = fh.read()
                                    r2_url = await _upload_generated_file(
                                        file_bytes=data,
                                        filename=rel_upload,
                                        mime_type=mime,
                                        conversation_id=conversation_id,
                                        user_id=user_id,
                                    )
                                    accumulated_files.append({
                                        "filename": rel_upload,
                                        "download_url": r2_url,
                                        "size_bytes": len(data),
                                    })
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "generated_files",
                                            "files": [accumulated_files[-1]],
                                        })
                                        + "\n\n"
                                    )
                                except Exception as up_err:
                                    logger.warning(f"sandbox_edit R2 upload skipped: {up_err}")
                                tool_outputs.append(receipt)
                            else:
                                tool_outputs.append("sandbox_edit error: both 'path' and 'old_str' are required.")
                        except Exception as e:
                            logger.error(f"Agent sandbox_edit failed: {e}")
                            tool_outputs.append(f"sandbox_edit error: {str(e)}")

                    elif t_name == "execute_code":
                        try:
                            from app.services.code_sandbox import execute_code_in_sandbox
                            args = json.loads(t_args_str or "{}")
                            code_str = args.get("code", "")
                            lang_str = args.get("language", "python")
                            if code_str:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Running {lang_str} code...",
                                    })
                                    + "\n\n"
                                )
                                exec_output, exec_files = await execute_code_in_sandbox(
                                    code=code_str,
                                    language=lang_str,
                                    conversation_id=conversation_id,
                                    user_id=user_id,
                                    timeout_seconds=60,
                                )
                                if exec_files:
                                    accumulated_files.extend(exec_files)
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "generated_files",
                                            "files": exec_files,
                                        })
                                        + "\n\n"
                                    )
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "done",
                                        "label": "Code execution complete.",
                                    })
                                    + "\n\n"
                                )
                # Artifact isolation: cap persisted stdout so huge
                                # dumps never ride into the next model call. The
                                # model can inspect files on demand via sandbox_read.
                                _HEAD, _TAIL = 4000, 1000
                                if len(exec_output) > _HEAD + _TAIL + 64:
                                    capped = (
                                        exec_output[:_HEAD]
                                        + f"\n[... {len(exec_output) - _HEAD - _TAIL} chars truncated — use sandbox_ls / sandbox_read to inspect files ...]\n"
                                        + exec_output[-_TAIL:]
                                    )
                                else:
                                    capped = exec_output
                                tool_outputs.append(f"Code execution stdout/stderr:\n{capped}")
                                # Reflexion: on execution failure, inject a self-correction
                                # directive so the next iteration changes approach.
                                if any(sig in exec_output.lower() for sig in ("traceback", "error", "exception", "not found", "cannot")):
                                    try:
                                        trial = reflexion.record_trial(f"execute_code: {code_str[:120]}", exec_output[:500])
                                        tool_outputs.append(f"[Self-correction] {trial.self_critique}")
                                    except Exception as ref_err:
                                        logger.debug("reflexion skip: %s", ref_err)
                            else:
                                tool_outputs.append("Code snippet was empty.")
                        except Exception as e:
                            logger.error(f"Agent execute_code failed: {e}")
                            tool_outputs.append(f"Code sandbox error: {str(e)}")

                    elif t_name == "generate_image":
                        try:
                            args = json.loads(t_args_str or "{}")
                            img_prompt = args.get("prompt", "")
                            img_style = args.get("style", "photorealistic")
                            if img_prompt:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": "Generating image with FLUX...",
                                    })
                                    + "\n\n"
                                )
                                job_id = await _enqueue_image_gen(
                                    user_id, conversation_id, img_prompt, img_style
                                )
                                accumulated_image_jobs.append({
                                    "job_id": job_id,
                                    "prompt": img_prompt,
                                    "status": "pending"
                                })
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "image_gen_queued",
                                        "job_id": job_id,
                                        "prompt": img_prompt,
                                    })
                                    + "\n\n"
                                )
                                tool_outputs.append(f"Image generation job queued successfully with ID: {job_id}.")
                            else:
                                tool_outputs.append("Image prompt was empty.")
                        except Exception as err:
                            tool_outputs.append(f"Image generation error: {err}")

                    elif t_name == "fetch_stock_image":
                        try:
                            args = json.loads(t_args_str or "{}")
                            stock_query = str(args.get("query") or "").strip()
                            if stock_query:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Searching stock photos: {stock_query[:50]}...",
                                    })
                                    + "\n\n"
                                )
                                from app.services.pexels_service import get_stock_service, PexelsService
                                stock = await get_stock_service()
                                stock_result = await stock.search(
                                    stock_query,
                                    per_page=int(args.get("per_page") or 6),
                                    orientation=args.get("orientation"),
                                )
                                tool_outputs.append(PexelsService.format_for_model(stock_result, stock_query))
                            else:
                                tool_outputs.append("fetch_stock_image error: no query provided.")
                        except Exception as e:
                            logger.error(f"Agent fetch_stock_image failed: {e}")
                            tool_outputs.append(f"fetch_stock_image error: {str(e)}")

                    elif t_name == "terminal":
                        try:
                            from app.core.agent_config import get_terminal_timeout
                            from app.services.code_sandbox import execute_code_in_sandbox
                            args = json.loads(t_args_str or "{}")
                            terminal_cmd = str(args.get("command") or "").strip()
                            if terminal_cmd:
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "search_activity",
                                        "status": "searching",
                                        "label": f"Running terminal: {terminal_cmd[:60]}...",
                                    })
                                    + "\n\n"
                                )
                                term_output, term_files = await execute_code_in_sandbox(
                                    code=terminal_cmd,
                                    language="bash",
                                    conversation_id=conversation_id,
                                    user_id=user_id,
                                    timeout_seconds=await get_terminal_timeout(),
                                )
                                if term_files:
                                    accumulated_files.extend(term_files)
                                    yield (
                                        "data: "
                                        + json.dumps({"type": "generated_files", "files": term_files})
                                        + "\n\n"
                                    )
                                _T_HEAD, _T_TAIL = 4000, 1000
                                if len(term_output) > _T_HEAD + _T_TAIL + 64:
                                    term_capped = (
                                        term_output[:_T_HEAD]
                                        + f"\n[... {len(term_output) - _T_HEAD - _T_TAIL} chars truncated — use sandbox_ls / sandbox_read to inspect files ...]\n"
                                        + term_output[-_T_TAIL:]
                                    )
                                else:
                                    term_capped = term_output
                                tool_outputs.append(f"Terminal output:\n{term_capped}")
                                # Reflexion on build failures (same channel as execute_code).
                                if any(sig in term_output.lower() for sig in ("error", "not found", "cannot", "failed")):
                                    try:
                                        trial = reflexion.record_trial(f"terminal: {terminal_cmd[:120]}", term_output[:500])
                                        tool_outputs.append(f"[Self-correction] {trial.self_critique}")
                                    except Exception as ref_err:
                                        logger.debug("reflexion skip: %s", ref_err)
                            else:
                                tool_outputs.append("terminal error: no command provided.")
                        except Exception as e:
                            logger.error(f"Agent terminal failed: {e}")
                            tool_outputs.append(f"terminal error: {str(e)}")

                    elif t_name == "visualize__read_me":
                        # Returns design tokens + module rules as a tool result.
                        # No SSE event — this is purely context injection for the model.
                        try:
                            from app.core.widget_tools import get_read_me_result
                            args = json.loads(t_args_str or "{}")
                            modules = args.get("modules", ["diagram"])
                            # Model passes platform; if "unknown", use the viewport hint from the request
                            platform = args.get("platform", "desktop")
                            if platform == "unknown" and viewport == "mobile":
                                platform = "mobile"
                            elif platform == "unknown":
                                platform = "desktop"
                            result_text = get_read_me_result(modules, platform)
                            tool_outputs.append(result_text)
                            logger.info("visualize__read_me: loaded modules=%s platform=%s", modules, platform)
                        except Exception as e:
                            logger.error(f"visualize__read_me failed: {e}")
                            tool_outputs.append(f"Design token load error: {str(e)}")

                    elif t_name == "visualize__show_widget":
                        try:
                            args = json.loads(t_args_str or "{}")
                            w_code = args.get("widget_code", "")
                            w_title = args.get("title", "ochuko_widget")
                            w_msgs = args.get("loading_messages", ["Assembling visual..."])
                            w_type = args.get("widget_type", "diagram")

                            # §5 security: rate-limit to max 3 widget renders per turn
                            widget_render_count = sum(
                                1 for tc in current_tool_calls if tc.get("name") == "visualize__show_widget"
                            )
                            if widget_render_count > 3:
                                tool_outputs.append(
                                    "Widget render limit reached (max 3 per turn). "
                                    "Summarise remaining visuals in prose."
                                )
                            elif w_code and w_code.strip():
                                # Signal loading state to frontend BEFORE the full payload
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "widget_loading",
                                        "title": w_title,
                                        "loading_messages": w_msgs,
                                        "widget_type": w_type,
                                    })
                                    + "\n\n"
                                )
                                # Emit the full widget payload for rendering
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "widget",
                                        "code": w_code,
                                        "title": w_title,
                                        "loading_messages": w_msgs,
                                        "widget_type": w_type,
                                    })
                                    + "\n\n"
                                )
                                is_svg = w_code.strip().startswith("<svg")
                                tool_outputs.append(
                                    f"Widget '{w_title}' rendered successfully in "
                                    f"{'SVG' if is_svg else 'HTML'} mode on client UI."
                                )
                                # Accumulate for §8.4 persistence
                                accumulated_widgets.append({
                                    "type": "widget",
                                    "title": w_title,
                                    "mode": "svg" if is_svg else "html",
                                    "code": w_code,
                                    "widget_type": w_type,
                                })
                            else:
                                tool_outputs.append(
                                    f"Widget '{w_title}' had empty code. "
                                    "Ensure visualize__read_me was called first and the code is complete."
                                )
                        except Exception as e:
                            logger.error(f"Agent visualize__show_widget failed: {e}")
                            tool_outputs.append(f"Widget render error: {str(e)}")

                    elif t_name in (
                        "render_options_card", "render_step_flow", "render_itinerary",
                        "render_map", "render_quiz", "render_translation", "render_sports_card",
                    ):
                        try:
                            args = json.loads(t_args_str or "{}")
                            # Phase 6 §4: schema verification gate
                            card_ok, card_err = verification_gates.verify_render_card_schema(t_name, args)
                            if not card_ok:
                                tool_outputs.append(f"{t_name} schema error: {card_err}")
                            else:
                                # Emit SSE display_card event — frontend renders native UI component
                                card_summary = (
                                    args.get("summary")
                                    or args.get("title")
                                    or (f"{args.get('home_team')} {args.get('home_score')} - {args.get('away_score')} {args.get('away_team')}" if t_name == "render_sports_card" else t_name)
                                )
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "display_card",
                                        "card_type": t_name,
                                        "payload": args,
                                        "summary": card_summary,
                                    })
                                    + "\n\n"
                                )
                                tool_outputs.append(
                                    f"Display card '{t_name}' rendered on client. "
                                    "Do NOT re-list its content in prose — add one takeaway sentence only."
                                )
                                # Persist in message content_parts for conversation history
                                accumulated_display_cards.append({
                                    "card_type": t_name,
                                    "payload": args,
                                    "summary": card_summary,
                                })
                        except Exception as e:
                            logger.error(f"Agent {t_name} failed: {e}")
                            tool_outputs.append(f"{t_name} error: {str(e)}")

                    elif t_name == "present_deliverable":
                        try:
                            args = json.loads(t_args_str or "{}")
                            p_name = args.get("project_name") or args.get("title") or "Project Deliverable"
                            p_entry = args.get("entry_file") or "index.html"
                            p_files = args.get("files") or []

                            from app.services.code_sandbox import get_or_create_sandbox_workspace, _upload_generated_file
                            from app.services.google_drive import upload_to_google_drive
                            import zipfile

                            workspace_root, src_dir, data_dir = get_or_create_sandbox_workspace(conversation_id)
                            presented_items = []

                            candidate_files = []
                            if p_files and isinstance(p_files, list):
                                for pf in p_files:
                                    fname = pf if isinstance(pf, str) else (pf.get("filename", "") if isinstance(pf, dict) else "")
                                    if fname:
                                        candidate_files.append(fname.replace("\\", "/").strip("/"))
                            elif os.path.exists(data_dir):
                                for r, d, fs in os.walk(data_dir):
                                    d[:] = [x for x in d if x not in (".git", "node_modules", ".venv", "__pycache__")]
                                    for f in fs:
                                        if f not in ("script.py", "script.js", "command.sh", "project.zip"):
                                            candidate_files.append(os.path.relpath(os.path.join(r, f), data_dir).replace("\\", "/"))

                            for rel_f in candidate_files:
                                full_p = os.path.join(data_dir, rel_f)
                                if os.path.exists(full_p) and os.path.isfile(full_p):
                                    try:
                                        with open(full_p, "rb") as f_in:
                                            b_data = f_in.read()
                                        mime_t, _ = mimetypes.guess_type(rel_f)
                                        f_url = await _upload_generated_file(
                                            file_bytes=b_data,
                                            filename=rel_f,
                                            mime_type=mime_t or "application/octet-stream",
                                            conversation_id=conversation_id,
                                            user_id=user_id,
                                        )
                                        presented_items.append({
                                            "filename": rel_f,
                                            "download_url": f_url,
                                            "size_bytes": len(b_data),
                                        })
                                    except Exception as up_err:
                                        logger.warning(f"Failed to upload {rel_f} for present_deliverable: {up_err}")

                            # Build project.zip if multiple files exist
                            if len(candidate_files) > 1 and os.path.exists(data_dir):
                                try:
                                    import io as _io
                                    z_buf = _io.BytesIO()
                                    with zipfile.ZipFile(z_buf, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
                                        for root_z, dirs_z, files_z in os.walk(data_dir):
                                            dirs_z[:] = [d for d in dirs_z if d not in (".git", "node_modules", ".venv", "__pycache__")]
                                            for fz in files_z:
                                                if fz in ("script.py", "script.js", "command.sh", "project.zip"):
                                                    continue
                                                fp_z = os.path.join(root_z, fz)
                                                zf.write(fp_z, arcname=os.path.relpath(fp_z, data_dir))
                                    z_bytes = z_buf.getvalue()
                                    if z_bytes:
                                        zip_p = os.path.join(data_dir, "project.zip")
                                        with open(zip_p, "wb") as zf_out:
                                            zf_out.write(z_bytes)
                                        try:
                                            await upload_to_google_drive(user_id, conversation_id, data_dir)
                                        except Exception as gd_err:
                                            logger.warning(f"Google Drive sync in present_deliverable: {gd_err}")
                                        z_url = await _upload_generated_file(
                                            file_bytes=z_bytes,
                                            filename="project.zip",
                                            mime_type="application/zip",
                                            conversation_id=conversation_id,
                                            user_id=user_id,
                                        )
                                        presented_items.append({
                                            "filename": "project.zip",
                                            "download_url": z_url,
                                            "size_bytes": len(z_bytes),
                                        })
                                except Exception as z_err:
                                    logger.warning(f"Error creating project.zip in present_deliverable: {z_err}")

                            if presented_items:
                                accumulated_files.extend(presented_items)
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "generated_files",
                                        "files": presented_items,
                                    })
                                    + "\n\n"
                                )
                                tool_outputs.append(
                                    f"Successfully presented deliverable '{p_name}' with {len(presented_items)} files. "
                                    "The interactive preview and repository card are now displayed."
                                )
                            else:
                                tool_outputs.append(f"present_deliverable notice: No files found in sandbox to present.")
                        except Exception as e:
                            logger.error(f"Agent present_deliverable failed: {e}")
                            tool_outputs.append(f"present_deliverable error: {str(e)}")

                    elif t_name == "weather_fetch":

                        try:
                            from app.services.weather_service import fetch_weather
                            args = json.loads(t_args_str or "{}")
                            loc = (args.get("location", "") or "").strip()
                            days = int(args.get("days", 3) or 3)
                            if loc:
                                weather_result = await fetch_weather(loc, days=days)
                                tool_outputs.append(weather_result)
                            else:
                                tool_outputs.append("weather_fetch error: 'location' is required.")
                        except Exception as e:
                            logger.error(f"Agent weather_fetch failed: {e}")
                            tool_outputs.append(f"weather_fetch error: {str(e)}")

                    elif t_name == "ask_user_input":
                        try:
                            args = json.loads(t_args_str or "{}")
                            q = (args.get("question", "") or "").strip()
                            opts = args.get("options") or []
                            sel_type = args.get("select_type", "single_select")
                            if q and opts and isinstance(opts, list):
                                # Emit both event types to ensure full frontend compatibility
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "agent_ask_user_input",
                                        "question": q,
                                        "options": opts,
                                        "select_type": sel_type,
                                    })
                                    + "\n\n"
                                )
                                yield (
                                    "data: "
                                    + json.dumps({
                                        "type": "ask_user_input",
                                        "question": q,
                                        "options": opts,
                                        "select_type": sel_type,
                                    })
                                    + "\n\n"
                                )
                                if not assistant_content.strip():
                                    assistant_content = q
                                    yield (
                                        "data: "
                                        + json.dumps({
                                            "type": "content_block_delta",
                                            "delta": {"type": "text_delta", "text": q},
                                        })
                                        + "\n\n"
                                    )
                                tool_outputs.append(
                                    f"Presented question with tappable options to user: '{q}' "
                                    f"Options: {', '.join(str(o) for o in opts)}. "
                                    "Paused for user selection."
                                )
                                paused_for_user_input = True
                            else:
                                tool_outputs.append("ask_user_input error: 'question' and non-empty 'options' list required.")
                        except Exception as e:
                            logger.error(f"Agent ask_user_input failed: {e}")
                            tool_outputs.append(f"ask_user_input error: {str(e)}")

                    elif t_name == "end_conversation":
                        try:
                            from app.core.abuse_policy import STATE_ENDED, TERMINATION_MESSAGE
                            try:
                                supabase = get_supabase_admin()
                                await asyncio.to_thread(
                                    lambda: supabase.table("conversations")
                                    .update({"abuse_state": STATE_ENDED})
                                    .eq("id", conversation_id)
                                    .execute()
                                )
                            except Exception as db_err:
                                logger.warning(f"Could not persist abuse_state: {db_err}")

                            yield (
                                "data: "
                                + json.dumps({
                                    "type": "conversation_ended",
                                    "reason": "Abusive treatment after warning.",
                                    "message": TERMINATION_MESSAGE,
                                })
                                + "\n\n"
                            )
                            tool_outputs.append("Conversation ended permanently per safety policy.")
                            break
                        except Exception as e:
                            logger.error(f"Agent end_conversation failed: {e}")
                            tool_outputs.append(f"end_conversation error: {str(e)}")

                    else:
                        tool_outputs.append(f"Unknown tool name: {t_name}")

                # Add tool response messages to local history
                for tc, t_out in zip(current_tool_calls, tool_outputs):
                    local_messages.append({
                        "role": "system",
                        "content": f"[Tool Output for {tc['name']}]:\n{t_out}"
                    })

                if paused_for_user_input:
                    logger.info("Halting conversational OODA loop to await user interactive input.")
                    break

                iteration += 1
                continue

            break

        # Think/Solve Mode Fallback: if reasoning occurred but no final answer was emitted, auto-synthesize the response
        if (
            not stream_failed
            and routing_mode in ("think", "solve")
            and not assistant_content.strip()
            and accumulated_thinking.strip()
        ):
            logger.info("Think mode generated reasoning without final answer. Auto-synthesizing response...")
            yield (
                "data: "
                + json.dumps({
                    "type": "search_activity",
                    "status": "searching",
                    "label": "Formulating detailed answer...",
                })
                + "\n\n"
            )
            try:
                synth_input = local_messages + [
                    {"role": "system", "content": full_system},
                    {"role": "assistant", "content": f"<thinking>\n{accumulated_thinking}\n</thinking>"},
                    {"role": "user", "content": "Based on your thorough reasoning above, deliver your complete, detailed final response directly to the user."}
                ]
                synth_kwargs: Dict[str, Any] = {
                    "model": deployment,
                    "input": [normalize_responses_message(m) for m in synth_input],
                }
                if output_budget is not None:
                    synth_kwargs["max_output_tokens"] = output_budget
                if reasoning_effort:
                    synth_kwargs["reasoning"] = {"effort": reasoning_effort}
                async with client.responses.stream(**synth_kwargs) as synth_stream:
                    async for s_event in synth_stream:
                        if s_event.type == "response.output_text.delta":
                            s_chunk = s_event.delta
                            assistant_content += s_chunk
                            yield (
                                "data: "
                                + json.dumps({"type": "content_block_delta", "delta": {"text": s_chunk}})
                                + "\n\n"
                            )
            except Exception as synth_err:
                logger.warning(f"Think mode auto-synthesis error: {synth_err}")

        if stream_failed:
            lower_err = error_message.lower()
            is_guardrail = (
                "content_filter" in lower_err 
                or "responsible_ai" in lower_err 
                or "policy" in lower_err 
                or "safety" in lower_err
                or "trigger" in lower_err
                or "completed event" in lower_err
            )
            is_rate_limit = (
                "rate limit" in lower_err
                or "too many requests" in lower_err
                or "429" in lower_err
                or "high demand" in lower_err
                or "provisioned throughput" in lower_err
                or "peak load" in lower_err
            )
            if is_guardrail:
                friendly_err = "The request or response was flagged by safety guardrails. Please modify your query and try again."
            elif is_rate_limit:
                friendly_err = f"The AI service is experiencing high demand: {error_message}"
            else:
                friendly_err = f"A streaming connection issue occurred: {error_message}"

            if assistant_content:
                # Append the safety/early stop notice to the partial text
                assistant_content += f"\n\n*(Note: Response stopped early: {friendly_err})*"
                yield (
                    "data: "
                    + json.dumps({"type": "content_block_delta", "delta": {"text": f"\n\n*(Note: Response stopped early: {friendly_err})*"}})
                    + "\n\n"
                )
            else:
                # No content was generated at all, yield error event and exit
                yield f"data: {json.dumps({'type': 'error', 'error': friendly_err})}\n\n"
                yield "data: [DONE]\n\n"
                return

        try:
            # Fallback estimation if actual tokens are 0/None
            est_input = sum(len(m.get("content", "")) for m in messages) // 4
            est_output = len(assistant_content) // 4
            actual_prompt_tokens = prompt_tokens if prompt_tokens > 0 else max(50, est_input)
            actual_completion_tokens = completion_tokens if completion_tokens > 0 else max(10, est_output)

            assistant_msg_insert = {
                "conversation_id": conversation_id,
                "role": "assistant",
                "content": assistant_content,
                "routing_mode": routing_mode,
                "routing_reason": routing_reason,
                "response_id": response_id,
                "model": deployment,
                "tokens_input": actual_prompt_tokens,
                "tokens_output": actual_completion_tokens,
            }
            content_parts = {}
            if accumulated_thinking:
                content_parts["thinking_content"] = accumulated_thinking
            if accumulated_image_jobs:
                content_parts["image_jobs"] = accumulated_image_jobs
            if accumulated_files:
                content_parts["generated_files"] = [
                    {
                        "filename": f["filename"],
                        "download_url": f["download_url"],
                        "size_bytes": f["size_bytes"]
                    } for f in accumulated_files
                ]
            if accumulated_widgets:
                content_parts["widgets"] = accumulated_widgets
            if accumulated_display_cards:
                content_parts["display_cards"] = accumulated_display_cards
            if content_parts:
                assistant_msg_insert["content_parts"] = content_parts
            supabase = get_supabase_admin()
            await asyncio.to_thread(
                lambda: supabase.table("messages").insert(assistant_msg_insert).execute()
            )

            # Reconcile token budget
            actual_total = actual_prompt_tokens + actual_completion_tokens
            diff = actual_total - estimated_tokens
            if diff != 0:
                try:
                    await asyncio.to_thread(
                        lambda: supabase.rpc("reconcile_token_budget", {
                            "p_user_id": user_id,
                            "p_diff": diff
                        }).execute()
                    )
                    logger.info(f"Reconciled token budget for user {user_id} via RPC: diff={diff}")
                except Exception as rpc_err:
                    logger.warning("Failed to call reconcile_token_budget RPC, falling back to read-modify-write: %s", rpc_err)
                    try:
                        current_date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                        def get_budget():
                            return (
                                supabase.table("token_budgets")
                                .select("tokens_used")
                                .eq("user_id", user_id)
                                .eq("period", current_date_str)
                                .maybe_single()
                                .execute()
                            )
                        budget_res = await asyncio.to_thread(get_budget)
                        if budget_res.data:
                            current_used = budget_res.data.get("tokens_used", 0)
                            new_used = max(0, current_used + diff)
                            await asyncio.to_thread(
                                lambda: supabase.table("token_budgets").update({
                                    "tokens_used": new_used
                                }).eq("user_id", user_id).eq("period", current_date_str).execute()
                            )
                            logger.info(f"Reconciled token budget for user {user_id} via fallback: new_used={new_used}")
                    except Exception as fallback_err:
                        logger.error("Failed in-memory fallback for token budget reconciliation: %s", fallback_err)

            # Update message count in conversation
            def count_msgs():
                return (
                    supabase.table("messages")
                    .select("id", count="exact")
                    .eq("conversation_id", conversation_id)
                    .execute()
                )
            count_res = await asyncio.to_thread(count_msgs)
            msg_count = count_res.count if count_res.count is not None else (len(messages) + 2)
            await asyncio.to_thread(
                lambda: supabase.table("conversations").update({
                    "message_count": msg_count,
                }).eq("id", conversation_id).execute()
            )

        except Exception as db_err:
            logger.error(f"Failed to save assistant response: {db_err}")

        # Log routing decision to audit log
        try:
            audit_entry = {
                "user_id": user_id,
                "action": "model_route",
                "resource_type": "chat",
                "metadata": {
                    "mode": mode,
                    "deployment": deployment,
                    "reasoning": routing_reason,
                    "conversation_id": conversation_id,
                },
                "policy_decision": "ALLOW",
            }
            supabase = get_supabase_admin()
            await asyncio.to_thread(
                lambda: supabase.table("audit_log").insert(audit_entry).execute()
            )
        except Exception as audit_err:
            logger.error(f"Failed to log routing decision to audit_log: {audit_err}")

        yield "data: [DONE]\n\n"

    except Exception as e:
        logger.error(f"Error in chat stream generator: {e}")
        yield f"data: {json.dumps({'type': 'error', 'error': str(e)})}\n\n"
        yield "data: [DONE]\n\n"


def is_code_or_text_file(filename: str, mime_type: str = "") -> bool:
    _, ext = os.path.splitext(filename.lower())
    code_extensions = {
        ".txt", ".html", ".htm", ".css", ".js", ".mjs", ".ts", ".tsx", ".jsx", 
        ".vue", ".svelte", ".java", ".py", ".c", ".cpp", ".cc", ".h", ".hpp", 
        ".cs", ".sh", ".bash", ".json", ".md", ".yaml", ".yml", ".xml", ".sql", 
        ".csv", ".tsv", ".rs", ".go", ".rb", ".php", ".kt", ".swift", ".scala", 
        ".r", ".lua", ".dart", ".zig", ".sol", ".wasm", ".gradle", ".properties", 
        ".ipynb", ".ini", ".cfg", ".bat", ".cmd", ".ps1", ".toml", ".env", 
        ".dockerfile", ".graphql", ".gql", ".proto", ".diff", ".patch", ".log", ".tex"
    }
    if ext in code_extensions:
        return True
    if mime_type and (
        mime_type.startswith("text/") 
        or mime_type in {
            "application/json", "application/javascript", "application/xml", 
            "application/x-yaml", "application/toml", "application/graphql", 
            "application/x-sh", "application/dart"
        }
    ):
        return True
    return False


async def _fetch_attachment_bytes(att: Dict[str, Any]) -> Optional[bytes]:
    """
    Downloads attachment bytes using httpx with automatic fallback to direct Cloudflare R2 S3 retrieval.
    """
    att_url = att.get("url", "")
    file_id = att.get("file_id") or att.get("fileId")

    # 1. If file_id is provided, try direct R2 download first
    if file_id:
        try:
            return await download_file_bytes(file_id, "UPLOADS")
        except Exception as e:
            logger.debug(f"Direct R2 download via file_id '{file_id}' failed: {e}")

    # 2. If att_url is provided, try HTTP GET
    if att_url and (att_url.startswith("http://") or att_url.startswith("https://")):
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                r = await client.get(att_url)
                if r.status_code == 200:
                    return r.content
        except Exception as e:
            logger.debug(f"HTTP GET for '{att_url}' failed: {e}")

        # If HTTP failed (e.g. 401 on private R2 domain), try extracting R2 key from URL
        try:
            for marker in ["uploads/", "generated/"]:
                if marker in att_url:
                    key = marker + att_url.split(marker, 1)[1]
                    return await download_file_bytes(key, "UPLOADS")
        except Exception as e:
            logger.warning(f"Fallback R2 download from URL '{att_url}' failed: {e}")

    return None


_VALID_MODES = {"think", "solve", "discuss", "agent"}


@router.post("/responses/stream")
async def stream_chat(
    payload: Dict[str, Any],
    request: Request,
    user: Dict[str, Any] = Depends(verify_jwt)
):
    """
    POST /v1/responses/stream
    Streams chat completion responses using Server-Sent Events (SSE).

    Payload fields:
      - messages (list):              Full message history
      - mode (str):                   "think", "solve", or "discuss" (default: "think")
      - conversation_id (str):        For nano turn tracking and audit
      - previous_response_id (str):   Response ID from last turn (stateful multi-turn)
    """
    messages = payload.get("messages", [])
    raw_mode = payload.get("mode", "think")
    # Sanitise: coerce unknown values to the safest valid mode
    mode = raw_mode if raw_mode in _VALID_MODES else "think"
    conversation_id: Optional[str] = payload.get("conversation_id")
    previous_response_id: Optional[str] = payload.get("previous_response_id")

    if not messages:
        raise HTTPException(status_code=400, detail="Messages list cannot be empty.")

    # If user asks for test, return mock stream
    if messages[-1].get("content") == "__test_scaffold__":
        return StreamingResponse(
            mock_stream_generator(),
            media_type="text/event-stream"
        )

    # Extract the latest user message text for routing analysis
    last_user_msg = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            last_user_msg = m.get("content", "")
            break

    supabase = get_supabase_admin()
    user_id = user.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="User identifier not found in JWT.")

    # 1. Resolve or create conversation in the database
    is_new_conversation = False
    nano_turn_count = 0

    if not conversation_id or conversation_id == "00000000-0000-0000-0000-000000000000":
        is_new_conversation = True
        title = last_user_msg[:30] + "..." if len(last_user_msg) > 30 else last_user_msg
        if not title:
            title = "New Chat"

        conv_insert = {
            "user_id": user_id,
            "title": title,
            "mode": mode,
            "agent_type": "chat",
        }

        conv_res = None
        _modes_to_try = [mode, "think"] if mode != "think" else ["think"]
        last_exc: Optional[Exception] = None

        for _attempt_mode in _modes_to_try:
            conv_insert["mode"] = _attempt_mode
            # Retry transient network/socket errors with backoff
            for attempt in range(3):
                try:
                    conv_res = await asyncio.to_thread(
                        lambda: supabase.table("conversations").insert(conv_insert).execute()
                    )
                    if conv_res and conv_res.data:
                        if _attempt_mode != mode:
                            logger.warning(
                                f"conversations_mode_check blocked mode='{mode}' — "
                                f"inserted with fallback mode='{_attempt_mode}'."
                            )
                            mode = _attempt_mode
                        break
                except Exception as _ins_e:
                    last_exc = _ins_e
                    _err = str(_ins_e).lower()
                    if "mode_check" in _err or "check constraint" in _err or "constraint" in _err:
                        # Constraint error — proceed immediately to fallback mode
                        break
                    logger.warning(f"Transient DB insert attempt {attempt + 1} failed: {_ins_e}")
                    if attempt < 2:
                        await asyncio.sleep(0.25 * (attempt + 1))
            if conv_res and conv_res.data:
                break

        if conv_res and conv_res.data:
            conversation_id = conv_res.data[0]["id"]
            logger.info(f"Created new conversation {conversation_id} for user {user_id}")
        else:
            # Fallback UUID to guarantee chat stream is NEVER aborted due to transient DB connection
            fallback_id = str(uuid.uuid4())
            conversation_id = fallback_id
            logger.warning(f"Database conversation creation deferred, proceeding with fallback UUID {fallback_id}: {last_exc}")
        nano_turn_count = 0
    else:
        try:
            conv_res = None
            for attempt in range(3):
                try:
                    def fetch_conv():
                        return (
                            supabase.table("conversations")
                            .select("user_id, mode, nano_turn_count")
                            .eq("id", conversation_id)
                            .maybe_single()
                            .execute()
                        )
                    conv_res = await asyncio.to_thread(fetch_conv)
                    break
                except Exception as fetch_e:
                    if attempt < 2:
                        await asyncio.sleep(0.25 * (attempt + 1))
                    else:
                        logger.warning(f"Database fetch failed after retries: {fetch_e}")

            if not (conv_res and conv_res.data):
                # Conversation ID provided but not found in DB — auto-create
                is_new_conversation = True
                title = last_user_msg[:30] + "..." if len(last_user_msg) > 30 else last_user_msg
                conv_insert = {
                    "id": conversation_id,
                    "user_id": user_id,
                    "title": title or "New Chat",
                    "mode": mode,
                    "agent_type": "chat",
                }
                try:
                    create_res = await asyncio.to_thread(
                        lambda: supabase.table("conversations").insert(conv_insert).execute()
                    )
                    if create_res and create_res.data:
                        conversation_id = create_res.data[0]["id"]
                except Exception as create_e:
                    logger.warning(f"Auto-creating conversation with explicit ID failed (non-fatal, continuing stream): {create_e}")
                nano_turn_count = 0
            else:
                if conv_res.data.get("user_id") != user_id:
                    raise HTTPException(status_code=403, detail="Not authorized to access this conversation.")

                db_mode = conv_res.data.get("mode")
                if db_mode:
                    mode = db_mode
                nano_turn_count = conv_res.data.get("nano_turn_count", 0)
        except HTTPException:
            raise
        except Exception as e:
            logger.warning(f"Non-fatal error resolving conversation {conversation_id}, continuing stream: {e}")
            nano_turn_count = 0

    # Inspect attachments early to guide model routing and extraction
    attachments = payload.get("attachments", [])
    has_ocr_attachments = False
    has_non_ocr_attachments = False
    img_exts = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".ico", ".tiff", ".tif", ".avif", ".heic", ".heif"}

    for att in attachments:
        fname = (att.get("filename") or "").lower()
        mime = (att.get("mime_type") or "").lower()
        _, aext = os.path.splitext(fname)
        if aext in img_exts or (mime and mime.startswith("image/")):
            has_ocr_attachments = True
        elif fname:
            has_non_ocr_attachments = True

    # 2. Route through the model router
    decision = await model_router.route(
        user_message=last_user_msg,
        mode=mode,
        conversation_id=conversation_id,
        nano_turn_count=nano_turn_count,
        has_non_ocr_attachments=has_non_ocr_attachments,
        has_ocr_attachments=has_ocr_attachments,
    )

    logger.info(
        "Routing decision for conversation %s: mode=%s, deployment=%s, reasoning=%s",
        conversation_id,
        decision.routing_mode,
        decision.deployment,
        decision.routing_reason,
    )

    # Process and place attachments into active conversation sandbox
    injected_code_prompts = []
    injected_binary_files = []
    injected_image_files = []
    vision_image_data_uris = []

    # Sandbox directories for code execution & file inspection
    work_dir = f"/tmp/sandbox_{conversation_id}"
    data_dir = os.path.join(work_dir, "data")
    src_dir = os.path.join(work_dir, "src")
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(src_dir, exist_ok=True)

    # Ensure active conversation sandbox workspace is fully hydrated from Cloudflare R2
    # so files uploaded or generated in earlier turns remain instantly accessible across container lifecycles
    try:
        from app.services.code_sandbox import sync_conversation_sandbox_workspace
        if conversation_id and conversation_id != "00000000-0000-0000-0000-000000000000":
            await sync_conversation_sandbox_workspace(conversation_id, user_id)
    except Exception as ws_err:
        logger.debug(f"Non-fatal workspace hydration warning: {ws_err}")

    if attachments:
        from app.services.document_processor import DocumentProcessor

        archive_exts = {".zip", ".tar", ".gz", ".tgz", ".bz2", ".tbz2", ".xz", ".txz", ".7z", ".rar", ".zst", ".lzma", ".cab", ".iso", ".dmg"}
        tabular_exts = {".xlsx", ".xls", ".xlsm", ".csv", ".tsv", ".ods", ".parquet"}
        doc_exts = {".docx", ".pdf", ".doc", ".rtf", ".odt", ".odp", ".epub", ".tex"}
        audio_exts = {".mp3", ".wav", ".m4a", ".ogg", ".opus", ".oga", ".amr", ".flac", ".aac"}
        model_exts = {".pb", ".onnx"}

        for att in attachments:
            att_name = att.get("filename", "")
            att_url = att.get("url", "")
            att_mime = att.get("mime_type", "")
            
            if att_name:
                ext = os.path.splitext(att_name.lower())[1]
                is_code = is_code_or_text_file(att_name, att_mime)
                is_image = ext in img_exts or (att_mime and att_mime.startswith("image/"))
                is_archive = ext in archive_exts
                is_tabular = ext in tabular_exts
                is_doc = ext in doc_exts
                is_audio = ext in audio_exts or (att_mime and att_mime.startswith("audio/"))
                is_model = ext in model_exts
                
                try:
                    content_bytes = await _fetch_attachment_bytes(att)
                    if content_bytes is not None:
                        file_path = os.path.join(data_dir, att_name)
                        with open(file_path, "wb") as f:
                            f.write(content_bytes)
                        src_file_path = os.path.join(src_dir, att_name)
                        with open(src_file_path, "wb") as f:
                            f.write(content_bytes)
                            
                        logger.info(f"Successfully downloaded and placed file {att_name} in sandbox: {file_path}")
                        
                        # 1. Compressed Archives (decompressed into sandbox, directory tree & preview generated)
                        if is_archive:
                            target_unpacked = os.path.join(data_dir, f"unpacked_{os.path.splitext(att_name)[0]}")
                            arch_info = DocumentProcessor.extract_archive(file_path, target_unpacked)
                            try:
                                shutil.copytree(target_unpacked, os.path.join(src_dir, f"unpacked_{os.path.splitext(att_name)[0]}"), dirs_exist_ok=True)
                            except Exception as cpy_err:
                                logger.debug(f"Non-fatal mirror error for unpacked archive {att_name}: {cpy_err}")

                            tree_str = arch_info.get("file_tree", "")
                            num_files = arch_info.get("total_files", len(arch_info.get("extracted_files", [])))
                            summary_lines = [
                                f"--- ARCHIVE ARCHITECTURE: {att_name} ---",
                                f"Extracted {num_files} files into sandbox workspace (`unpacked_{os.path.splitext(att_name)[0]}/`).",
                                f"Directory Tree:\n{tree_str}"
                            ]
                            previews = arch_info.get("previews", {})
                            if previews:
                                summary_lines.append("\nKey File Previews:")
                                for p_name, p_body in list(previews.items())[:5]:
                                    summary_lines.append(f"File `{p_name}`:\n```\n{p_body[:1500]}\n```")
                            summary_lines.append(f"--- END ARCHIVE: {att_name} ---")
                            injected_code_prompts.append("\n".join(summary_lines))
                            injected_binary_files.append(att_name)

                        # 2. Tabular Data (spreadsheets & CSVs parsed to markdown tables)
                        elif is_tabular:
                            tabular_str = DocumentProcessor.extract_tabular_summary(file_path)
                            if tabular_str:
                                injected_code_prompts.append(
                                    f"--- TABULAR SUMMARY: {att_name} ---\n{tabular_str}\n--- END TABULAR SUMMARY: {att_name} ---"
                                )
                            injected_binary_files.append(att_name)

                        # 3. Documents (.docx, .pdf, .rtf native text extraction)
                        elif is_doc:
                            doc_text = DocumentProcessor.extract_document_text(file_path)
                            if doc_text and doc_text.strip():
                                injected_code_prompts.append(
                                    f"--- EXTRACTED DOCUMENT TEXT: {att_name} ---\n{doc_text}\n--- END DOCUMENT TEXT: {att_name} ---"
                                )
                            injected_binary_files.append(att_name)

                        # 4. Code & Text Files (decoded directly as UTF-8)
                        elif is_code:
                            try:
                                content_str = content_bytes.decode("utf-8", errors="replace")
                            except Exception:
                                content_str = "[Binary or non-UTF-8 content]"
                                
                            # Truncate content to avoid token limits (max 40k chars)
                            if len(content_str) > 40000:
                                content_str = content_str[:40000] + "\n... [TRUNCATED] ..."
                                
                            injected_code_prompts.append(
                                f"--- START FILE: {att_name} ---\n{content_str}\n--- END FILE: {att_name} ---"
                            )

                        # 5. Multimodal Images / OCR
                        elif is_image:
                            b64_img = base64.b64encode(content_bytes).decode("ascii")
                            mime = att_mime or "image/png"
                            data_uri = f"data:{mime};base64,{b64_img}"
                            vision_image_data_uris.append(data_uri)
                            injected_image_files.append(f"- `{att_name}`")
                            injected_binary_files.append(att_name)

                        # 6. Audio & WhatsApp Voice Notes
                        elif is_audio:
                            audio_tag = f"{att_name} (Audio format - can be inspected/converted using mutagen, pydub, scipy, ffmpeg in sandbox)"
                            injected_binary_files.append(audio_tag)

                        # 7. ML Models & Protobuf (.pb, .onnx)
                        elif is_model:
                            model_tag = f"{att_name} (Protobuf / ML model - can be inspected via google.protobuf or onnx in sandbox)"
                            injected_binary_files.append(model_tag)

                        # 8. Other Binaries
                        else:
                            injected_binary_files.append(att_name)

                except Exception as e:
                    logger.error(f"Failed to process attachment {att_name}: {e}")
                        
    # Check all files currently present in the sandbox data directory
    current_sandbox_files = []
    if os.path.exists(data_dir):
        try:
            for root, dirs, files in os.walk(data_dir):
                dirs[:] = [d for d in dirs if not d.startswith(".")]
                for f in files:
                    if not f.startswith("."):
                        rel_p = os.path.relpath(os.path.join(root, f), data_dir)
                        current_sandbox_files.append(rel_p)
                if len(current_sandbox_files) >= 100:
                    break
        except Exception:
            current_sandbox_files = []

    # Inject contents of existing text/code/markdown workspace files not already injected this turn
    for fname in current_sandbox_files:
        if any(fname in p for p in injected_code_prompts):
            continue
        full_p = os.path.join(data_dir, fname)
        ext = os.path.splitext(fname.lower())[1]
        is_code = is_code_or_text_file(fname) or ext in {".md", ".txt", ".json", ".csv", ".py", ".js", ".ts", ".html", ".css", ".yaml", ".yml", ".sql", ".sh"}
        if is_code:
            try:
                sz = os.path.getsize(full_p)
                # Auto-inject readable text files under 35KB
                if sz <= 35000:
                    with open(full_p, "r", encoding="utf-8", errors="replace") as f_in:
                        content_str = f_in.read()
                    if len(content_str) > 30000:
                        content_str = content_str[:30000] + "\n... [TRUNCATED] ..."
                    injected_code_prompts.append(
                        f"--- PERSISTENT WORKSPACE FILE: {fname} ---\n{content_str}\n--- END FILE: {fname} ---"
                    )
            except Exception as read_err:
                logger.debug(f"Could not auto-read workspace file {fname}: {read_err}")

    if injected_code_prompts or injected_binary_files or injected_image_files or current_sandbox_files:
        context_parts = []
        if injected_code_prompts:
            context_parts.append(
                "Here are the contents of the attached code/text files:\n" +
                "\n\n".join(injected_code_prompts)
            )
        if injected_image_files:
            context_parts.append(
                "Attached Images in this turn:\n" +
                "\n".join(injected_image_files)
            )
        if current_sandbox_files:
            all_files_list = ", ".join(f"`{f}`" for f in current_sandbox_files)
            context_parts.append(
                f"The following user files/images are currently available in your active sandbox workspace:\n"
                f"[{all_files_list}]\n\n"
                "CRITICAL ZERO-EXCUSE FILE ACCESS MANDATE:\n"
                "- NEVER state 'I cannot find your file', 'I don't have access to your file', or 'I cannot see its content', or ask the user to re-upload.\n"
                "- All user files uploaded in this conversation are ALREADY saved in your sandbox workspace (`/workspace/data/` or `./`).\n"
                "- If a file's content is not inlined above (e.g. audio, protobuf `.pb` models, complex binaries, or unscanned docs), you have full autonomous tools (`sandbox_read`, `sandbox_ls`, `execute_code`) to inspect, parse, or execute scripts on them.\n\n"
                "AUDIO & WHATSAPP MEDIA PROCESSING:\n"
                "- For audio files (including WhatsApp voice notes `.opus`, `.oga`, `.amr`, `.m4a`, `.aac`, `.mp3`, `.wav`, `.flac`):\n"
                "  The sandbox environment has internet access. You can autonomously install any audio libraries on demand via `execute_code` (e.g. `pip install mutagen pydub soundfile librosa`). You can extract metadata (duration, sample rate, bit rate, channels), convert `.opus`/`.oga`/`.amr` to `.wav`, plot waveforms, or transcribe/analyze the audio directly.\n\n"
                "MACHINE LEARNING & PROTOBUF (.pb):\n"
                "- For `.pb` (Protobuf serialized models / TensorFlow graphs / protocol buffer binaries):\n"
                "  You can autonomously inspect message descriptors or graph nodes via `execute_code` using `google.protobuf` or `pip install protobuf onnx`.\n\n"
                "DOCUMENT & PDF EXTRACTION (AI-FIRST INTELLIGENCE):\n"
                "- Initial text extracted by PyMuPDF or python-docx above is SECONDARY — YOU are the primary intelligence determining accuracy.\n"
                "- If the extracted text appears noisy, incomplete, scrambled, or missing tables/images (scanned PDF), DO NOT conclude the file has no content. AUTONOMOUSLY inspect the raw file in the sandbox using `execute_code` (`pdfplumber`, `fitz.open()`, rendering pages as PNGs to inspect or OCR with `easyocr` / `pytesseract` / vision). Always deliver thorough and accurate answers."
            )
            
        code_context_str = (
            "\n\n[System Context: User attached files and sandbox workspace state:\n" +
            "\n\n".join(context_parts) +
            "\n]\n\n"
        )
        decision.system_prompt += code_context_str

    # 3. If nano interceptor fired, increment the turn counter in the database
    if decision.was_intercepted:
        try:
            # We call the increment_nano_turns RPC to update the count
            await asyncio.to_thread(
                lambda: supabase.rpc("increment_nano_turns", {"p_conv_id": conversation_id}).execute()
            )
        except Exception as e:
            logger.error(f"Failed to increment nano turn count: {e}")

    # 4. Save the user's message to the database
    # Non-fatal: log the error and continue streaming — a missing user message row is
    # recoverable; aborting the entire stream is not.
    try:
        user_msg_insert = {
            "conversation_id": conversation_id,
            "role": "user",
            "content": last_user_msg,
        }
        if payload.get("attachments"):
            user_msg_insert["content_parts"] = {"attachments": payload.get("attachments")}
        await asyncio.to_thread(
            lambda: supabase.table("messages").insert(user_msg_insert).execute()
        )
    except Exception as e:
        logger.error(f"Failed to save user message to database (non-fatal, stream continues): {e}")

    # Trigger compaction check if not a brand new conversation
    compaction_summary = None
    if not is_new_conversation:
        compaction_summary = await compact_conversation_history(conversation_id)

    # 5. Build context from active database messages (ignores archived/compacted ones)
    db_context_messages = await build_llm_context(conversation_id)

    # 5a. If the current turn has image attachments, inject them as multimodal image_url
    #     content parts into the LAST user message so the vision model can actually see them.
    #     We prioritize base64 Data URIs so the model receives the image bytes inline without
    #     relying on external public domain reachability.
    if (vision_image_data_uris or any(
        att.get("url") and (
            att.get("mime_type", "").startswith("image/") or
            os.path.splitext(att.get("filename", "").lower())[1] in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".tiff", ".avif"}
        )
        for att in payload.get("attachments", [])
    )) and db_context_messages:
        resolved_images = []
        if vision_image_data_uris:
            resolved_images = vision_image_data_uris
        else:
            resolved_images = [
                att.get("url", "")
                for att in payload.get("attachments", [])
                if att.get("url") and (
                    att.get("mime_type", "").startswith("image/") or
                    os.path.splitext(att.get("filename", "").lower())[1] in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".bmp", ".tiff", ".avif"}
                )
            ]

        # Find the last user message and upgrade it to multimodal
        for idx in range(len(db_context_messages) - 1, -1, -1):
            msg = db_context_messages[idx]
            if msg.get("role") == "user":
                raw_c = msg.get("content", "")
                text_part = ""
                if isinstance(raw_c, str):
                    text_part = raw_c
                elif isinstance(raw_c, list):
                    text_part = "\n\n".join(
                        p.get("text", "") if isinstance(p, dict) else str(p)
                        for p in raw_c
                        if not isinstance(p, dict) or p.get("type") in ("text", "input_text")
                    )
                multimodal_content: List[Any] = [{"type": "input_text", "text": text_part or last_user_msg or "Please analyze this image."}]
                for img_src in resolved_images:
                    multimodal_content.append({
                        "type": "input_image",
                        "image_url": img_src,
                        "detail": "auto"
                    })
                db_context_messages[idx] = {**msg, "content": multimodal_content}
                logger.info(
                    "Injected %d image(s) as multimodal vision content into user message for conversation %s",
                    len(resolved_images), conversation_id
                )
                break


    estimated_tokens = getattr(request.state, "estimated_tokens", 0) or 0

    # Stream from Azure OpenAI Responses API
    return StreamingResponse(
        chat_stream_generator(
            db_context_messages,
            decision.deployment,
            decision.system_prompt,
            decision.routing_mode,
            decision.routing_reason,
            conversation_id,
            user_id,
            mode,
            estimated_tokens,
            previous_response_id,
            user_timezone=payload.get("timezone"),
            viewport=payload.get("viewport"),  # "mobile" | "desktop" | None
            compaction_summary=compaction_summary,
            reasoning_effort=decision.reasoning_effort,
            complexity=decision.complexity,
            workstation_access_enabled=bool(payload.get("workstation_access_enabled", False)),
            review_policy=payload.get("review_policy"),
        ),
        media_type="text/event-stream"
    )


async def _upload_generated_file(
    file_bytes: bytes,
    filename: str,
    mime_type: str,
    conversation_id: str,
    user_id: str,
) -> str:
    """Upload to R2, persist metadata. Returns public URL."""
    from app.services.cloudflare_r2 import upload_file_bytes

    # Uploads to the sharded GENERATED bucket
    r2_url = await upload_file_bytes(
        file_bytes=file_bytes,
        filename=filename,
        mime_type=mime_type,
        bucket_type="GENERATED",
        key_prefix=f"generated/{conversation_id}/"
    )

    try:
        get_supabase_admin().table("generated_files").insert({
            "conversation_id": conversation_id,
            "user_id":         user_id,
            "filename":        filename,
            "r2_url":          r2_url,
            "size_bytes":      len(file_bytes),
            "mime_type":       mime_type,
        }).execute()
    except Exception as db_err:
        logger.warning("Failed to save generated_file metadata: %s", db_err)

    return r2_url


