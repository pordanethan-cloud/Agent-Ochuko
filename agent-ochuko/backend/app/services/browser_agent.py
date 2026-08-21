# app/services/browser_agent.py
"""
Headless Browser & Scraping Agent Service.
Extracts structured markdown, accessibility content, tables, and page metadata
from live URLs with high speed, anti-blocking headers, and clean readability formatting.
"""

import re
import asyncio
import logging
from typing import Dict, Any, Optional, List
import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger("app.services.browser_agent")

_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Sec-Ch-Ua": '"Chromium";v="122", "Not(A:Brand";v="24", "Google Chrome";v="122"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Upgrade-Insecure-Requests": "1",
}


def html_to_clean_markdown(html_content: str, max_chars: int = 4000) -> Dict[str, Any]:
    """
    Converts raw HTML into clean, high-density structured markdown.
    Strips noise (nav, ads, footer, scripts) while preserving headings, lists, tables, and links.
    """
    soup = BeautifulSoup(html_content, "html.parser")

    # 1. Extract metadata
    title = soup.title.string.strip() if soup.title and soup.title.string else "Untitled Page"
    meta_desc = ""
    desc_tag = soup.find("meta", attrs={"name": re.compile(r"description", re.I)}) or soup.find("meta", attrs={"property": re.compile(r"og:description", re.I)})
    if desc_tag and desc_tag.get("content"):
        meta_desc = desc_tag["content"].strip()

    # 2. Strip non-content elements
    for tag in soup(["script", "style", "noscript", "nav", "footer", "header", "aside", "svg", "form", "iframe"]):
        tag.decompose()

    # 3. Find main content container if available
    main_el = soup.find("main") or soup.find("article") or soup.find("div", class_=re.compile(r"content|post|article|body", re.I)) or soup.body or soup

    # 4. Convert tables to markdown
    for table in main_el.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cells = [c.get_text(strip=True) for c in tr.find_all(["th", "td"])]
            if cells:
                rows.append("| " + " | ".join(cells) + " |")
        if rows:
            header_sep = "| " + " | ".join(["---"] * len(table.find_all("tr")[0].find_all(["th", "td"]))) + " |"
            if len(rows) > 1:
                table_md = "\n" + rows[0] + "\n" + header_sep + "\n" + "\n".join(rows[1:]) + "\n"
            else:
                table_md = "\n" + rows[0] + "\n"
            table.replace_with(table_md)

    # 5. Extract structured text
    raw_text = main_el.get_text(separator="\n", strip=True)

    # 6. Normalize line breaks and clean whitespace
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    cleaned_md = "\n\n".join(lines)

    if len(cleaned_md) > max_chars:
        cleaned_md = cleaned_md[:max_chars] + f"\n\n... [Content truncated for speed, {len(cleaned_md)} total chars extracted]"

    return {
        "title": title,
        "description": meta_desc,
        "content_markdown": cleaned_md,
        "char_count": len(cleaned_md),
    }


class BrowserAgent:
    """Headless browser and web scraping agent."""

    @staticmethod
    async def scrape_url(
        url: str,
        extract_type: str = "markdown",
        timeout_seconds: float = 6.0,
    ) -> Dict[str, Any]:
        """
        Fast asynchronous web page scraping with anti-blocking headers and clean markdown extraction.
        """
        target_url = url.strip()
        if not target_url.startswith(("http://", "https://")):
            target_url = "https://" + target_url

        try:
            async with httpx.AsyncClient(
                headers=_BROWSER_HEADERS,
                timeout=timeout_seconds,
                follow_redirects=True,
                verify=False,
            ) as client:
                response = await client.get(target_url)

            if response.status_code >= 400:
                return {
                    "success": False,
                    "url": target_url,
                    "status_code": response.status_code,
                    "error": f"HTTP {response.status_code}: Unable to load page.",
                    "summary": f"Could not access {target_url} (HTTP {response.status_code}).",
                }

            parsed = html_to_clean_markdown(response.text)

            summary = (
                f"**Page Title**: {parsed['title']}\n\n"
                f"{parsed['content_markdown'][:800]}..."
            )

            return {
                "success": True,
                "url": target_url,
                "status_code": response.status_code,
                "title": parsed["title"],
                "description": parsed["description"],
                "content_markdown": parsed["content_markdown"],
                "summary": summary,
            }

        except Exception as err:
            logger.warning(f"BrowserAgent scrape error for {target_url}: {err}")
            return {
                "success": False,
                "url": target_url,
                "error": str(err),
                "summary": f"Error scraping {target_url}: {str(err)[:120]}",
            }
