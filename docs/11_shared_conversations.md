# Phase 11 — Shared Conversations & Guest View

> **Duration**: 1–2 days
> **Depends on**: Phase 2 (frontend routing and message rendering), Phase 1 (backend routes for `/v1/shared/*`)

---

## 11.1 — Share Flow (Day 1)

- [ ] Add **Share button** to the conversation header (desktop) or context menu (mobile)
- [ ] Click → `PATCH /v1/conversations/{id}` with `{is_shared: true}` → backend returns the `share_token`
- [ ] Generate the shareable URL: `https://agent-ochuko.azurestaticapps.net/shared/{share_token}`
- [ ] Copy URL to clipboard automatically on share → show toast "Link copied!"
- [ ] Show the share link in a dismissable modal so the user can also manually copy it
- [ ] **Unshare button**: same modal → `PATCH /v1/conversations/{id}` with `{is_shared: false}` → existing links immediately return `404`

---

## 11.2 — Guest View Page (Day 1–2)

- [ ] Route: `/shared/:token` — **no authentication required**
- [ ] Backend: `GET /v1/shared/{share_token}` → returns conversation title + all messages (uses RLS `convos_shared` policy)
- [ ] Read-only rendered view:
  - Same message bubble styling, markdown rendering, code syntax highlighting as the main chat
  - No input bar, no sidebar, no mode toggle — pure read-only display
- [ ] Watermark at top: "Exported from Agent Ochuko"
- [ ] **Export to JSON** button: downloads full conversation as a structured JSON file
  ```json
  {
    "title": "Conversation about async Python",
    "exported_at": "2026-06-27T22:00:00Z",
    "messages": [
      {"role": "user", "content": "..."},
      {"role": "assistant", "content": "..."}
    ]
  }
  ```
- [ ] **SEO**: page title = conversation title, meta description = first 160 chars of first assistant message

---

## Milestone

Users can share any conversation via a single link. Recipients see a polished read-only view without needing an account. Conversation can be exported as JSON at any time.

---

## Considerations

> Items from the implementation plan relevant to this phase that require additional context.

### `GET /v1/shared/{share_token}` Must Be Unauthenticated

This endpoint is explicitly marked as "no auth required" (implementation plan Section 7). The middleware stack must allow this route through **without** running `JWTValidatorMiddleware`. Add this path to the JWT middleware's bypass list (e.g., a `PUBLIC_PATHS` set in `jwt_validator.py`):
```python
PUBLIC_PATHS = {"/health", "/ready", "/v1/shared/"}

# In middleware:
if any(request.url.path.startswith(p) for p in PUBLIC_PATHS):
    await call_next(request)
    return
```

### RLS for Shared Conversations Includes Messages

The `msgs_shared` RLS policy (implementation plan Section 6) allows reading messages for shared conversations:
```sql
CREATE POLICY "msgs_shared" ON messages FOR SELECT USING (
  conversation_id IN (SELECT id FROM conversations WHERE is_shared = TRUE)
);
```
Confirm this policy is present in the production Supabase project. It is defined in the full schema but may be missing from `03_supabase_setup.md` Migration 002 (which uses a simplified policy set).

### `exports` Blob Container vs JSON Download

The implementation plan mentions an `exports` Supabase Storage bucket for sharing. However, the JSON export button described in 11.2 generates the file client-side (no server round-trip needed) and triggers a browser download. The `exports` bucket in Azure Blob Storage is intended for larger exported files if server-side generation is needed. For Phase 11, client-side JSON generation is sufficient — the `exports` bucket may be used in a future enhancement for PDF exports.

### Archived Messages in Guest View

The guest view calls `GET /v1/shared/{share_token}` which returns all messages. Decide whether to include `is_archived_msg = TRUE` messages in the shared view:
- **Include all** (recommended): the guest sees the full history as the owner does
- **Exclude archived**: the guest only sees the compacted/recent context

The implementation plan says the guest view returns "all messages" (Section 11.2), so include archived messages in the shared endpoint response.
