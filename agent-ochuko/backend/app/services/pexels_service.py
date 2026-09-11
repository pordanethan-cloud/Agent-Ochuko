# app/services/pexels_service.py
"""
Pexels stock photo service — Phase 5 (tool: fetch_stock_image).

Backs the `fetch_stock_image` tool. Contract notes (verify against
https://www.pexels.com/api/documentation/ when network allows — docs page
returned 403 to the fetcher during implementation):

  - Auth: header `Authorization: <PEXELS_API_KEY>` (raw key, no Bearer prefix)
  - GET /v1/search?query=&per_page=&page=&orientation=&size=&color=
  - Photo object: id, width, height, url (page), photographer, avg_color, alt,
    src.{original, large2x, large, medium, small, portrait, landscape, tiny}

Output is normalized for the model: a compact list of candidates with direct
image URLs + attribution, ready to embed via standard markdown image syntax.
The tool NEVER returns base64 blobs — hotlink the src.large2x/large URLs.
"""
import logging
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

PEXELS_BASE = "https://api.pexels.com/v1"
_DEFAULT_PER_PAGE = 6
_MAX_PER_PAGE = 15
_TIMEOUT = httpx.Timeout(15.0, connect=8.0)


class PexelsService:
    """Thin async client over the Pexels photo API."""

    def __init__(self, api_key: Optional[str]):
        self._api_key = (api_key or "").strip()
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=_TIMEOUT,
                headers={"Authorization": self._api_key},
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    # ── Public API ────────────────────────────────────────────────────────

    async def search(
        self,
        query: str,
        *,
        per_page: int = _DEFAULT_PER_PAGE,
        page: int = 1,
        orientation: Optional[str] = None,   # landscape | portrait | square
        size: Optional[str] = None,          # small | medium | large
        color: Optional[str] = None,         # name or hex (no #)
    ) -> Dict[str, Any]:
        """Returns {'photos': [...normalized...], 'total_results': int} or {'error': str}."""
        if not self.enabled:
            return {"error": "PEXELS_API_KEY is not configured"}
        per_page = max(1, min(int(per_page or _DEFAULT_PER_PAGE), _MAX_PER_PAGE))
        params: Dict[str, Any] = {"query": query, "per_page": per_page, "page": page}
        if orientation:
            params["orientation"] = orientation
        if size:
            params["size"] = size
        if color:
            params["color"] = color
        try:
            resp = await self._get_client().get(f"{PEXELS_BASE}/search", params=params)
            if resp.status_code == 401:
                return {"error": "Pexels rejected the API key (401)"}
            if resp.status_code == 429:
                return {"error": "Pexels rate limit hit (429) — try again shortly"}
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Pexels search failed for %r: %s", query, exc)
            return {"error": f"Pexels request failed: {exc}"}
        return {
            "photos": [self._normalize(p) for p in data.get("photos", [])],
            "total_results": data.get("total_results", 0),
        }

    async def curated(
        self, *, per_page: int = _DEFAULT_PER_PAGE, page: int = 1
    ) -> Dict[str, Any]:
        if not self.enabled:
            return {"error": "PEXELS_API_KEY is not configured"}
        per_page = max(1, min(int(per_page or _DEFAULT_PER_PAGE), _MAX_PER_PAGE))
        try:
            resp = await self._get_client().get(
                f"{PEXELS_BASE}/curated", params={"per_page": per_page, "page": page}
            )
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Pexels curated failed: %s", exc)
            return {"error": f"Pexels request failed: {exc}"}
        return {
            "photos": [self._normalize(p) for p in data.get("photos", [])],
            "total_results": data.get("total_results", 0),
        }

    # ── Normalization ─────────────────────────────────────────────────────

    @staticmethod
    def _normalize(photo: Dict[str, Any]) -> Dict[str, Any]:
        """Compact, model-friendly candidate: URLs + attribution, no fluff."""
        src = photo.get("src", {}) or {}
        return {
            "id": photo.get("id"),
            "url": src.get("large2x") or src.get("large") or src.get("original"),
            "preview": src.get("medium") or src.get("small"),
            "width": photo.get("width"),
            "height": photo.get("height"),
            "avg_color": photo.get("avg_color"),
            "alt": photo.get("alt") or "",
            "photographer": photo.get("photographer") or "",
            "pexels_page": photo.get("url"),
        }

    @staticmethod
    def format_for_model(result: Dict[str, Any], query: str) -> str:
        """Renders the search result as the tool-reply text for the model."""
        if result.get("error"):
            return f"fetch_stock_image error: {result['error']}"
        photos: List[Dict[str, Any]] = result.get("photos", [])
        if not photos:
            return f"No Pexels results for {query!r}. Suggest adjusting keywords, or use generate_image instead."
        lines = [
            f"Pexels results for {query!r} ({result.get('total_results', '?')} total, showing {len(photos)}).",
            "Embed with standard markdown image syntax using `url`; attribute the photographer:",
        ]
        for i, p in enumerate(photos, 1):
            alt = (p.get("alt") or query).strip()
            lines.append(
                f"{i}. url={p['url']} | {p['width']}x{p['height']} | avg_color={p.get('avg_color')} | "
                f"alt={alt!r} | photographer={p['photographer']!r} | page={p.get('pexels_page')}"
            )
        lines.append(
            "Pick the best match; embed ONLY chosen images, e.g. ![alt](url). "
            "Keep the photographer attribution visible near the image or in a sources line."
        )
        return "\n".join(lines)


# ── Secondary providers (fallback behind Pexels) ─────────────────────────────
# Unsplash: free API, highest quality; auth header `Client-ID <key>`.
# Pixabay:  free API; `key` query param. StockSnap.io / Reshot have no public
# API (scrape-only) — deferred to a future phase rather than scraping.

_UNSPLASH_BASE = "https://api.unsplash.com"
_PIXABAY_BASE = "https://pixabay.com/api"


class UnsplashService:
    """Unsplash search — same normalized result shape as PexelsService."""

    def __init__(self, access_key: Optional[str]):
        self._key = (access_key or "").strip()
        self._client: Optional[httpx.AsyncClient] = None

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()

    async def search(self, query: str, *, per_page: int = _DEFAULT_PER_PAGE,
                     orientation: Optional[str] = None, **_ignored) -> Dict[str, Any]:
        if not self.enabled:
            return {"error": "UNSPLASH_API_KEY is not configured"}
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=_TIMEOUT, headers={"Authorization": f"Client-ID {self._key}"}
            )
        params: Dict[str, Any] = {"query": query, "per_page": min(int(per_page), _MAX_PER_PAGE)}
        if orientation:
            params["orientation"] = orientation
        try:
            resp = await self._client.get(f"{_UNSPLASH_BASE}/search/photos", params=params)
            if resp.status_code == 401:
                return {"error": "Unsplash rejected the API key (401)"}
            if resp.status_code == 429:
                return {"error": "Unsplash rate limit hit (429)"}
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Unsplash search failed for %r: %s", query, exc)
            return {"error": f"Unsplash request failed: {exc}"}
        photos = [
            {
                "id": r.get("id"),
                "url": (r.get("urls", {}) or {}).get("regular") or (r.get("urls", {}) or {}).get("full"),
                "preview": (r.get("urls", {}) or {}).get("small"),
                "width": r.get("width"),
                "height": r.get("height"),
                "avg_color": r.get("color"),
                "alt": (r.get("alt_description") or r.get("description") or ""),
                "photographer": (r.get("user", {}) or {}).get("name") or "",
                "pexels_page": (r.get("links", {}) or {}).get("html"),
            }
            for r in data.get("results", [])
        ]
        return {"photos": photos, "total_results": data.get("total", 0)}


class PixabayService:
    """Pixabay search — photos only, same normalized result shape."""

    def __init__(self, api_key: Optional[str]):
        self._key = (api_key or "").strip()

    @property
    def enabled(self) -> bool:
        return bool(self._key)

    async def aclose(self) -> None:  # parity with the interface
        return None

    async def search(self, query: str, *, per_page: int = _DEFAULT_PER_PAGE,
                     orientation: Optional[str] = None, **_ignored) -> Dict[str, Any]:
        if not self.enabled:
            return {"error": "PIXABAY_API_KEY is not configured"}
        params: Dict[str, Any] = {
            "key": self._key,
            "q": query,
            "per_page": min(int(per_page), _MAX_PER_PAGE),
            "image_type": "photo",
            "safesearch": "true",
        }
        if orientation in ("landscape", "portrait"):
            params["orientation"] = orientation
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                resp = await client.get(_PIXABAY_BASE, params=params)
                if resp.status_code == 429:
                    return {"error": "Pixabay rate limit hit (429)"}
                resp.raise_for_status()
                data = resp.json()
        except httpx.HTTPError as exc:
            logger.warning("Pixabay search failed for %r: %s", query, exc)
            return {"error": f"Pixabay request failed: {exc}"}
        photos = [
            {
                "id": h.get("id"),
                "url": h.get("largeImageURL") or h.get("webformatURL"),
                "preview": h.get("webformatURL"),
                "width": h.get("imageWidth"),
                "height": h.get("imageHeight"),
                "avg_color": None,
                "alt": (h.get("tags") or "").replace(",", ", "),
                "photographer": h.get("user") or "",
                "pexels_page": h.get("pageURL"),
            }
            for h in data.get("hits", [])
        ]
        return {"photos": photos, "total_results": data.get("total", 0)}


# ── Multi-provider aggregator ────────────────────────────────────────────────
# Pexels first, then Unsplash, then Pixabay — first provider with results wins.
# Keys: env var first, then App Config (PEXELS_API_KEY / UNSPLASH_API_KEY /
# PIXABAY_API_KEY), runtime-tunable.

_PROVIDER_CONFIG_KEYS = {
    "pexels": "PEXELS_API_KEY",
    "unsplash": "UNSPLASH_API_KEY",
    "pixabay": "PIXABAY_API_KEY",
}


def _resolve_keys() -> Dict[str, Optional[str]]:
    """Best-effort sync peek: env vars, then the App Config in-memory cache."""
    import os
    keys = {name: os.environ.get(cfg) for name, cfg in _PROVIDER_CONFIG_KEYS.items()}
    try:
        from app.core.config import _CONFIG_CACHE  # type: ignore
        for name, cfg in _PROVIDER_CONFIG_KEYS.items():
            if not keys[name] and _CONFIG_CACHE.get(cfg):
                keys[name] = str(_CONFIG_CACHE[cfg])
    except Exception:
        pass
    return keys


async def _await_config_fallback(keys: Dict[str, Optional[str]]) -> None:
    """Async App Config fallback for any still-missing key."""
    try:
        from app.core.config import get_config
        for name, cfg in _PROVIDER_CONFIG_KEYS.items():
            if not keys.get(name):
                keys[name] = await get_config(cfg, "")
    except Exception:
        pass


async def get_stock_service() -> "MultiStockService":
    """Builds the multi-provider aggregator with keys resolved (env → App Config)."""
    keys = _resolve_keys()
    await _await_config_fallback(keys)
    return MultiStockService(
        pexels=PexelsService(keys.get("pexels")),
        unsplash=UnsplashService(keys.get("unsplash")),
        pixabay=PixabayService(keys.get("pixabay")),
    )


class MultiStockService:
    """Pexels → Unsplash → Pixabay; first provider with results wins."""

    def __init__(self, *, pexels: PexelsService, unsplash: UnsplashService, pixabay: PixabayService):
        self.providers: List[tuple] = [
            ("pexels", pexels), ("unsplash", unsplash), ("pixabay", pixabay)
        ]

    @property
    def enabled(self) -> bool:
        return any(svc.enabled for _name, svc in self.providers)

    async def aclose(self) -> None:
        for _name, svc in self.providers:
            await svc.aclose()

    async def search(self, query: str, **kwargs) -> Dict[str, Any]:
        errors: List[str] = []
        for name, svc in self.providers:
            if not svc.enabled:
                continue
            result = await svc.search(query, **kwargs)
            if result.get("error"):
                errors.append(f"{name}: {result['error']}")
                continue
            if result.get("photos"):
                result["provider"] = name
                return result
        detail = "; ".join(errors) if errors else "no providers configured"
        return {"error": f"All stock providers exhausted ({detail}) — fall back to generate_image"}
