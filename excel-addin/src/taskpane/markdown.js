/**
 * markdown.js — Lightweight markdown renderer for Agent Ochuko Excel Add-in
 *
 * No external dependencies. Handles:
 *   bold, italic, inline code, fenced code blocks (with copy button),
 *   headings (H1-H4), ordered/unordered lists, horizontal rules,
 *   markdown tables (with Insert Table button), Excel formula chips
 *   (=FUNCTION(...) with Insert Formula button).
 *
 * Usage:
 *   const { html, formulas, tables } = MD.render(rawText);
 *   element.innerHTML = html;
 */
"use strict";

const MD = {
  /**
   * Render a markdown string to an HTML string.
   * Returns { html: string, formulas: string[], tables: any[][][] }
   */
  render(raw) {
    const formulas = [];
    const tables   = [];
    const lines    = raw.split("\n");
    let html       = "";
    let i          = 0;

    while (i < lines.length) {
      const line = lines[i];

      /* ── Fenced code block ──────────────────── */
      if (line.startsWith("```")) {
        const lang = line.slice(3).trim();
        let code   = "";
        i++;
        while (i < lines.length && !lines[i].startsWith("```")) {
          code += lines[i] + "\n";
          i++;
        }
        i++; // skip closing ```
        html += MD._codeBlock(code.trimEnd(), lang);
        continue;
      }

      /* ── Markdown table ─────────────────────── */
      if (
        line.includes("|") &&
        i + 1 < lines.length &&
        /^[\s|:-]+$/.test(lines[i + 1])
      ) {
        const tableLines = [];
        while (i < lines.length && lines[i].trim().startsWith("|")) {
          tableLines.push(lines[i]);
          i++;
        }
        const { tableHtml, tableData } = MD._table(tableLines, tables.length);
        tables.push(tableData);
        html += tableHtml;
        continue;
      }

      /* ── Headings ───────────────────────────── */
      const hm = line.match(/^(#{1,4})\s+(.+)/);
      if (hm) {
        const lvl = Math.min(hm[1].length + 2, 6);
        html += `<h${lvl} class="md-h">${MD._inline(hm[2])}</h${lvl}>`;
        i++;
        continue;
      }

      /* ── Unordered list ─────────────────────── */
      if (/^[-*+]\s+/.test(line)) {
        html += '<ul class="md-ul">';
        while (i < lines.length && /^[-*+]\s+/.test(lines[i])) {
          html += `<li>${MD._inline(lines[i].replace(/^[-*+]\s+/, ""))}</li>`;
          i++;
        }
        html += "</ul>";
        continue;
      }

      /* ── Ordered list ───────────────────────── */
      if (/^\d+\.\s+/.test(line)) {
        html += '<ol class="md-ol">';
        while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
          html += `<li>${MD._inline(lines[i].replace(/^\d+\.\s+/, ""))}</li>`;
          i++;
        }
        html += "</ol>";
        continue;
      }

      /* ── Horizontal rule ────────────────────── */
      if (/^-{3,}$/.test(line.trim())) {
        html += '<hr class="md-hr">';
        i++;
        continue;
      }

      /* ── Empty line ─────────────────────────── */
      if (line.trim() === "") {
        html += '<div class="md-spacer"></div>';
        i++;
        continue;
      }

      /* ── Paragraph ──────────────────────────── */
      html += `<p class="md-p">${MD._inline(line)}</p>`;
      i++;
    }

    /* Collect all Excel formulas found in the raw text */
    const fMatches = raw.match(/=\s*[A-Z][A-Z0-9_]*\s*\(/g) || [];
    // Get fuller formula strings
    (raw.match(/=[A-Z][A-Z0-9_]*\([^)]{0,120}\)/g) || []).forEach(f => {
      if (!formulas.includes(f)) formulas.push(f);
    });

    return { html, formulas, tables };
  },

  /* ── Inline formatting ────────────────────────────────────────── */
  _inline(text) {
    // 1. Escape HTML entities first
    text = text
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

    // 2. Excel formula chips  (=FUNCTION(...)) before any other processing
    text = text.replace(
      /(=[A-Z][A-Z0-9_.]*\([^()]{0,120}\))/g,
      (formula) => {
        const safe = encodeURIComponent(formula.replace(/&amp;/g, "&").replace(/&lt;/g, "<").replace(/&gt;/g, ">"));
        return `<span class="formula-chip" data-formula="${safe}">${formula
          }<button class="formula-insert-btn" onclick="insertFormulaChip(this)">Insert</button></span>`;
      }
    );

    // 3. Bold **text**
    text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

    // 4. Italic *text* (not inside **)
    text = text.replace(/(?<!\*)\*([^*]+?)\*(?!\*)/g, "<em>$1</em>");

    // 5. Inline code `text`
    text = text.replace(/`([^`]+?)`/g, '<code class="md-code">$1</code>');

    return text;
  },

  /* ── Fenced code block ────────────────────────────────────────── */
  _codeBlock(code, lang) {
    const escaped = code
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
    const uid = "cb-" + Math.random().toString(36).slice(2, 8);
    return `<div class="md-pre-wrap">${
      lang ? `<span class="md-lang">${lang}</span>` : ""
    }<button class="md-copy-btn" onclick="copyCodeBlock('${uid}')">Copy</button
    ><pre class="md-pre" id="${uid}"><code>${escaped}</code></pre></div>`;
  },

  /* ── Markdown table ───────────────────────────────────────────── */
  _table(lines, tableIndex) {
    const parseRow = (l) =>
      l.split("|")
        .map((c) => c.trim())
        .filter((_, i, a) => i > 0 && i < a.length - 1);

    const headers = parseRow(lines[0]);
    // lines[1] is the separator row — skip it
    const bodyLines = lines.slice(2).filter(
      (l) => !/^[\s|:-]+$/.test(l)
    );
    const rows = bodyLines.map(parseRow);

    // 2D array for Excel insertion: header + data rows
    const tableData = [headers, ...rows];

    const thHTML  = headers.map((h) => `<th>${MD._inline(h)}</th>`).join("");
    const rowsHTML = rows
      .map((r) => `<tr>${r.map((c) => `<td>${MD._inline(c)}</td>`).join("")}</tr>`)
      .join("");

    const html = `<div class="md-table-wrap">
      <table class="md-table">
        <thead><tr>${thHTML}</tr></thead>
        <tbody>${rowsHTML}</tbody>
      </table>
      <button class="md-insert-table-btn" data-table-index="${tableIndex}"
        onclick="insertTableChip(this)">Insert Table</button>
    </div>`;

    return { tableHtml: html, tableData };
  },
};

/* ══════════════════════════════════════════════════════════════════
   GLOBAL HELPERS called from inline onclick attributes
══════════════════════════════════════════════════════════════════ */

/**
 * Copy a fenced code block to the clipboard.
 */
function copyCodeBlock(uid) {
  const el = document.getElementById(uid);
  if (!el) return;
  navigator.clipboard.writeText(el.textContent).then(
    () => toast("Copied"),
    () => toast("Copy failed")
  );
}

/**
 * Insert the formula from a formula chip into the selected Excel cell.
 * Delegates to insertToSheet() defined in taskpane.js.
 */
function insertFormulaChip(btn) {
  const chip = btn.closest(".formula-chip");
  if (!chip) return;
  const formula = decodeURIComponent(chip.dataset.formula || "");
  if (formula && typeof insertToSheet === "function") {
    insertToSheet(formula, "formula");
  }
}

/**
 * Insert the detected table into Excel starting at the selected cell.
 * Uses window._lastRenderedTables set by taskpane.js.
 */
function insertTableChip(btn) {
  const idx = parseInt(btn.dataset.tableIndex, 10);
  const tables = window._lastRenderedTables;
  if (!isNaN(idx) && tables && tables[idx] && typeof insertToSheet === "function") {
    insertToSheet(tables[idx], "table");
  }
}
