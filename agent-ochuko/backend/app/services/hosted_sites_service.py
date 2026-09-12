# app/services/hosted_sites_service.py
"""
Instant 1-Click Static Website Deployment Service.
Enables Agent Ochuko and users to deploy interactive HTML/CSS/JS websites,
landing pages, portfolios, and web tools to instant public URLs (/v1/sites/{slug}).
Includes in-memory cache fallback for resilient zero-downtime deployment.
"""

import os
import re
import uuid
import base64
import secrets
import asyncio
import logging
from typing import Dict, Any, Optional, List
from datetime import datetime

# Public-facing base URL of the backend — used to build hosted-site preview links.
# Set BACKEND_PUBLIC_URL in your container/env to the Container App URL.
_DEFAULT_BASE_URL = os.environ.get(
    "BACKEND_PUBLIC_URL",
    "https://agent-ochuko-api.calmbush-d59124b5.southafricanorth.azurecontainerapps.io"
)

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


# ── Phase 5 (B): multi-file site helpers ─────────────────────────────────────

_SITE_MIME_MAP = {
    ".html": "text/html; charset=utf-8",
    ".htm": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "text/javascript; charset=utf-8",
    ".mjs": "text/javascript; charset=utf-8",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".txt": "text/plain; charset=utf-8",
    ".md": "text/plain; charset=utf-8",
    ".xml": "application/xml",
    ".webmanifest": "application/manifest+json",
}

_TRAVERSAL_RE = re.compile(r"(^|[/\\])\.\.($|[/\\])")

# Relative href/src extractor for hosted-site bundle integrity checks (Gate 5).
_RELATIVE_REF_RE = re.compile(r'(?:href|src)\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_EXTERNAL_OR_INERT_RE = re.compile(r"^(https?://|data:|mailto:|tel:|javascript:|//)", re.IGNORECASE)


def guess_content_type(filename: str) -> str:
    ext = os.path.splitext(filename.lower())[1]
    if ext in _SITE_MIME_MAP:
        return _SITE_MIME_MAP[ext]
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".avif"):
        return f"image/{'jpeg' if ext == '.jpg' else ext.lstrip('.')}"
    if ext in (".woff", ".woff2", ".ttf", ".otf"):
        return "font/" + ext.lstrip(".")
    return "application/octet-stream"


def normalize_file_map(files: Optional[Dict[str, str]]) -> Dict[str, str]:
    """
    Validates a repo-style file map: traversal-safe relative paths, posix
    normalization, drops empties. Raises ValueError on path escapes.
    """
    if not files:
        return {}
    normalized: Dict[str, str] = {}
    for raw_path, content in files.items():
        rel = (raw_path or "").replace("\\", "/").lstrip("/").strip()
        if not rel:
            continue
        if _TRAVERSAL_RE.search(rel) or ":" in rel or rel.startswith("/"):
            raise ValueError(f"Site file path escapes the site root: {raw_path!r}")
        if content is None:
            continue
        normalized[rel] = str(content)
    return normalized


async def _mirror_files_to_r2(
    slug: str,
    files: Dict[str, str],
    user_id: Optional[str],
    conversation_id: Optional[str],
) -> Dict[str, str]:
    """
    Best-effort mirror of site files to the R2 GENERATED bucket under
    sites/{slug}/<relpath>. Returns {relpath: public_url}. Failures are
    non-fatal (memory + DB rows carry content).
    """
    from app.services.cloudflare_r2 import upload_file_bytes

    urls: Dict[str, str] = {}
    for rel, content in files.items():
        data: bytes
        if content.startswith("data:"):
            # data URI (bundled binary assets): decode the base64 payload.
            header, _, payload = content.partition(",")
            mime = header[5:].split(";")[0] or "application/octet-stream"
            data = base64.b64decode(payload)
        else:
            mime = guess_content_type(rel)
            data = content.encode("utf-8")
        url = await upload_file_bytes(
            file_bytes=data,
            filename=f"sites/{slug}/{rel}",
            mime_type=mime,
            bucket_type="GENERATED",
        )
        if url:
            urls[rel] = url
    return urls


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
        base_url: str = "",
        files: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Deploys a static site and returns the site metadata and live preview URL.

        Phase 5 (B): `files` maps repo-style relative paths to text content
        ({"index.html": ..., "css/styles.css": ..., "js/main.js": ...}). When a
        file map with index.html is supplied, the site is deployed MULTI-FILE:
        `/{slug}` serves index.html and `/{slug}/{path}` serves any bundled
        file, so relative links resolve. The legacy single-HTML path is
        unchanged and remains valid for snippets and quick mockups.
        """
        slug = generate_slug(title)
        full_html = bundle_html(title=title, html_content=html_content, css_content=css_content, js_content=js_content)
        site_id = str(uuid.uuid4())
        now_iso = datetime.utcnow().isoformat()

        normalized_files = normalize_file_map(files) if files else {}
        if "index.html" not in normalized_files and full_html:
            normalized_files["index.html"] = full_html

        # ── Delivery Gate: bundle integrity (pre-persist) ───────────────────
        # An entry page whose nav links point at files that were never bundled
        # ships a broken preview. Check BEFORE persisting; warnings surface in
        # the deploy result so the caller can fix and redeploy.
        integrity_warnings: List[str] = []
        _entry_html = normalized_files.get("index.html", "")
        if not _entry_html or not _entry_html.strip():
            integrity_warnings.append("index.html is empty — preview will render blank")
        else:
            for _ref in _RELATIVE_REF_RE.findall(_entry_html):
                _clean = _ref.split("#", 1)[0].split("?", 1)[0].strip()
                if not _clean or _EXTERNAL_OR_INERT_RE.match(_clean):
                    continue
                _norm = os.path.normpath(_clean).replace("\\", "/")
                if _norm.startswith(".."):
                    integrity_warnings.append(f"link escapes site root: {_ref}")
                elif _norm.lstrip("/") not in normalized_files:
                    integrity_warnings.append(f"relative link target not bundled: {_ref}")
            if integrity_warnings:
                logger.warning(
                    "Hosted-site bundle integrity warnings for slug=%s: %s", slug, integrity_warnings
                )

        site_record = {
            "id": site_id,
            "slug": slug,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "title": title or "Untitled Site",
            "html_content": full_html,
            "css_content": css_content,
            "js_content": js_content,
            "files": normalized_files,
            "is_public": is_public,
            "view_count": 0,
            "created_at": now_iso,
            "updated_at": now_iso,
        }

        # Best-effort R2 mirror so files survive backend restarts on the CDN.
        # Memory + Supabase rows always carry the content as fallback.
        urls: Dict[str, str] = {}
        if normalized_files:
            try:
                urls = await _mirror_files_to_r2(
                    slug, normalized_files, user_id, conversation_id
                )
                if urls:
                    site_record["files_urls"] = urls

                # Persist site.json metadata to R2 for durable container-restart recovery
                import json
                from app.services.cloudflare_r2 import upload_file_bytes
                meta_bytes = json.dumps(site_record).encode("utf-8")
                await upload_file_bytes(
                    file_bytes=meta_bytes,
                    filename=f"sites/{slug}/site.json",
                    mime_type="application/json",
                    bucket_type="GENERATED",
                )
            except Exception as r2_err:
                logger.warning(f"Hosted-site R2 mirror skipped: {r2_err}")

        # Cache in memory immediately for ultra-fast response
        _MEMORY_HOSTED_SITES[slug] = site_record
        _MEMORY_HOSTED_SITES[site_id] = site_record

        # ── Delivery Gate: preview health-check (read-back) ─────────────────
        # Confirm the preview the URL points at actually serves a non-empty
        # entry page before the caller advertises it as live.
        preview_verified = False
        try:
            _served = _MEMORY_HOSTED_SITES.get(slug)
            preview_verified = bool(
                _served and (_served.get("files") or {}).get("index.html", "").strip()
            )
        except Exception as _pv_err:
            logger.warning(f"Hosted-site preview health-check skipped: {_pv_err}")

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

        effective_base = (base_url or _DEFAULT_BASE_URL).rstrip('/')
        preview_url = f"{effective_base}/v1/sites/{slug}"
        cdn_url = urls.get("index.html") if urls else None

        return {
            "site_id": site_id,
            "slug": slug,
            "title": title or "Untitled Site",
            "preview_url": preview_url,
            "is_public": is_public,
            "created_at": now_iso,
            "files": sorted(normalized_files.keys()),
            "files_urls": urls,
            "multi_file": len(normalized_files) > 1,
            "preview_verified": preview_verified,
            "integrity_warnings": integrity_warnings,
        }

    @staticmethod
    async def get_site_file(
        slug_or_id: str, file_path: str, supabase_client=None
    ) -> Optional[Dict[str, Any]]:
        """
        Retrieves one file of a multi-file hosted site. Returns
        {'content': str, 'content_type': str, 'url': Optional[str]} or None.
        """
        site = await HostedSitesService.get_site(slug_or_id, supabase_client)
        if not site:
            return None
        rel = (file_path or "").replace("\\", "/").lstrip("/")
        if site:
            files = site.get("files") or {}
            if rel in files:
                urls = site.get("files_urls") or {}
                content = files[rel]
                return {
                    "content": content,
                    "content_type": guess_content_type(rel),
                    "url": urls.get(rel),
                }

        # Check R2 fallback directly for sites/{slug_or_id}/{rel}
        try:
            from app.services.cloudflare_r2 import get_r2_client, build_r2_public_url
            s3_client, bucket_name, pub_domain = get_r2_client("GENERATED")
            r2_key = f"sites/{slug_or_id}/{rel}"

            def _fetch_site_file():
                try:
                    resp = s3_client.get_object(Bucket=bucket_name, Key=r2_key)
                    raw_bytes = resp["Body"].read()
                    try:
                        return raw_bytes.decode("utf-8")
                    except Exception:
                        import base64
                        return "data:" + guess_content_type(rel) + ";base64," + base64.b64encode(raw_bytes).decode("ascii")
                except Exception:
                    return None

            body = await asyncio.to_thread(_fetch_site_file)
            if body is not None:
                if site and "files" in site:
                    site["files"][rel] = body
                return {
                    "content": body,
                    "content_type": guess_content_type(rel),
                    "url": build_r2_public_url(pub_domain, r2_key),
                }
        except Exception as r2_err:
            logger.debug(f"R2 get_site_file fallback error: {r2_err}")

        return None

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
                # Validate if slug_or_id is a valid UUID before querying id column
                is_valid_uuid = False
                try:
                    uuid.UUID(str(slug_or_id))
                    is_valid_uuid = True
                except (ValueError, TypeError, AttributeError):
                    is_valid_uuid = False

                def _run_query():
                    tbl = supabase_client.table("hosted_sites").select("*")
                    if is_valid_uuid:
                        return tbl.or_(f"slug.eq.{slug_or_id},id.eq.{slug_or_id}").maybe_single().execute()
                    else:
                        return tbl.eq("slug", str(slug_or_id)).maybe_single().execute()

                res = await asyncio.to_thread(_run_query)
                if res and res.data:
                    _MEMORY_HOSTED_SITES[slug_or_id] = res.data
                    return res.data
            except Exception as db_err:
                logger.warning(f"Supabase get_site query error: {db_err}")

        # 3. Cloudflare R2 persistent storage fallback (container restart resilience)
        try:
            from app.services.cloudflare_r2 import get_r2_client
            import json

            s3_client, bucket_name, _ = get_r2_client("GENERATED")

            def _fetch_from_r2():
                # 3a. Check for sites/{slug_or_id}/site.json
                meta_key = f"sites/{slug_or_id}/site.json"
                try:
                    resp = s3_client.get_object(Bucket=bucket_name, Key=meta_key)
                    raw_bytes = resp["Body"].read()
                    data = json.loads(raw_bytes.decode("utf-8"))
                    if data and isinstance(data, dict):
                        return data
                except Exception:
                    pass

                # 3b. Fallback: Check for sites/{slug_or_id}/index.html
                index_key = f"sites/{slug_or_id}/index.html"
                try:
                    resp = s3_client.get_object(Bucket=bucket_name, Key=index_key)
                    raw_bytes = resp["Body"].read()
                    html = raw_bytes.decode("utf-8", errors="replace")
                    return {
                        "id": str(uuid.uuid4()),
                        "slug": slug_or_id,
                        "title": slug_or_id,
                        "html_content": html,
                        "css_content": "",
                        "js_content": "",
                        "files": {"index.html": html},
                        "is_public": True,
                        "view_count": 1,
                        "created_at": datetime.utcnow().isoformat(),
                    }
                except Exception:
                    pass
                return None

            site_data = await asyncio.to_thread(_fetch_from_r2)
            if site_data:
                _MEMORY_HOSTED_SITES[slug_or_id] = site_data
                _MEMORY_HOSTED_SITES[site_data.get("slug", slug_or_id)] = site_data
                return site_data
        except Exception as r2_err:
            logger.debug(f"R2 get_site fallback error for {slug_or_id}: {r2_err}")

        return None
