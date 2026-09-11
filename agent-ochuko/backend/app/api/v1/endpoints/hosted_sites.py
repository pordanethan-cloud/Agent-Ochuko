# app/api/v1/endpoints/hosted_sites.py
"""
Hosted Sites Endpoints.
Serves instant 1-click deployed static websites and provides REST endpoints
for site creation and management.
"""

from typing import Optional, Dict, Any
import base64
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from pydantic import BaseModel, Field

from app.core.jwt_validator import verify_jwt
from app.api.v1.endpoints.chat import get_supabase_admin
from app.services.hosted_sites_service import HostedSitesService

router = APIRouter()


class DeploySiteRequest(BaseModel):
    title: str = Field("Untitled Project", description="Site title")
    html_content: str = Field(..., description="Raw or bundled HTML markup")
    css_content: Optional[str] = Field("", description="Optional custom CSS")
    js_content: Optional[str] = Field("", description="Optional custom JavaScript")
    files: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "Repo-style multi-file site map (relpath → text content). When present "
            "with index.html, the site is served multi-file: /{slug} serves "
            "index.html and /{slug}/{path} serves bundled files so relative links "
            "resolve. Binary assets may use data: URIs."
        ),
    )
    conversation_id: Optional[str] = Field(None, description="Linked conversation ID")
    is_public: bool = Field(True, description="Whether the site is publicly reachable")


@router.post("/deploy", status_code=201)
@router.post("/", status_code=201)
async def deploy_website(
    payload: DeploySiteRequest,
    request: Request,
    user: Dict = Depends(verify_jwt),
):
    """Deploys a static HTML/CSS/JS website and returns its live preview URL."""
    user_id = user.get("sub")
    supabase = get_supabase_admin()
    base_url = str(request.base_url)

    result = await HostedSitesService.deploy_site(
        title=payload.title,
        html_content=payload.html_content,
        css_content=payload.css_content or "",
        js_content=payload.js_content or "",
        user_id=user_id,
        conversation_id=payload.conversation_id,
        is_public=payload.is_public,
        supabase_client=supabase,
        base_url=base_url,
        files=payload.files,
    )
    return result


@router.get("/{slug}")
async def render_hosted_site(slug: str):
    """
    Publicly serves the deployed static website as interactive text/html
    with safe sandbox CSP and responsive mobile rendering. For multi-file
    sites (Phase 5), this serves the bundled index.html so relative links
    resolve against /{slug}/{path}.
    """
    supabase = get_supabase_admin()
    site = await HostedSitesService.get_site(slug, supabase_client=supabase)
    if not site:
        raise HTTPException(status_code=404, detail="Hosted website not found or has been removed.")

    # Multi-file site: serve the bundled index.html entry point.
    site_files = site.get("files") or {}
    if site_files:
        index_content = site_files.get("index.html") or site_files.get("index.htm")
        if index_content:
            content = index_content
        else:
            content = site.get("html_content", "<h1>Empty site</h1>")
    else:
        content = site.get("html_content", "<h1>Empty site</h1>")

    headers = {
        "Content-Security-Policy": (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' https: data: blob:; "
            "img-src 'self' https: data: blob:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "font-src 'self' https: data:; "
            "frame-ancestors 'self' http://localhost:* https://*;"
        ),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=3600",
    }
    return Response(
        content=content,
        media_type="text/html; charset=utf-8",
        headers=headers,
    )


@router.get("/{slug}/raw")
async def get_hosted_site_raw(slug: str):
    """Returns the raw site JSON data for editing or inspection."""
    supabase = get_supabase_admin()
    site = await HostedSitesService.get_site(slug, supabase_client=supabase)
    if not site:
        raise HTTPException(status_code=404, detail="Hosted website not found.")
    return site


@router.get("/{slug}/{file_path:path}")
async def render_hosted_site_file(slug: str, file_path: str):
    """
    Serves one bundled file of a multi-file hosted site (css/styles.css,
    js/main.js, images/...). data: URI payloads are decoded to bytes.
    NOTE: registered AFTER /{slug}/raw so the raw endpoint is not shadowed.
    """
    supabase = get_supabase_admin()
    entry = await HostedSitesService.get_site_file(slug, file_path, supabase_client=supabase)
    if not entry:
        raise HTTPException(status_code=404, detail="Site file not found.")

    headers = {
        "Content-Security-Policy": (
            "default-src 'self' 'unsafe-inline' 'unsafe-eval' https: data: blob:; "
            "img-src 'self' https: data: blob:; "
            "style-src 'self' 'unsafe-inline' https:; "
            "font-src 'self' https: data:; "
            "frame-ancestors 'self' http://localhost:* https://*;"
        ),
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "public, max-age=3600",
    }
    content = entry["content"]
    if content.startswith("data:"):
        _header, _, payload = content.partition(",")
        try:
            return Response(content=base64.b64decode(payload), media_type=entry["content_type"], headers=headers)
        except Exception:
            raise HTTPException(status_code=500, detail="Corrupt data URI in site file.")
    return Response(
        content=content.encode("utf-8"),
        media_type=entry["content_type"],
        headers=headers,
    )
