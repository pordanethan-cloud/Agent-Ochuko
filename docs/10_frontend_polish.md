# Phase 10 — Frontend Polish & Mobile Responsiveness

> **Duration**: 3–4 days
> **Depends on**: Phase 2 (core UI), Phase 8 (mode toggle), Phase 9 (voice integration)

---

## 10.1 — ChatGPT-Grade UI Polish (Day 1–2)

- [ ] Dark theme: zinc/slate palette, no pure black (`#000`), subtle borders (`zinc-800`)
- [ ] Message bubbles:
  - User messages: right-aligned with accent color
  - Assistant messages: left-aligned, no background
- [ ] Markdown rendering: full GitHub Flavored Markdown (GFM) support — headings, bold, italic, links, images, tables, blockquotes
- [ ] Code blocks: syntax highlighting (Prism.js or Shiki), language label in top-right corner, one-click copy button
- [ ] LaTeX rendering: KaTeX for inline `$...$` and block `$$...$$` math expressions
- [ ] Streaming cursor: blinking `▌` at the end of the assistant's response while the stream is active
- [ ] Smooth scroll-to-bottom: auto-scroll during streaming, but pause auto-scroll if user manually scrolls up (reading history)
- [ ] Message actions (appear on hover):
  - Copy full message text
  - Regenerate response (re-sends the last user message)
- [ ] Timestamps: show relative time ("2 min ago") by default; hover to reveal exact datetime
- [ ] Empty state: when no conversation is selected, show centered "Start a new chat" prompt with keyboard shortcut hint

---

## 10.2 — Sidebar Polish (Day 2)

- [ ] Conversation list: grouped by **Today | Yesterday | Previous 7 Days | Older**
- [ ] Each item shows: title (auto-generated from first message or user-renamed), last message preview snippet, relative time
- [ ] Inline rename: click conversation title → editable text field → blur or Enter to save
- [ ] Delete: right-click context menu (desktop) or swipe left (mobile) → confirmation dialog → soft delete (`DELETE /v1/conversations/{id}`)
- [ ] Search: filter conversations by title or message content (Supabase full-text search via `textsearch`)
- [ ] "Show archived" toggle at the bottom — loads conversations where `is_archived = TRUE`
- [ ] New chat button: prominent, at the top of the sidebar

---

## 10.3 — Mobile Responsive (Day 2–3)

- [ ] Breakpoints: mobile (< 768px), tablet (768–1024px), desktop (> 1024px)
- [ ] **Mobile layout**:
  - Sidebar collapsed by default — hamburger menu opens it as a full-screen overlay
  - No artifact panel (hidden via `useMediaQuery`)
  - Input bar: full width, voice button + attach button compact-sized
  - Mode toggle: compact pill selector above input bar
  - Messages: full width, minimal horizontal padding
- [ ] **Tablet layout**:
  - Sidebar as collapsible drawer (pushes content rather than overlays)
  - Artifact panel hidden (only on desktop 1024px+)
- [ ] **Desktop layout**:
  - Sidebar always visible (resizable, 250px default width)
  - Artifact panel appears as right 50% split when artifact HTML/React content is detected in assistant response
- [ ] **DOM virtualization** for long message histories: only render messages in/near the viewport
  - Use `react-virtuoso` or equivalent — prevents memory bloat on 200+ message conversations
- [ ] **Infinite scroll**: load messages in pages of 50, fetch more on scroll-up

---

## 10.4 — Keyboard Shortcuts (Day 3)

- [ ] `Ctrl/Cmd + K` → focus search in sidebar
- [ ] `Ctrl/Cmd + Shift + N` → new conversation
- [ ] `Enter` → send message
- [ ] `Shift + Enter` → newline in input (do NOT send)
- [ ] `Ctrl/Cmd + Shift + V` → toggle voice input
- [ ] `Escape` → close artifact panel / close sidebar on mobile
- [ ] `Ctrl/Cmd + 1` → switch to THINK mode
- [ ] `Ctrl/Cmd + 2` → switch to SOLVE mode
- [ ] `Ctrl/Cmd + 3` → switch to DISCUSS mode

---

## 10.5 — PWA Configuration (Day 3–4)

- [ ] `manifest.json`: app name `"Agent Ochuko"`, icons from `AGENT ochuko(icon,favcon,img).png`, `theme_color`, `background_color`, `display: "standalone"`
- [ ] Service worker (via Vite PWA plugin): cache app shell (HTML/CSS/JS) for offline-capable load
- [ ] Show "You're offline" banner when network is unavailable
- [ ] iOS: add `apple-touch-icon` meta tags to `index.html`
- [ ] "Install app" browser prompt on supported browsers (Chrome, Edge)

---

## Milestone

Production-quality chat interface. Indistinguishable from ChatGPT in look and feel. Responsive across all devices. Keyboard-navigable. Installable as PWA on desktop and mobile.

---

## Considerations

> Items from the implementation plan relevant to this phase that require additional context.

### Artifact Panel Detection Logic

The implementation plan (Section 9) shows that `ArtifactPanel.tsx` renders only on desktop (`min-width: 1024px`). The trigger for opening the artifact panel — detecting HTML or React code in the assistant response — needs to be implemented in `ChatWindow.tsx` or `MessageBubble.tsx`. Specifically:
- Parse the assistant message for fenced code blocks with `language = 'html'` or `language = 'jsx'`/`'tsx'`
- If found → set artifact panel content and display it on the right split
- Include a "Close artifact" button that collapses the panel

### Conversation Search Implementation

Full-text search requires a Postgres `tsvector` index on `conversations.title` and `messages.content`. Add this before 10.2:
```sql
CREATE INDEX idx_conversations_fts ON conversations USING gin(to_tsvector('english', title));
CREATE INDEX idx_messages_fts ON messages USING gin(to_tsvector('english', content));
```
The search endpoint can use Supabase's `textSearch()` client method or a raw RPC.

### Conversation Title Auto-Generation

Phase 10.2 mentions auto-generated titles "from first message." This auto-generation is not defined as an endpoint in the implementation plan. Consider calling GPT-5.4 Nano after the first assistant response to generate a short title (5–8 words), then `PATCH /v1/conversations/{id}` with `{title: "..."}`. This should be a background task — not in the streaming hot path.

### PWA Service Worker and SSE Compatibility

Service workers can intercept and cache network requests. Ensure the service worker is configured to **never cache** the SSE streaming endpoint (`/v1/responses/stream`) — caching an event stream will break streaming entirely. Use a `networkOnly` strategy for all `/v1/*` API routes in the service worker config.

### Vite PWA Plugin

Use `vite-plugin-pwa` for zero-config PWA integration with Vite. Add to `frontend/package.json`:
```
npm install -D vite-plugin-pwa
```
Configure in `vite.config.ts` with `registerType: 'autoUpdate'` and `runtimeCaching` rules.
