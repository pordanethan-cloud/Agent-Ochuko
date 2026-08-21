# tests/test_agent_mode_phase2.py
"""
Tests for Agent Mode Phase 2 Capabilities:
- Instant 1-Click Static Site Deployment (/sites/:slug)
- Headless Browser Scraping & Markdown Extraction
- Handle Intelligence (GitHub, Twitter, Social)
- SubAgentPool Phase 2 Tool Delegations
- AgentTaskManager Phase 2 Step Dispatching
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.hosted_sites_service import (
    HostedSitesService,
    bundle_html,
    generate_slug,
    _MEMORY_HOSTED_SITES,
)
from app.services.browser_agent import (
    BrowserAgent,
    html_to_clean_markdown,
)
from app.services.handle_intelligence import (
    HandleIntelligence,
)
from app.core.sub_agent_pool import SubAgentPool
from app.core.agent_task_models import AgentTask, PlanStep
from app.core.agent_task_manager import AgentTaskManager


@pytest.mark.asyncio
async def test_hosted_sites_bundle_and_deploy():
    """Verifies that static site bundling creates responsive HTML and deploys to memory/DB."""
    html = "<div class='hero'><h1>Hello World</h1></div>"
    css = ".hero { color: red; }"
    js = "console.log('loaded');"

    bundled = bundle_html("My Site", html, css, js)
    assert "<!DOCTYPE html>" in bundled
    assert "Hello World" in bundled
    assert ".hero { color: red; }" in bundled
    assert "console.log('loaded');" in bundled
    assert "viewport" in bundled

    # Deploy site
    res = await HostedSitesService.deploy_site(
        title="Portfolio Demo",
        html_content=html,
        css_content=css,
        js_content=js,
        base_url="http://localhost:8000",
    )

    assert "site_id" in res
    assert "slug" in res
    assert res["preview_url"].startswith("http://localhost:8000/v1/sites/")
    assert res["title"] == "Portfolio Demo"

    # Retrieve deployed site
    site = await HostedSitesService.get_site(res["slug"])
    assert site is not None
    assert site["title"] == "Portfolio Demo"
    assert "Hello World" in site["html_content"]


def test_browser_agent_html_to_markdown():
    """Verifies clean structured markdown extraction from complex HTML."""
    raw_html = """
    <!DOCTYPE html>
    <html>
      <head>
        <title>Pricing & Specs | SuperApp</title>
        <meta name="description" content="Official technical specifications and pricing breakdown.">
      </head>
      <body>
        <nav><a href="/home">Home</a></nav>
        <main>
          <h1>Enterprise Pricing</h1>
          <p>SuperApp provides scalable cloud architectures.</p>
          <table>
            <tr><th>Tier</th><th>Price</th></tr>
            <tr><td>Starter</td><td>$10/mo</td></tr>
            <tr><td>Pro</td><td>$50/mo</td></tr>
          </table>
        </main>
        <footer><p>Copyright 2026</p></footer>
      </body>
    </html>
    """

    parsed = html_to_clean_markdown(raw_html)
    assert parsed["title"] == "Pricing & Specs | SuperApp"
    assert "Official technical specifications" in parsed["description"]
    assert "Enterprise Pricing" in parsed["content_markdown"]
    assert "| Tier | Price |" in parsed["content_markdown"]
    assert "| Starter | $10/mo |" in parsed["content_markdown"]
    assert "Copyright" not in parsed["content_markdown"]  # footer stripped


@pytest.mark.asyncio
async def test_handle_intelligence_github_parsing():
    """Verifies developer handle lookup parses public GitHub profiles cleanly."""
    mock_user_data = {
        "login": "torvalds",
        "name": "Linus Torvalds",
        "avatar_url": "https://github.com/images/avatar.jpg",
        "bio": "Linux creator",
        "public_repos": 10,
        "followers": 200000,
        "html_url": "https://github.com/torvalds",
    }
    mock_repos_data = [
        {
            "name": "linux",
            "description": "Linux kernel source tree",
            "language": "C",
            "stargazers_count": 180000,
            "forks_count": 55000,
            "html_url": "https://github.com/torvalds/linux",
        }
    ]

    with patch("httpx.AsyncClient.get") as mock_get:
        mock_res1 = MagicMock()
        mock_res1.status_code = 200
        mock_res1.json.return_value = mock_user_data

        mock_res2 = MagicMock()
        mock_res2.status_code = 200
        mock_res2.json.return_value = mock_repos_data

        mock_get.side_effect = [mock_res1, mock_res2]

        res = await HandleIntelligence.lookup_profile("torvalds", platform="github")
        assert res["success"] is True
        assert res["username"] == "torvalds"
        assert res["name"] == "Linus Torvalds"
        assert len(res["top_repositories"]) == 1
        assert res["top_repositories"][0]["name"] == "linux"
        assert "Linux creator" in res["summary"]


@pytest.mark.asyncio
async def test_sub_agent_phase2_delegations():
    """Verifies SubAgentPool delegation methods for Phase 2 tools."""
    mock_client = MagicMock()
    pool = SubAgentPool(openai_client=mock_client, nano_deployment="test-nano")

    # 1. Site deployment delegation
    site_res = await pool.delegate_site_deployment(
        title="Test App",
        html_content="<h1>Live</h1>",
    )
    assert site_res.success is True
    assert len(site_res.artifacts) == 1
    assert site_res.artifacts[0]["type"] == "site_preview"
    assert "/v1/sites/" in site_res.artifacts[0]["download_url"]

    # 2. Browser scrape delegation
    with patch.object(BrowserAgent, "scrape_url", new=AsyncMock(return_value={"success": True, "summary": "Scraped page text.", "content_markdown": "Page content"})):
        scrape_res = await pool.delegate_browser_scrape("https://example.com")
        assert scrape_res.success is True
        assert "Scraped page text" in scrape_res.summary


@pytest.mark.asyncio
async def test_agent_task_manager_phase2_step_dispatch():
    """Verifies AgentTaskManager dispatches Phase 2 tool steps accurately."""
    task = AgentTask(goal="Create and deploy modern landing page", conversation_id="conv-123", user_id="user-456")
    mock_client = MagicMock()
    manager = AgentTaskManager(task=task, openai_client=mock_client, deployment="test", nano_deployment="test")

    # Step: deploy_site
    deploy_step = PlanStep(index=1, description="Deploy landing page for AI SaaS", tool_name="deploy_site")
    with patch.object(manager, "_generate_website_code", new=AsyncMock(return_value="<h1>AI SaaS</h1>")):
        res = await manager._execute_single_step(deploy_step)
        assert res.success is True
        assert len(res.artifacts) == 1
        assert res.artifacts[0]["type"] == "site_preview"
        assert "/v1/sites/" in res.artifacts[0]["download_url"]
