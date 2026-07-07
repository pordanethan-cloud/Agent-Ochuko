# Phase 10 â€” Frontend Polish & Mobile Responsiveness

> **Duration**: 3â€“4 days
> **Depends on**: Phase 2 (core UI), Phase 8 (mode toggle), Phase 9 (voice integration)
> **Last updated**: 2026-07-07 â€” reflects agentic loop transition (Phases 1â€“4) and Cloudflare R2 storage migration

---

## 10.1 â€” ChatGPT-Grade UI Polish (Day 1â€“2)

- [x] Dark theme: deep `#08090a` background, `#1e2025` borders â€” custom brand palette, not generic zinc
- [x] Message bubbles:
  - User messages: right-aligned, `#1c1e22` background with `#2b2e35` border
  - Assistant messages: left-aligned, transparent background (`bg-transparent`)
- [x] Markdown rendering: full GFM support â€” headings (H1â€“H6), bold, italic, inline code, links, blockquotes, tables, ordered/unordered lists, fenced code blocks (`parseMarkdownToBlocks` AST parser)
- [x] Code blocks: language label in top-left, one-click **Copy** button (clipboard API) â€” `CodeBlock` component
- [ ] LaTeX rendering: KaTeX for inline `$...$` and block `$$...$$` math expressions *(pending)*
- [x] Streaming cursor: bouncing dots (`dot-bounce`) appear before first token; replaced by content as it arrives
- [x] Smooth scroll-to-bottom: auto-scroll locked to bottom during streaming; pauses when user scrolls up (`isAutoScrollEnabledRef`)
- [x] Message actions (appear on hover):
  - Copy full message text
  - Edit user message (re-sends truncated history)
  - TTS listen / stop per message
- [x] Timestamps: show relative time ("2m ago", "3h ago") on hover; `title` attr reveals exact datetime
- [x] Empty state: blank canvas with Ochuko branding and input focus on mount

---

## 10.2 â€” Sidebar Polish (Day 2)

- [x] Conversation list: shows all sessions with title, mode badge
- [x] Each item: title, delete button, active session highlight
- [x] Delete: trash icon â†’ `DELETE /v1/conversations/{id}` with confirmation (`convoToDelete` state)
- [x] New chat button at top of sidebar
- [x] Slide-out sidebar drawer with hover-to-reveal zone (left-edge 12px trigger)
- [x] Grouped by **Today | Yesterday | This Week | Older** — date-bucketed sidebar grouping
- [ ] Inline rename: click title â†’ editable field â†’ blur/Enter to save *(pending)*
- [ ] Search conversations by title/content *(pending â€” see SQL note below)*
- [ ] "Show archived" toggle *(pending)*

---

## 10.3 â€” Mobile Responsive (Day 2â€“3)

- [x] Mobile: sidebar collapsed by default, hamburger opens it; backdrop overlay on open
- [x] Input bar: full width, compact voice + attach buttons
- [x] Mode toggle: THINK / SOLVE / DISCUSS pill at bottom
- [ ] Tablet layout: sidebar as collapsible drawer (pushes content rather than overlays) *(pending)*
- [ ] Desktop: sidebar resizable (currently fixed width 256px) *(pending)*
- [ ] Artifact panel right-split for HTML/JSX code blocks *(pending)*
- [ ] DOM virtualization for 200+ message histories (`react-virtuoso`) *(pending)*
- [ ] Infinite scroll: load messages in pages of 50, fetch more on scroll-up *(pending)*

---

## 10.4 — Keyboard Shortcuts (Day 3)

- [x] `Ctrl/Cmd + K` → focus search in sidebar
- [x] `Ctrl/Cmd + Shift + N` → new conversation
- [x] `Enter` → send message
- [x] `Shift + Enter` → newline in input (does NOT send)
- [x] `Ctrl/Cmd + Shift + V` → toggle voice input
- [x] `Escape` → close sidebar on mobile
- [x] `Ctrl/Cmd + 1/2/3` → switch THINK / SOLVE / DISCUSS

---

## 10.5 — PWA Configuration (Day 3–4)

- [ ] `manifest.json`: app name `"Agent Ochuko"`, icons, `theme_color`, `display: "standalone"` *(pending)*
- [ ] Service worker (via `vite-plugin-pwa`): cache app shell for offline-capable load *(pending)*
- [ ] Show "You're offline" banner when network unavailable *(pending)*
- [ ] iOS: `apple-touch-icon` meta tags in `index.html` *(pending)*
- [ ] "Install app" browser prompt on Chrome/Edge *(pending)*

---

## 10.6 â€” Agentic UX (Added 2026-07-07) âœ“ COMPLETE

All items below were implemented as part of the OODA loop transition (Phases 1â€“4 today).

- [x] **`AgentStepIndicator`** component: spinning ring + `Step N / MAX` pill inside assistant bubble during multi-step tool loops
- [x] **`agent_step` SSE event**: emitted at start of every OODA iteration; frontend updates step counter live
- [x] **`memory_written` SSE event**: toast notification `"Remembered: key"` flashes when `write_memory` tool fires
- [x] **`write_memory` tool**: model stores key-value facts to `conversations.agent_memory` (JSONB) â€” persists across turns
- [x] **`read_file` tool**: model fetches user-uploaded files from **Cloudflare R2** public domain URL and reads text into context
- [x] **Agent memory injection**: `build_llm_context` prepends a `--- AGENT MEMORY ---` system block on every turn
- [x] **Agent planner**: pre-loop nano call for complex goals (THINK/SOLVE mode) decomposes task into numbered steps injected into system prompt
- [x] **Max iteration cap**: configurable per mode via Azure App Config (`MAX_AGENT_ITERS_THINK`, `MAX_AGENT_ITERS_SOLVE`, etc.)

---

## 10.7 â€” Cloudflare R2 Storage (Added 2026-07-07) âœ“ COMPLETE

Storage fully migrated from Azure Blob Storage to Cloudflare R2.

- [x] `app/services/cloudflare_r2.py`: S3-compatible boto3 client generating presigned `PUT` URLs
- [x] `files.py` `/v1/files/upload`: validates extension, generates R2 presigned URL, returns `blob_url` as `R2_PUBLIC_DOMAIN/uploads/{user}/{convo}/{file}`
- [x] Frontend (`Dashboard.tsx`): detects `blob.core.windows.net` vs R2 and sets `x-ms-blob-type` header only for Azure â€” R2 PUT works without it
- [x] `read_file` agent tool: fetches from `blob_url` (R2 public domain) via `httpx.AsyncClient` â€” no SAS tokens needed for public reads
- [x] Required env vars: `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_ENDPOINT`, `R2_BUCKET_NAME`, `R2_PUBLIC_DOMAIN`

---

## Milestone

Production-quality agentic chat interface. Autonomous multi-step reasoning with live step visibility. Cloudflare R2 file storage. Voice I/O. Keyboard-navigable. Responsive across mobile/tablet/desktop. Installable as PWA *(PWA pending)*.

---

## Considerations

### Conversation Search Implementation

Full-text search requires a Postgres `tsvector` index on `conversations.title` and `messages.content`. Run before implementing 10.2 search:
```sql
CREATE INDEX idx_conversations_fts ON conversations USING gin(to_tsvector('english', title));
CREATE INDEX idx_messages_fts ON messages USING gin(to_tsvector('english', content));
```
The search endpoint uses Supabase's `textSearch()` client method or a raw RPC.

### Conversation Title Auto-Generation

Phase 10.2 mentions auto-generated titles "from first message." Current behaviour: title is set to first 30 chars of user message at conversation creation. Proper implementation: call GPT-5.4 Nano after first assistant response to generate a 5â€“8 word title, then `PATCH /v1/conversations/{id}` with `{title: "..."}`. Must be a background task â€” not in the streaming hot path.

### PWA Service Worker and SSE Compatibility

Service workers can intercept and cache network requests. Ensure the service worker is configured to **never cache** the SSE streaming endpoint (`/v1/responses/stream`) â€” caching an event stream breaks streaming entirely. Use a `networkOnly` strategy for all `/v1/*` API routes:
```js
// vite-plugin-pwa runtimeCaching rule
{ urlPattern: /\/v1\/.*/, handler: 'NetworkOnly' }
```

### Vite PWA Plugin

Use `vite-plugin-pwa` for zero-config PWA integration. Add to `frontend/`:
```
npm install -D vite-plugin-pwa
```
Configure in `vite.config.ts` with `registerType: 'autoUpdate'` and `runtimeCaching` rules for `/v1/*`.

### Cloudflare R2 â€” CORS for Direct Client Upload

The R2 bucket must have a CORS rule allowing `PUT` from the frontend origin:
```json
[{
  "AllowedOrigins": ["https://your-frontend-domain.com"],
  "AllowedMethods": ["PUT", "GET"],
  "AllowedHeaders": ["Content-Type"],
  "MaxAgeSeconds": 3600
}]
```
Set via Cloudflare Dashboard â†’ R2 â†’ Bucket â†’ Settings â†’ CORS, or via `wrangler r2 bucket cors put`.

### Agent Memory Column â€” Supabase RLS

The `conversations.agent_memory` column is written by the backend service role (bypasses RLS). Ensure the column is **not** exposed to the Supabase anon key via the API schema â€” the agent_memory is internal state and should never be readable by the frontend directly.


