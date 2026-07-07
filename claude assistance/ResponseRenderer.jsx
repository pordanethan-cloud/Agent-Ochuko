// ResponseRenderer.jsx
// Parses agent response text and routes each content block
// to the correct renderer: Mermaid → mermaid.js, SVG → inline DOM,
// Images → <img>, Markdown → marked

import { useEffect, useRef, useState } from "react";
import mermaid from "mermaid";
import { marked } from "marked";
import DOMPurify from "dompurify";

// ─── Init mermaid once on app load ───────────────────────────────────────────
mermaid.initialize({
  startOnLoad: false,
  theme: "dark",          // match your UI theme
  securityLevel: "loose", // needed to render in injected DOM
});

let mermaidIdCounter = 0;

// ─── Block types the parser detects ──────────────────────────────────────────
// Order matters: check more specific patterns first

function parseBlocks(text) {
  const blocks = [];
  // regex patterns for each content type
  const MERMAID = /```mermaid\n([\s\S]*?)```/g;
  const SVG     = /(<svg[\s\S]*?<\/svg>)/g;
  const IMAGE   = /!\[([^\]]*)\]\((\/files\/[^\)]+)\)/g;
  const CODE    = /```(\w+)?\n([\s\S]*?)```/g;

  // Build a unified list of match positions → sorted → fill gaps with markdown
  const matches = [];

  let m;
  while ((m = MERMAID.exec(text)) !== null)
    matches.push({ start: m.index, end: m.index + m[0].length, type: "mermaid", content: m[1] });
  while ((m = SVG.exec(text)) !== null)
    matches.push({ start: m.index, end: m.index + m[0].length, type: "svg", content: m[1] });
  while ((m = IMAGE.exec(text)) !== null)
    matches.push({ start: m.index, end: m.index + m[0].length, type: "image", content: m[2], alt: m[1] });
  while ((m = CODE.exec(text)) !== null) {
    // skip if already captured as mermaid
    if (!matches.some(b => b.start === m.index))
      matches.push({ start: m.index, end: m.index + m[0].length, type: "code", content: m[2], lang: m[1] });
  }

  matches.sort((a, b) => a.start - b.start);

  let cursor = 0;
  for (const match of matches) {
    if (match.start > cursor) {
      const prose = text.slice(cursor, match.start).trim();
      if (prose) blocks.push({ type: "markdown", content: prose });
    }
    blocks.push(match);
    cursor = match.end;
  }
  if (cursor < text.length) {
    const tail = text.slice(cursor).trim();
    if (tail) blocks.push({ type: "markdown", content: tail });
  }

  return blocks;
}

// ─── Sub-renderers ────────────────────────────────────────────────────────────

function MermaidBlock({ code }) {
  const ref = useRef(null);
  const id = useRef(`mermaid-${++mermaidIdCounter}`).current;

  useEffect(() => {
    if (!ref.current) return;
    mermaid.render(id, code).then(({ svg }) => {
      ref.current.innerHTML = svg;
    }).catch(err => {
      ref.current.innerHTML = `<pre style="color:red">Mermaid error: ${err.message}</pre>`;
    });
  }, [code]);

  return (
    <div
      ref={ref}
      className="mermaid-block"
      style={{ background: "#0d1117", borderRadius: 8, padding: 16, overflowX: "auto" }}
    />
  );
}

function SvgBlock({ svg }) {
  // Sanitize — remove scripts, event handlers
  const clean = DOMPurify.sanitize(svg, { USE_PROFILES: { svg: true } });
  return (
    <div
      className="svg-block"
      style={{ display: "flex", justifyContent: "center", padding: 16 }}
      dangerouslySetInnerHTML={{ __html: clean }}
    />
  );
}

function ImageBlock({ src, alt }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <div className="image-block" style={{ textAlign: "center", padding: "8px 0" }}>
      <img
        src={src}
        alt={alt || "Agent output"}
        style={{
          maxWidth: expanded ? "100%" : 480,
          borderRadius: 8,
          cursor: "pointer",
          border: "1px solid #30363d",
        }}
        onClick={() => setExpanded(e => !e)}
        title="Click to expand"
      />
      {alt && <p style={{ fontSize: 12, color: "#8b949e", marginTop: 4 }}>{alt}</p>}
    </div>
  );
}

function CodeBlock({ code, lang }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    navigator.clipboard.writeText(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };
  return (
    <div style={{ position: "relative", margin: "8px 0" }}>
      <button
        onClick={copy}
        style={{
          position: "absolute", top: 8, right: 8,
          background: "#21262d", border: "1px solid #30363d",
          color: "#8b949e", borderRadius: 4, padding: "2px 8px",
          cursor: "pointer", fontSize: 11,
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
      <pre style={{
        background: "#0d1117", borderRadius: 8, padding: 16,
        overflowX: "auto", fontSize: 13, color: "#e6edf3",
      }}>
        <code>{code}</code>
      </pre>
    </div>
  );
}

function MarkdownBlock({ content }) {
  const html = DOMPurify.sanitize(marked.parse(content));
  return (
    <div
      className="markdown-block prose"
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}

// ─── Main renderer ────────────────────────────────────────────────────────────

export function ResponseRenderer({ text }) {
  if (!text) return null;
  const blocks = parseBlocks(text);

  return (
    <div className="response-renderer">
      {blocks.map((block, i) => {
        switch (block.type) {
          case "mermaid":  return <MermaidBlock key={i} code={block.content} />;
          case "svg":      return <SvgBlock     key={i} svg={block.content} />;
          case "image":    return <ImageBlock   key={i} src={block.content} alt={block.alt} />;
          case "code":     return <CodeBlock    key={i} code={block.content} lang={block.lang} />;
          case "markdown": return <MarkdownBlock key={i} content={block.content} />;
          default:         return null;
        }
      })}
    </div>
  );
}
