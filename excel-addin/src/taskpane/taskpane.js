/**
 * taskpane.js — Agent Ochuko Excel Add-in (Phase 2 + Phase 3)
 *
 * Auth:         Google OAuth via Supabase (Office.js dialog popup)
 * Chat:         SSE streaming — POST /v1/responses/stream
 * Web Search:   Toggle — mode "think" (off) / "solve" (on)
 * Excel Interop: Read selection, write formulas/tables, watch SelectionChanged
 * Markdown:     Rich rendering via markdown.js
 * Quick Actions: Per-mode contextual buttons
 * Modes:
 *   Teacher — Builds mastery: concept → breakdown → example → mastery check
 *   Solver  — Saves time: direct answer, expert-to-expert, no padding
 */
"use strict";

/* ═══════════════════════════════════════════════
   CONFIG
═══════════════════════════════════════════════ */
const CONFIG = {
  SUPABASE_URL:      "https://mghydfaiggngeaspeotd.supabase.co",
  SUPABASE_ANON_KEY: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Im1naHlkZmFpZ2duZ2Vhc3Blb3RkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODI0MjQ2MDksImV4cCI6MjA5ODAwMDYwOX0.TyzDZ5SbLcPx7CE4FtWJvoAIPBJcxN8uIyP1XTc6Nh0",
  API_URL:           "https://agent-ochuko-api.azurecontainerapps.io",
  OAUTH_CALLBACK:    "https://agentochukostore.z1.web.core.windows.net/addin/src/auth/callback.html",
};

/* ═══════════════════════════════════════════════
   MODE — SYSTEM PROMPTS
═══════════════════════════════════════════════ */
const TEACHER_PROMPT = `You are Ochuko in Teacher Mode. Your mission is to build genuine, lasting mastery — not just give answers.

Rules:
1. Always explain the WHY before the WHAT — the concept before the formula or solution.
2. Break every complex idea into its simplest parts first (first principles thinking).
3. Use concrete analogies and real-world examples the user can picture and relate to.
4. Show your reasoning step by step — make invisible thinking fully visible.
5. After every explanation, provide a hands-on practical example using the data if available.
6. End EVERY response with a short "Mastery Check" section — one question that tests whether the concept truly landed.
7. For Excel formulas: explain what each argument does before revealing the full formula.
8. Suggest one small experiment the user can try next to deepen their understanding.
9. Never assume prior knowledge — always build from what the user has shown they know.
10. If the user makes a mistake, guide them to discover the fix themselves through questions.

Tone: warm, encouraging, curious. Like a brilliant friend who knows everything and genuinely loves to teach.
Format each response as: Context & Why → Step-by-Step Breakdown → Concrete Example → Mastery Check question`;

const SOLVER_PROMPT = `You are Ochuko in Solver Mode. The user has mastered the fundamentals. Respect their time above all else.

Rules:
1. Lead with the answer — formula, code, or solution first, always, no exceptions.
2. Maximum one sentence of context unless the user explicitly asks for more detail.
3. Use bullet points and tight structure for speed and scannability.
4. If multiple approaches exist, list them ranked by best fit with a one-word reason each.
5. Assume expert-level understanding — skip definitions, analogies, and basics entirely.
6. No filler phrases, no preamble, no "great question!", no unnecessary affirmations.
7. For Excel: give the formula directly with argument labels only where genuinely ambiguous.
8. If something is wrong, say exactly what and give the fix — no hedging.

Tone: precise, confident, peer-to-peer. Like texting a senior colleague who needs a quick answer right now.`;

/* ═══════════════════════════════════════════════
   QUICK ACTIONS — PER MODE
═══════════════════════════════════════════════ */
const QUICK_ACTIONS = {
  teacher: [
    { action: "tp-explain",   label: "Explain"    },
    { action: "tp-breakdown", label: "Breakdown"  },
    { action: "tp-analogy",   label: "Analogy"    },
    { action: "tp-practice",  label: "Practice"   },
    { action: "tp-compare",   label: "Compare"    },
  ],
  solver: [
    { action: "analyze",      label: "Analyze"    },
    { action: "formula",      label: "Formula"    },
    { action: "explain",      label: "Explain"    },
    { action: "clean",        label: "Clean"      },
    { action: "chart",        label: "Chart"      },
  ],
};

const QUICK_PROMPTS = {
  // Solver mode
  analyze:       "Analyze the selected data and give me key insights, trends, and any anomalies.",
  formula:       "Suggest the most useful Excel formulas I can use with this data. Include examples.",
  explain:       "", // special: reads cell formula
  clean:         "Identify any data quality issues in the selected range: blanks, inconsistencies, duplicates, or formatting problems.",
  chart:         "Based on the selected data, recommend the best chart type and explain why. Include configuration tips.",
  // Teacher mode
  "tp-explain":   "Explain what is happening in the selected cells from first principles. Start with the concept before the mechanics.",
  "tp-breakdown": "Break down step by step exactly what is happening in the selected cells. Make every piece of invisible thinking visible.",
  "tp-analogy":   "Give me a memorable, intuitive analogy that makes the core concept in the selected content click without needing technical background.",
  "tp-practice":  "Create a short, hands-on practice exercise based on the selected data so I can test my understanding of the underlying concept.",
  "tp-compare":   "Compare the approach shown in the selected cells to alternative approaches. Explain the tradeoffs in plain language.",
};

/* ═══════════════════════════════════════════════
   STATE
═══════════════════════════════════════════════ */
const S = {
  jwt:           null,
  email:         "",
  convId:        null,
  history:       [],
  streaming:     false,
  webSearch:     false,
  mode:          "teacher",  // "teacher" | "solver"
  selectionData: null,
  selDismissed:  false,
  lastRawText:   "",
  lastUserMsg:   "",
};

/* ═══════════════════════════════════════════════
   OFFICE BOOTSTRAP
═══════════════════════════════════════════════ */
Office.onReady((info) => {
  if (info.host !== Office.HostType.Excel) return;
  loadState();
  loadMode();
  bindEvents();
  S.jwt ? showApp() : showAuth();
});

/* ═══════════════════════════════════════════════
   PERSISTENCE
═══════════════════════════════════════════════ */
function loadState() {
  try {
    S.jwt       = ls("ochuko_jwt");
    S.email     = ls("ochuko_email") || "";
    S.convId    = ls("ochuko_conv")  || null;
    S.webSearch = ls("ochuko_wsrch") === "1";
  } catch (_) {}
}
function saveState() {
  try {
    if (S.jwt)    set_ls("ochuko_jwt",   S.jwt);
    if (S.email)  set_ls("ochuko_email", S.email);
    if (S.convId) set_ls("ochuko_conv",  S.convId);
    set_ls("ochuko_wsrch", S.webSearch ? "1" : "0");
  } catch (_) {}
}
function loadMode() {
  try { S.mode = ls("ochuko_mode") || "teacher"; } catch (_) {}
}
function saveMode() {
  try { set_ls("ochuko_mode", S.mode); } catch (_) {}
}
function clearSession() {
  try {
    ["ochuko_jwt", "ochuko_email", "ochuko_conv"].forEach(k => localStorage.removeItem(k));
  } catch (_) {}
  S.jwt = null; S.email = ""; S.convId = null; S.history = [];
}
function ls(k)        { return localStorage.getItem(k); }
function set_ls(k, v) { localStorage.setItem(k, v); }

/* ═══════════════════════════════════════════════
   SYSTEM PROMPT
═══════════════════════════════════════════════ */
function buildSystemPrompt() {
  return S.mode === "teacher" ? TEACHER_PROMPT : SOLVER_PROMPT;
}

/* ═══════════════════════════════════════════════
   SCREEN HELPERS
═══════════════════════════════════════════════ */
function showAuth() {
  $("auth-screen").style.display = "flex";
  $("app-screen").classList.remove("active");
  $("auth-err").classList.add("hidden");
  $("auth-err").textContent = "";
  setGoogleBtnLoading(false);
}

function showApp() {
  $("auth-screen").style.display = "none";
  $("app-screen").classList.add("active");
  $("s-email").value = S.email;
  applyToggleUI();
  applyModeUI();
  renderQuickActions();
  watchSelection();
  captureSelection().then(sel => {
    if (sel && !S.selDismissed) { S.selectionData = sel; updateSelectionPill(sel); }
  });
}

/* ═══════════════════════════════════════════════
   MODE — SWITCH & APPLY
═══════════════════════════════════════════════ */
function switchMode(mode) {
  if (S.mode === mode) return;
  S.mode = mode;
  saveMode();
  applyModeUI();
  renderQuickActions();
  // Update welcome block if still visible
  const wb = $("welcome-block");
  if (wb) updateWelcomeBlock(wb);
  toast(mode === "teacher" ? "Teacher Mode — building your mastery" : "Solver Mode — saving your time");
}

function applyModeUI() {
  const body = document.body;
  body.classList.toggle("mode-teacher", S.mode === "teacher");
  body.classList.toggle("mode-solver",  S.mode === "solver");

  // Segmented toggle state
  document.querySelectorAll(".mode-seg").forEach(seg => {
    seg.classList.toggle("active", seg.dataset.mode === S.mode);
  });
}

/* ═══════════════════════════════════════════════
   QUICK ACTIONS — RENDER
═══════════════════════════════════════════════ */
function renderQuickActions() {
  const container = $("quick-actions");
  if (!container) return;
  container.innerHTML = "";
  QUICK_ACTIONS[S.mode].forEach(({ action, label }) => {
    const btn = document.createElement("button");
    btn.className = "quick-btn";
    btn.dataset.action = action;
    btn.textContent = label;
    btn.addEventListener("click", () => quickAction(action));
    container.appendChild(btn);
  });
}

/* ═══════════════════════════════════════════════
   EVENTS
═══════════════════════════════════════════════ */
function bindEvents() {
  $("btn-google-login").addEventListener("click", doGoogleLogin);
  $("btn-send").addEventListener("click", doSend);
  $("chat-input").addEventListener("keydown", e => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") { e.preventDefault(); doSend(); }
  });
  $("chat-input").addEventListener("input", autoResize);
  $("toggle-search-track").addEventListener("click", toggleSearch);
  $("sel-dismiss").addEventListener("click", () => {
    S.selDismissed  = true;
    S.selectionData = null;
    $("selection-pill").classList.add("hidden");
  });
  // Mode toggle segments
  document.querySelectorAll(".mode-seg").forEach(seg => {
    seg.addEventListener("click", () => switchMode(seg.dataset.mode));
  });
  $("btn-settings-open").addEventListener("click",  openSettings);
  $("btn-settings-close").addEventListener("click", closeSettings);
  $("settings-overlay").addEventListener("click", e => {
    if (e.target === $("settings-overlay")) closeSettings();
  });
  $("btn-new-chat").addEventListener("click", newChat);
  $("btn-signout").addEventListener("click",  doSignOut);
}

function $(id) { return document.getElementById(id); }

/* ═══════════════════════════════════════════════
   GOOGLE OAUTH
═══════════════════════════════════════════════ */
function doGoogleLogin() {
  setGoogleBtnLoading(true);
  $("auth-err").classList.add("hidden");

  const params = new URLSearchParams({
    provider:    "google",
    redirect_to: CONFIG.OAUTH_CALLBACK,
    access_type: "offline",
    prompt:      "consent",
    scopes:      "https://www.googleapis.com/auth/drive.file",
  });

  Office.context.ui.displayDialogAsync(
    `${CONFIG.SUPABASE_URL}/auth/v1/authorize?${params}`,
    { height: 65, width: 40, displayInIframe: false },
    (asyncResult) => {
      if (asyncResult.status === Office.AsyncResultStatus.Failed) {
        setGoogleBtnLoading(false);
        showAuthErr("Could not open sign-in window: " + asyncResult.error.message);
        return;
      }
      const dialog = asyncResult.value;
      dialog.addEventHandler(Office.EventType.DialogMessageReceived, (msg) => {
        dialog.close();
        try {
          const data = JSON.parse(msg.message);
          if (data.type === "success" && data.access_token) {
            S.jwt   = data.access_token;
            S.email = data.email || "";
            saveState();
            showApp();
            toast("Signed in");
          } else {
            setGoogleBtnLoading(false);
            showAuthErr(data.error || "Sign-in failed. Please try again.");
          }
        } catch (_) {
          setGoogleBtnLoading(false);
          showAuthErr("Unexpected error during sign-in.");
        }
      });
      dialog.addEventHandler(Office.EventType.DialogEventReceived, (evt) => {
        if (evt.error === 12006) setGoogleBtnLoading(false);
      });
    }
  );
}
function showAuthErr(msg) {
  const el = $("auth-err");
  el.textContent = msg;
  el.classList.remove("hidden");
}
function setGoogleBtnLoading(on) {
  $("btn-google-login").disabled = on;
  $("btn-google-text").textContent = on ? "Signing in..." : "Continue with Google";
  $("btn-google-spin").classList.toggle("hidden", !on);
  const icon = document.querySelector(".google-icon");
  if (icon) icon.style.display = on ? "none" : "block";
}

/* ═══════════════════════════════════════════════
   WEB SEARCH TOGGLE
═══════════════════════════════════════════════ */
function toggleSearch() {
  S.webSearch = !S.webSearch;
  saveState();
  applyToggleUI();
}
function applyToggleUI() {
  $("toggle-search-track").classList.toggle("on", S.webSearch);
  $("search-pill").classList.toggle("hidden", !S.webSearch);
}

/* ═══════════════════════════════════════════════
   EXCEL INTEROP — READ SELECTION
═══════════════════════════════════════════════ */
async function captureSelection() {
  try {
    return await Excel.run(async (ctx) => {
      const range = ctx.workbook.getSelectedRange();
      const sheet = ctx.workbook.worksheets.getActiveWorksheet();
      range.load(["values", "formulas", "address", "rowCount", "columnCount"]);
      sheet.load("name");
      await ctx.sync();

      const truncated = range.rowCount * range.columnCount > 500;
      return {
        address:   range.address,
        sheetName: sheet.name,
        values:    truncated ? range.values.slice(0, 20) : range.values,
        formulas:  truncated ? range.formulas.slice(0, 20) : range.formulas,
        rowCount:  range.rowCount,
        colCount:  range.columnCount,
        truncated,
      };
    });
  } catch (_) { return null; }
}

function watchSelection() {
  try {
    Excel.run(async (ctx) => {
      ctx.workbook.onSelectionChanged.add(async () => {
        if (S.selDismissed) return;
        const sel = await captureSelection();
        if (sel) { S.selectionData = sel; updateSelectionPill(sel); }
      });
      await ctx.sync();
    });
  } catch (_) {}
}

function updateSelectionPill(sel) {
  const pill = $("selection-pill");
  if (sel.rowCount === 1 && sel.colCount === 1 && !selHasData(sel)) {
    pill.classList.add("hidden"); return;
  }
  const addr = sel.address.includes("!") ? sel.address.split("!")[1] : sel.address;
  $("sel-address").textContent = addr;
  $("sel-dims").textContent    = `${sel.rowCount} x ${sel.colCount}`;
  pill.classList.remove("hidden");
}

function selHasData(sel) {
  return sel.values && sel.values.some(r => r.some(c => c !== "" && c !== null));
}

/* ═══════════════════════════════════════════════
   EXCEL INTEROP — WRITE TO CELLS
═══════════════════════════════════════════════ */
async function insertToSheet(data, type) {
  try {
    await Excel.run(async (ctx) => {
      const range = ctx.workbook.getSelectedRange();
      if (type === "formula") {
        range.getCell(0, 0).formulas = [[data]];
      } else if (type === "table") {
        const rows = data.length, cols = Math.max(...data.map(r => r.length));
        const padded = data.map(r => { const row = [...r]; while (row.length < cols) row.push(""); return row; });
        range.getCell(0, 0).getResizedRange(rows - 1, cols - 1).values = padded;
      }
      await ctx.sync();
      toast("Inserted into sheet");
    });
  } catch (e) {
    toast("Insert failed — select a target cell first");
  }
}

/* ═══════════════════════════════════════════════
   EXCEL CONTEXT INJECTION
═══════════════════════════════════════════════ */
function buildExcelContext(sel) {
  if (!sel || !selHasData(sel)) return "";
  const { address, values, formulas, rowCount, colCount, truncated } = sel;
  const lines = [`[Excel Selection: ${address} — ${rowCount}r x ${colCount}c${truncated ? " (first 20 rows)" : ""}]`];
  const cap = Math.min(values.length, 20);
  for (let r = 0; r < cap; r++) {
    const cells = (values[r] || []).map((v, c) => {
      const f = formulas[r] && formulas[r][c];
      return (typeof f === "string" && f.startsWith("="))
        ? `${f} [=${v}]`
        : (v === null || v === "" ? "(blank)" : String(v));
    });
    lines.push(cells.join(" | "));
  }
  if (rowCount > 20) lines.push(`... (${rowCount - 20} more rows)`);
  lines.push("[End Selection]");
  return lines.join("\n");
}

/* ═══════════════════════════════════════════════
   QUICK ACTIONS
═══════════════════════════════════════════════ */
async function quickAction(type) {
  if (S.streaming) return;
  const sel = await captureSelection();
  if (sel) { S.selectionData = sel; if (!S.selDismissed) updateSelectionPill(sel); }

  let prompt = QUICK_PROMPTS[type] || "";

  if (type === "explain") {
    // Solver mode: read formula from selected cell
    const formula = sel && sel.formulas && sel.formulas[0] && sel.formulas[0][0];
    prompt = (typeof formula === "string" && formula.startsWith("="))
      ? `Explain what this Excel formula does:\n\n${formula}`
      : "Explain the contents of the selected cells.";
  }

  if (!prompt) return;
  const ta = $("chat-input");
  ta.value = prompt;
  autoResize();
  await doSend();
}

/* ═══════════════════════════════════════════════
   SETTINGS DRAWER
═══════════════════════════════════════════════ */
function openSettings()  { $("settings-overlay").classList.remove("hidden"); }
function closeSettings() { $("settings-overlay").classList.add("hidden"); }

function doSignOut() { clearSession(); resetChatUI(); closeSettings(); showAuth(); }

function newChat() {
  S.convId = null; S.history = []; S.lastRawText = ""; S.lastUserMsg = "";
  try { localStorage.removeItem("ochuko_conv"); } catch (_) {}
  resetChatUI(); closeSettings();
  toast("New chat started");
}

function resetChatUI() {
  const msgs = $("messages");
  msgs.innerHTML = "";
  const wb = document.createElement("div");
  wb.className = "welcome"; wb.id = "welcome-block";
  updateWelcomeBlock(wb);
  msgs.appendChild(wb);
}

function updateWelcomeBlock(wb) {
  const isTeacher = S.mode === "teacher";
  wb.innerHTML = `
    <div class="welcome-avatar">
      <img src="../../assets/icon-80.png" alt="Ochuko"
           onerror="this.style.display='none'; this.parentElement.textContent='AI'" />
    </div>
    <p class="welcome-msg">Hi, I'm Agent Ochuko${isTeacher ? " in Teacher Mode" : " in Solver Mode"}.</p>
    <p class="welcome-tip">${
      isTeacher
        ? "Select cells and ask me anything — I'll explain the WHY, not just the WHAT."
        : "Select cells and ask — I'll give you the answer directly, no padding."
    }</p>`;
}

/* ═══════════════════════════════════════════════
   CHAT — SEND
═══════════════════════════════════════════════ */
async function doSend() {
  if (S.streaming) return;
  const ta   = $("chat-input");
  const text = ta.value.trim();
  if (!text) return;

  const wb = $("welcome-block");
  if (wb) wb.remove();

  const ctx     = buildExcelContext(S.selectionData);
  const fullMsg = ctx ? `${ctx}\n\n${text}` : text;

  appendUserBubble(text);
  S.history.push({ role: "user", content: fullMsg });
  S.lastUserMsg = fullMsg;
  ta.value = ""; ta.style.height = "auto";

  await streamResponse();
}

/* ═══════════════════════════════════════════════
   CHAT — STREAM
═══════════════════════════════════════════════ */
async function streamResponse() {
  S.streaming = true;
  setQuickBtnsDisabled(true);
  $("btn-send").disabled = true;

  const typingId = "typing-" + Date.now();
  appendTyping(typingId);

  let rawText  = "";
  let bubbleEl = null;
  let asstRow  = null;
  let sources  = [];

  try {
    const mode = S.webSearch ? "solve" : "think";

    // Prepend system prompt fresh on every call — NOT stored in S.history
    const messagesWithSystem = [
      { role: "system", content: buildSystemPrompt() },
      ...S.history,
    ];

    const payload = {
      messages: messagesWithSystem,
      mode,
      ...(S.convId && { conversation_id: S.convId }),
    };

    const res = await fetch(`${CONFIG.API_URL}/v1/responses/stream`, {
      method: "POST",
      headers: {
        "Content-Type":  "application/json",
        "Authorization": `Bearer ${S.jwt}`,
      },
      body: JSON.stringify(payload),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      if (res.status === 401) {
        removeEl(typingId); clearSession(); showAuth();
        showAuthErr("Session expired. Please sign in again.");
        return;
      }
      throw new Error(err.detail || `HTTP ${res.status}`);
    }

    removeEl(typingId);
    const created = createAsstBubble();
    bubbleEl = created.bubble;
    asstRow  = created.row;

    const reader  = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer    = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split("\n");
      buffer = lines.pop();

      for (const line of lines) {
        if (!line.startsWith("data:")) continue;
        const raw = line.slice(5).trim();
        if (raw === "[DONE]") continue;
        try {
          const evt = JSON.parse(raw);
          if (evt.type === "conversation_id" && evt.conversation_id) {
            S.convId = evt.conversation_id; saveState();
          }
          if (evt.type === "search_result" && Array.isArray(evt.sources)) {
            sources = evt.sources;
          }
          const delta = evt.choices?.[0]?.delta?.content ?? evt.delta?.text ?? evt.content ?? "";
          if (delta) { rawText += delta; renderToBubble(bubbleEl, rawText); }
        } catch (_) {}
      }
    }

    renderToBubble(bubbleEl, rawText);
    S.lastRawText = rawText;
    S.history.push({ role: "assistant", content: rawText });
    if (sources.length > 0) renderSources(sources);
    if (asstRow) addActionBar(asstRow, rawText);
    scrollBottom();

  } catch (err) {
    removeEl(typingId);
    if (bubbleEl) bubbleEl.textContent = "Error: " + err.message;
    else appendUserBubble("Error: " + err.message);
    toast(err.message);
  } finally {
    S.streaming = false;
    setQuickBtnsDisabled(false);
    $("btn-send").disabled = false;
  }
}

/* ═══════════════════════════════════════════════
   MARKDOWN RENDERING
═══════════════════════════════════════════════ */
function renderToBubble(bubbleEl, rawText) {
  if (typeof MD === "undefined") { bubbleEl.textContent = rawText; return; }
  const { html, tables } = MD.render(rawText);
  bubbleEl.className  = "bubble md-body";
  bubbleEl.innerHTML  = html;
  window._lastRenderedTables = tables;
  scrollBottom();
}

/* ═══════════════════════════════════════════════
   RESPONSE ACTION BAR
═══════════════════════════════════════════════ */
function addActionBar(row, rawText) {
  const bar = document.createElement("div");
  bar.className = "action-bar";

  // Copy
  const copyBtn = makeActionBtn("Copy", iconCopy());
  copyBtn.addEventListener("click", () =>
    navigator.clipboard.writeText(rawText).then(() => toast("Copied"), () => toast("Copy failed"))
  );
  bar.appendChild(copyBtn);

  // Insert Formula (if detected)
  const formulaMatch = rawText.match(/=[A-Z][A-Z0-9_]*\([^)]{0,120}\)/);
  if (formulaMatch) {
    const insBtn = makeActionBtn("Insert Formula", iconPlus());
    insBtn.style.color = "#d29922"; insBtn.style.borderColor = "rgba(245,166,35,.3)";
    insBtn.addEventListener("click", () => insertToSheet(formulaMatch[0], "formula"));
    bar.appendChild(insBtn);
  }

  // Insert Table (if detected)
  if (window._lastRenderedTables && window._lastRenderedTables.length > 0) {
    const tblBtn = makeActionBtn("Insert Table", iconTable());
    tblBtn.style.color = "var(--accent)"; tblBtn.style.borderColor = "rgba(77,184,255,.3)";
    tblBtn.addEventListener("click", () => {
      const t = window._lastRenderedTables[0];
      if (t) insertToSheet(t, "table");
    });
    bar.appendChild(tblBtn);
  }

  // Retry
  const regenBtn = makeActionBtn("Retry", iconRetry());
  regenBtn.addEventListener("click", async () => {
    if (S.streaming) return;
    if (S.history.length >= 1 && S.history[S.history.length - 1].role === "assistant") S.history.pop();
    row.remove();
    await streamResponse();
  });
  bar.appendChild(regenBtn);

  row.appendChild(bar);
}

function makeActionBtn(label, svgHTML) {
  const btn = document.createElement("button");
  btn.className = "action-btn";
  btn.innerHTML = `${svgHTML}<span>${label}</span>`;
  return btn;
}

// Inline SVGs for action bar buttons (no emoji)
function iconCopy()  { return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>`; }
function iconPlus()  { return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`; }
function iconTable() { return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg>`; }
function iconRetry() { return `<svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>`; }

/* ═══════════════════════════════════════════════
   DOM HELPERS
═══════════════════════════════════════════════ */
function appendUserBubble(text) {
  const msgs = $("messages");
  const row  = document.createElement("div");
  row.className = "bubble-row user";
  const b = document.createElement("div");
  b.className = "bubble"; b.textContent = text;
  const meta = document.createElement("div");
  meta.className = "bubble-meta"; meta.textContent = "You";
  row.appendChild(b); row.appendChild(meta);
  msgs.appendChild(row); scrollBottom();
}

function createAsstBubble() {
  const msgs = $("messages");
  const row  = document.createElement("div");
  row.className = "bubble-row asst";
  const b = document.createElement("div");
  b.className = "bubble md-body"; b.textContent = "";
  const meta = document.createElement("div");
  meta.className = "bubble-meta"; meta.textContent = "Ochuko";
  row.appendChild(b); row.appendChild(meta);
  msgs.appendChild(row);
  return { bubble: b, row };
}

function appendTyping(id) {
  const msgs = $("messages");
  const row  = document.createElement("div");
  row.className = "bubble-row asst"; row.id = id;
  row.innerHTML = `<div class="typing"><div class="t-dot"></div><div class="t-dot"></div><div class="t-dot"></div></div>`;
  msgs.appendChild(row); scrollBottom();
}

function renderSources(srcList) {
  const msgs  = $("messages");
  const wrap  = document.createElement("div");
  wrap.className = "bubble-row asst";
  const srcs  = document.createElement("div");
  srcs.className = "sources";
  const lbl = document.createElement("div");
  lbl.className = "source-label";
  lbl.textContent = `${srcList.length} web source${srcList.length > 1 ? "s" : ""}`;
  srcs.appendChild(lbl);
  srcList.slice(0, 6).forEach(s => {
    const a = document.createElement("a");
    a.className = "source-link"; a.href = s.url || "#";
    a.textContent = s.title || s.url || "Source";
    a.target = "_blank"; a.rel = "noopener noreferrer";
    srcs.appendChild(a);
  });
  wrap.appendChild(srcs); msgs.appendChild(wrap); scrollBottom();
}

function removeEl(id)    { const el = document.getElementById(id); if (el) el.remove(); }
function scrollBottom()  { const m = $("messages"); m.scrollTop = m.scrollHeight; }
function setQuickBtnsDisabled(on) { document.querySelectorAll(".quick-btn").forEach(b => { b.disabled = on; }); }
function autoResize() {
  const ta = $("chat-input");
  ta.style.height = "auto";
  ta.style.height = Math.min(ta.scrollHeight, 110) + "px";
}

/* ═══════════════════════════════════════════════
   TOAST
═══════════════════════════════════════════════ */
let _tid = null;
function toast(msg) {
  const el = $("toast");
  el.textContent = msg; el.className = "toast";
  clearTimeout(_tid);
  _tid = setTimeout(() => el.classList.add("hidden"), 3000);
}
