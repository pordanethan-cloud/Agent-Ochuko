# app/core/copyright_guard.py
"""
Copyright enforcement engine — Phase 5 (item #7).

A stateful, per-turn gate over the final synthesis. The corpus of sources is
assembled from the turn's tool outputs (search_web / deep_research /
fetch_url results). Enforcement is mechanical, not advisory:

  - 15+ words from any single source  -> SEVERE VIOLATION (paraphrase required)
  - ONE quote per source MAXIMUM      -> after one quote that source is CLOSED
  - Displacement heuristic            -> heavy coverage of a source = violation

Violations produce a critique for the reflexion-style one-rewrite pass; if the
rewrite still violates, the offending span is hard-truncated before emit.
Copyright compliance is non-negotiable and takes precedence over user requests.
"""
import re
from typing import Dict, List, Optional, Tuple


class Violation:
    def __init__(self, kind: str, detail: str, span: Optional[Tuple[int, int]] = None):
        self.kind = kind          # "long_quote" | "closed_source" | "displacement"
        self.detail = detail
        self.span = span

    def __repr__(self) -> str:  # pragma: no cover
        return f"Violation({self.kind}: {self.detail[:80]})"


# Quoted spans: "double quotes" and typographic quotes (3+ chars to count).
_QUOTE_RE = re.compile(r'[\u201c"]([^\u201d"]{3,600})[\u201d"]')


def _words(text: str) -> List[str]:
    return re.findall(r"[A-Za-z0-9']+", text.lower())


def _shingles(text: str, n: int = 10) -> set:
    ws = _words(text)
    if len(ws) < n:
        return set()
    return {" ".join(ws[i:i + n]) for i in range(len(ws) - n + 1)}


class CopyrightGuard:
    """Per-turn copyright compliance engine. Build once with the tool corpus."""

    def __init__(self, tool_outputs: List[str], max_words_per_quote: int = 14):
        self.max_words_per_quote = max_words_per_quote
        # One entry per source: shingle set + quote count + corpus size.
        self._sources: List[Dict] = []
        for out in tool_outputs or []:
            if not out or len(_words(out)) < 10:
                continue  # receipts/errors aren't sources
            self._sources.append({
                "shingles": _shingles(out),
                "quotes": 0,
                "word_count": len(_words(out)),
                "text": out,
            })
        self._pending_quotes: List[Tuple[int, int, int]] = []

    # ── Checks ────────────────────────────────────────────────────────────

    def check(self, content: str) -> List[Violation]:
        violations: List[Violation] = []
        if not content or not self._sources:
            return violations

        for m in _QUOTE_RE.finditer(content):
            quote = m.group(1)
            n_words = len(_words(quote))
            if n_words > self.max_words_per_quote:
                violations.append(Violation(
                    "long_quote",
                    f"quote is {n_words} words (>{self.max_words_per_quote}) — paraphrase instead",
                    span=(m.start(), m.end()),
                ))
                continue
            src_idx = self._locate_source(quote)
            if src_idx is None:
                continue
            if self._sources[src_idx]["quotes"] >= 1:
                violations.append(Violation(
                    "closed_source",
                    "source already quoted once this turn — it is CLOSED; paraphrase",
                    span=(m.start(), m.end()),
                ))
                continue
            self._pending_quotes.append((src_idx, m.start(), m.end()))

        # Displacement: shingle overlap with any source dominating the draft.
        draft_shingles = _shingles(content)
        if draft_shingles:
            for src in self._sources:
                if not src["shingles"]:
                    continue
                overlap = len(draft_shingles & src["shingles"]) / len(draft_shingles)
                if overlap > 0.30:
                    violations.append(Violation(
                        "displacement",
                        f"draft mirrors source structure ({overlap:.0%} shingle overlap) — reorganize completely",
                    ))
                    break
        return violations

    def _locate_source(self, quote: str) -> Optional[int]:
        """Finds which corpus source the quote came from."""
        q_words = _words(quote)
        if not q_words:
            return None
        q_clean = " ".join(q_words)
        for i, src in enumerate(self._sources):
            src_clean = " ".join(_words(src.get("text", "")))
            if q_clean in src_clean:
                return i
        q_set = set(q_words)
        best_idx, best_score = None, 0.0
        for i, src in enumerate(self._sources):
            src_set = set(_words(src.get("text", "")))
            if not src_set:
                continue
            overlap = len(q_set & src_set) / len(q_set)
            if overlap > best_score:
                best_idx, best_score = i, overlap
        return best_idx if best_score >= 0.7 else None

    # ── Commit / remediation ──────────────────────────────────────────────

    def commit(self, content: str) -> str:
        """Registers accepted quotes (closes sources). Call on final content."""
        for src_idx, _s, _e in self._pending_quotes:
            self._sources[src_idx]["quotes"] += 1
        self._pending_quotes = []
        return content

    def hard_truncate_violations(self, content: str, violations: List[Violation]) -> str:
        """Last resort: replace violating quoted spans with a paraphrase note."""
        for v in sorted(
            [v for v in violations if v.span], key=lambda x: x.span[0], reverse=True
        ):
            s, e = v.span
            content = content[:s] + "[paraphrased — quote limit reached]" + content[e:]
        return content

    @staticmethod
    def critique(violations: List[Violation]) -> str:
        """Reflexion-channel critique injected for the one-rewrite pass."""
        details = "; ".join(f"{v.kind}: {v.detail}" for v in violations)
        return (
            f"COPYRIGHT VIOLATION — rewrite required. {details}. Default to paraphrasing: "
            "15+ words from any single source is a severe violation, and a source is CLOSED "
            "after one quote. Do not mirror the source's phrasing or structure."
        )
