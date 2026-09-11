# app/services/artifact_kv.py
"""
Artifact persistent K-V storage — Phase 5 (item #15).

Supabase-backed key-value store scoped per user or shared per conversation.
Exposed to widgets via the visualize__read_me docs and the widget-iframe
postMessage bridge (same protocol as height/prompt).

Schema (Supabase):
    artifact_kv(
        id          uuid DEFAULT gen_random_uuid() PRIMARY KEY,
        scope       text NOT NULL,          -- 'personal' | 'conversation'
        scope_id    text NOT NULL,          -- user_id or conversation_id
        key         text NOT NULL,
        value       text NOT NULL,          -- JSON string, max 5 MB
        updated_at  timestamptz DEFAULT now()
    )
    UNIQUE(scope, scope_id, key)
    RLS: personal rows readable only by owner (user_id = auth.uid());
         conversation rows readable by any member of the conversation.

All functions are async and degrade gracefully when Supabase is unavailable
(in-memory fallback keeps the API usable in local dev).
"""
import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("app.services.artifact_kv")

# In-memory fallback for local dev / network failures
_MEM: Dict[str, str] = {}  # key = f"{scope}:{scope_id}:{key}" → value

_MAX_VALUE_BYTES = 5 * 1024 * 1024  # 5 MB cap enforced server-side


def _mem_key(scope: str, scope_id: str, key: str) -> str:
    return f"{scope}:{scope_id}:{key}"


def _validate(scope: str, scope_id: str, key: str, value: Optional[str] = None) -> None:
    if scope not in ("personal", "conversation"):
        raise ValueError(f"Invalid scope {scope!r}; must be 'personal' or 'conversation'")
    if not scope_id or not key:
        raise ValueError("scope_id and key must be non-empty strings")
    if value is not None and len(value.encode("utf-8")) > _MAX_VALUE_BYTES:
        raise ValueError(
            f"Value exceeds 5 MB limit ({len(value.encode('utf-8'))} bytes)"
        )


async def kv_get(
    scope: str,
    scope_id: str,
    key: str,
    supabase_client=None,
) -> Optional[str]:
    """Retrieve a value. Returns None when the key does not exist."""
    _validate(scope, scope_id, key)
    if supabase_client:
        try:
            res = await asyncio.to_thread(
                lambda: supabase_client.table("artifact_kv")
                .select("value")
                .eq("scope", scope)
                .eq("scope_id", scope_id)
                .eq("key", key)
                .maybe_single()
                .execute()
            )
            if res and res.data:
                return res.data["value"]
            return None
        except Exception as exc:
            logger.warning("artifact_kv get failed (using memory): %s", exc)
    return _MEM.get(_mem_key(scope, scope_id, key))


async def kv_set(
    scope: str,
    scope_id: str,
    key: str,
    value: str,
    supabase_client=None,
) -> None:
    """Upsert a value (last-write-wins). value must be a valid JSON string."""
    _validate(scope, scope_id, key, value)
    # Validate JSON at the boundary
    try:
        json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError(f"artifact_kv value must be valid JSON: {exc}") from exc

    _MEM[_mem_key(scope, scope_id, key)] = value  # memory always updated

    if supabase_client:
        try:
            await asyncio.to_thread(
                lambda: supabase_client.table("artifact_kv")
                .upsert(
                    {
                        "scope": scope,
                        "scope_id": scope_id,
                        "key": key,
                        "value": value,
                    },
                    on_conflict="scope,scope_id,key",
                )
                .execute()
            )
        except Exception as exc:
            logger.warning("artifact_kv set failed (memory-only): %s", exc)


async def kv_delete(
    scope: str,
    scope_id: str,
    key: str,
    supabase_client=None,
) -> bool:
    """Delete a key. Returns True if the key existed."""
    _validate(scope, scope_id, key)
    mk = _mem_key(scope, scope_id, key)
    existed = mk in _MEM
    _MEM.pop(mk, None)

    if supabase_client:
        try:
            res = await asyncio.to_thread(
                lambda: supabase_client.table("artifact_kv")
                .delete()
                .eq("scope", scope)
                .eq("scope_id", scope_id)
                .eq("key", key)
                .execute()
            )
            existed = existed or bool(res and res.data)
        except Exception as exc:
            logger.warning("artifact_kv delete failed: %s", exc)

    return existed


async def kv_list(
    scope: str,
    scope_id: str,
    prefix: str = "",
    supabase_client=None,
) -> List[Dict[str, Any]]:
    """
    List all keys under (scope, scope_id), optionally filtered by key prefix.
    Returns [{"key": str, "size_bytes": int}, ...] ordered by key.
    """
    _validate(scope, scope_id, key="__list__")  # validates scope/scope_id only

    rows: List[Dict[str, Any]] = []

    if supabase_client:
        try:
            query = (
                supabase_client.table("artifact_kv")
                .select("key, value")
                .eq("scope", scope)
                .eq("scope_id", scope_id)
            )
            if prefix:
                query = query.like("key", f"{prefix}%")
            res = await asyncio.to_thread(lambda: query.execute())
            if res and res.data:
                rows = [
                    {
                        "key": row["key"],
                        "size_bytes": len((row.get("value") or "").encode("utf-8")),
                    }
                    for row in res.data
                ]
        except Exception as exc:
            logger.warning("artifact_kv list failed (falling back to memory): %s", exc)

    if not rows:
        # Memory fallback
        pfx = f"{scope}:{scope_id}:"
        for mk, v in _MEM.items():
            if mk.startswith(pfx):
                k = mk[len(pfx):]
                if not prefix or k.startswith(prefix):
                    rows.append({"key": k, "size_bytes": len(v.encode("utf-8"))})

    rows.sort(key=lambda r: r["key"])
    return rows
