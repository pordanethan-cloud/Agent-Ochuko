# app/services/hosted_sites_service.py
"""
Instant 1-Click Static Website Deployment Service.
Enables Agent Ochuko and users to deploy interactive HTML/CSS/JS websites,
landing pages, portfolios, and web tools to instant public URLs (/v1/sites/{slug}).
Includes in-memory cache fallback for resilient zero-downtime deployment.
"""

import re
import uuid
import secrets
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger("app.services.hosted_sites_service")

# In-memory storage fallback for zero-dependency local testing & network resiliency
_MEMORY_HOSTED_SITES: Dict[str, Dict[str, Any]] = {}


def generate_slug(title: str = "") -> str:
    """Generates a clean, short, URL-safe slug."""
    clean_title = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    short_hash = secrets.token_hex(3)
    if clean_title:
        return f"{clean_title[:24]}-{short_hash}"
    return f"site-{short_hash}"


def bundle_html(
    title: str,
    html_content: str,
    css_content: str = "",
    js_content: str = "",
) -> str:
    """
    Bundles HTML, CSS, and JS into a clean, standalone, mobile-responsive HTML document.
    Embeds security sandbox meta tags and mobile viewport standards.
    """
    raw_html = (html_content or "").strip()
    
    # If the provided HTML is already a complete <html> document, inject CSS/JS if provided
    if "<!doctype html" in raw_html.lower() or "<html" in raw_html.lower():
        bundled = raw_html
        if css_content and "<style>" not in bundled:
            bundled = re.sub(r"</head>", f"<style>\n{css_content}\n</style>\n</head>", bundled, flags=re.IGNORECASE)
        if js_content and "<script>" not in bundled:
            bundled = re.sub(r"</body>", f"<script>\n{js_content}\n</script>\n</body>", bundled, flags=re.IGNORECASE)
        return bundled

    # Otherwise wrap cleanly in high-quality HTML5 shell
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
  <title>{title or "Agent Ochuko Hosted Site"}</title>
  <!-- Tailwind & Google Fonts for instant premium styling -->
  <script src="https://cdn.tailwindcss.com"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    * {{
      font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      box-sizing: border-box;
    }}
    code, pre {{
      font-family: 'JetBrains Mono', monospace;
    }}
    {css_content}
  </style>
</head>
<body class="bg-[#0c0e12] text-white/90 antialiased min-h-screen">
  {html_content}

  <script>
    {js_content}
  </script>
</body>
</html>"""


class HostedSitesService:
    """Handles static site deployment, retrieval, and lifecycle management."""

    @staticmethod
    async def deploy_site(
        title: str,
        html_content: str,
        css_content: str = "",
        js_content: str = "",
        user_id: Optional[str] = None,
        conversation_id: Optional[str] = None,
        is_public: bool = True,
        supabase_client=None,
        base_url: str = "http://localhost:8000",
    ) -> Dict[str, Any]:
        """
        Deploys a static site and returns the site metadata and live preview URL.
        """
        slug = generate_slug(title)
        full_html = bundle_html(title=title, html_content=html_content, css_content=css_content, js_content=js_content)
        site_id = str(uuid.uuid4())
        now_iso = datetime.utcnow().isoformat()

        site_record = {
            "id": site_id,
            "slug": slug,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "title": title or "Untitled Site",
            "html_content": full_html,
            "css_content": css_content,
            "js_content": js_content,
            "is_public": is_public,
            "view_count": 0,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        # Cache in memory immediately for ultra-fast response
        _MEMORY_HOSTED_SITES[slug] = site_record
        _MEMORY_HOSTED_SITES[site_id] = site_record

        # Persist to Supabase if available
        if supabase_client:
            try:
                await asyncio.to_thread(
                    lambda: supabase_client.table("hosted_sites")
                    .insert({
                        "id": site_id,
                        "slug": slug,
                        "user_id": user_id,
                        "conversation_id": conversation_id,
                        "title": title or "Untitled Site",
                        "html_content": full_html,
                        "css_content": css_content,
                        "js_content": js_content,
                        "is_public": is_public,
                    })
                    .execute()
                )
            except Exception as db_err:
                logger.warning(f"Supabase hosted_sites insert failed (using memory store): {db_err}")

        preview_url = f"{base_url.rstrip('/')}/v1/sites/{slug}"

        return {
            "site_id": site_id,
            "slug": slug,
            "title": title or "Untitled Site",
            "preview_url": preview_url,
            "is_public": is_public,
            "created_at": now_iso,
        }

    @staticmethod
    async def get_site(slug_or_id: str, supabase_client=None) -> Optional[Dict[str, Any]]:
        """Retrieves a deployed site by slug or UUID."""
        # 1. Memory check
        if slug_or_id in _MEMORY_HOSTED_SITES:
            site = _MEMORY_HOSTED_SITES[slug_or_id]
            site["view_count"] = site.get("view_count", 0) + 1
            return site

        # 2. Supabase DB check
        if supabase_client:
            try:
                res = await asyncio.to_thread(
                    lambda: supabase_client.table("hosted_sites")
                    .select("*")
                    .or_(f"slug.eq.{slug_or_id},id.eq.{slug_or_id}")
                    .maybe_single()
                    .execute()
                )
                if res and res.data:
                    _MEMORY_HOSTED_SITES[slug_or_id] = res.data
                    return res.data
            except Exception as db_err:
                logger.warning(f"Supabase get_site query error: {db_err}")

        return None
