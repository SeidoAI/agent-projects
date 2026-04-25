"""lint/concept_drift — flag load-bearing terms that should be concept nodes.

Replaces the old `lint/issue_body_orphan_concepts` heuristic, which ran a
single regex+stopword pass and produced thousands of warnings on a normal
project. This rule combines several weak signals so that a finding only
fires when multiple signals line up — precision-first.

Pipeline:

1. Strip noise zones — markdown headers, fenced code blocks, inline code,
   `[[ref]]` content, URLs, checklist scaffolding. Only "real prose" survives.
2. Extract candidates from the prose:
   - Multi-word Title-Case noun phrases (`WebSocket Hub`). Leading
     determiners / imperative verbs are stripped; all-caps / acronym
     words are filtered.
   - kebab-case identifiers (`project-shell`). A compound-segment filter
     drops English compound adjectives (`read-only`, `client-side`,
     `id-to-dir`).
3. Score each candidate by combining cross-issue frequency, within-issue
   frequency, and kebab-case shape. Weak single-mention multi-word and
   single-mention kebab terms are dropped.
4. Filter against existing nodes (id / name / fuzzy normalised match) and
   the per-project allowlist.
5. Emit one finding per term (not per term-by-issue), ranked by total
   mention count, capped at MAX_FINDINGS overall.

Tunings (raise to make the rule quieter, lower to widen recall):

- `MIN_CROSS_ISSUE_FREQ = 2` — multi-word phrase must appear in ≥2 issues
  unless within-issue freq carries it.
- `MIN_WITHIN_ISSUE_FREQ = 3` — 3+ mentions in one issue is enough on
  its own for multi-word.
- `MIN_KEBAB_CROSS_ISSUE_FREQ = 2`, `MIN_KEBAB_WITHIN_ISSUE_FREQ = 2` —
  kebab-case has a slightly looser bar (within-issue 2 not 3) because
  the missing-bracket signal is shape-confirmed.
- `MAX_FINDINGS = 30` — global cap.

Calibrated on tripwire-v0 (83 issues, ~2,251 findings under the old rule).
After this calibration: 16 findings, ≥80% subjective precision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from tripwire.core.lint_allowlist import load_concept_allowlist
from tripwire.core.linter import LintFinding, register_rule
from tripwire.core.node_store import list_nodes
from tripwire.core.store import list_issues

# ---------------------------------------------------------------------------
# Tunings (see module docstring).
# ---------------------------------------------------------------------------

MIN_CROSS_ISSUE_FREQ = 2
MIN_WITHIN_ISSUE_FREQ = 3
# Kebab-case has its own (looser) bar: any frequency signal counts. The
# spec assumed "kebab-case in prose ≈ missing-bracket node ref", but on
# real spec content kebab-case is also routine for English compound
# adjectives ("per-project", "client-side"). The compound-segment filter
# strips the obvious adjectives; this threshold drops the long tail of
# one-off implementation-detail kebabs that are technically valid prose
# but not load-bearing concepts.
MIN_KEBAB_CROSS_ISSUE_FREQ = 2
MIN_KEBAB_WITHIN_ISSUE_FREQ = 2
# One finding per term, not per (term, issue) pair — the operator's job is
# to author a node for the concept, which fixes every mention at once.
# Capped at 30 total to keep CI output scannable; if a project legitimately
# has more, raising the cap is a one-line change and the long-tail signal
# was always weakest anyway.
MAX_FINDINGS = 30

# ---------------------------------------------------------------------------
# Noise-zone stripping. Hand-rolled — we only need section-header /
# code-block / fence detection, not a full markdown AST.
# ---------------------------------------------------------------------------

_FENCE = re.compile(r"^\s*(?:```|~~~)")
_HEADER = re.compile(r"^\s*#")
_CHECKLIST = re.compile(r"^\s*-\s*\[[ xX]\]\s*")
_INLINE_CODE = re.compile(r"`[^`\n]*`")
_REF = re.compile(r"\[\[[^\]\n]+\]\]")
_URL = re.compile(r"https?://\S+")


def _strip_noise(body: str) -> str:
    """Return only the "real prose" portion of a markdown body."""
    out: list[str] = []
    in_fence = False
    for line in body.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence or _HEADER.match(line):
            continue
        line = _CHECKLIST.sub("", line)
        line = _REF.sub(" ", line)
        line = _URL.sub(" ", line)
        line = _INLINE_CODE.sub(" ", line)
        out.append(line)
    return "\n".join(out)


# ---------------------------------------------------------------------------
# Candidate extraction.
# ---------------------------------------------------------------------------

# Multi-word Title-Case: 2+ words, each starting upper-case, separated by
# single spaces. "WebSocket Hub", "OAuth Token", "Project Shell".
_MULTIWORD_TITLE = re.compile(r"\b[A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)+\b")

# Determiners / pronouns / common imperative verbs that capitalise at
# sentence start and pollute multi-word matches ("The WebSocket Hub" →
# strip "The"; "Add CLI" → strip "Add"). Stripped from the *front* of a
# match; mid-phrase the same word is fine.
_LEADING_DETERMINERS = frozenset(
    {
        # determiners / articles
        "a",
        "an",
        "the",
        "this",
        "that",
        "these",
        "those",
        "our",
        "their",
        "your",
        "my",
        "his",
        "her",
        "its",
        "we",
        "they",
        "i",
        "you",
        "it",
        # conjunctions / prepositions that sometimes capitalise sentence-start
        "if",
        "when",
        "while",
        "where",
        "every",
        "each",
        "any",
        "some",
        "all",
        "no",
        "for",
        "and",
        "or",
        "but",
        "so",
        "with",
        "without",
        "to",
        "from",
        "into",
        "of",
        "on",
        # imperative verbs that start sentences in spec/issue prose
        "do",
        "use",
        "add",
        "drop",
        "skip",
        "run",
        "make",
        "let",
        "set",
        "fix",
        "see",
        "note",
        "stop",
        "start",
        "ensure",
        "implement",
        "define",
        "create",
        "update",
        "remove",
        "delete",
        "check",
        "test",
        "verify",
        "consider",
        "allow",
        "assume",
        "treat",
        "keep",
        "leave",
        "return",
        "pass",
        "raise",
        "accept",
        "reject",
        "log",
        "emit",
        "yield",
        "load",
        "save",
        "write",
        "read",
        "match",
        "after",
        "before",
        "during",
        "today",
        "given",
        "since",
        "until",
        # boolean / state words that surface in imperative form
        "not",
        "yes",
        "ok",
        "always",
        "never",
        "only",
    }
)

# kebab-case identifier — at least one hyphen, lowercase letters/digits.
_KEBAB = re.compile(r"\b[a-z][a-z0-9]*(?:-[a-z0-9]+)+\b")

# kebab-case parts that mark the match as an English compound adjective /
# adverb / state phrase rather than a node-shaped identifier. If any of
# these appear as a *segment* of a kebab match, the candidate is dropped.
# Goal: kill the "read-only" / "top-level" / "non-zero" noise while
# keeping real compound nouns like "task-checklist".
_KEBAB_ADJECTIVE_SEGMENTS = frozenset(
    {
        # suffix-style compound adjectives
        "only",
        "side",
        "level",
        "based",
        "aware",
        "ready",
        "wide",
        "wise",
        "driven",
        "friendly",
        "specific",
        "free",
        "heavy",
        "light",
        "rich",
        "shaped",
        "facing",
        "first",
        "centric",
        "agnostic",
        "compatible",
        "safe",
        "scoped",
        "local",
        "global",
        "bound",
        # prefix-style negators / modifiers
        "non",
        "un",
        "pre",
        "post",
        "per",
        "re",
        "co",
        "sub",
        "super",
        "semi",
        "multi",
        "self",
        "auto",
        "cross",
        "inter",
        "intra",
        "anti",
        # state / phase words
        "in",
        "out",
        "up",
        "down",
        "off",
        "on",
        "over",
        "under",
        "above",
        "below",
        "within",
        "around",
        "across",
        "between",
        "to",
        "from",
        "by",
        "for",
        "with",
        "without",
        "via",
        "ad",
        "de",
        "of",
        "or",
        "and",
        "no",
        "ish",
        # direction / position
        "top",
        "bottom",
        "left",
        "right",
        "front",
        "back",
        "head",
        "tail",
        "near",
        "far",
        "deep",
        "shallow",
        # time / order
        "last",
        "next",
        "prev",
        "then",
        "now",
        "later",
        "again",
        "early",
        "late",
        "old",
        "new",
        "soft",
        "hard",
        # generic
        "way",
        "type",
        "kind",
        "form",
        "case",
        "base",
        "long",
        "short",
        "low",
        "high",
        "big",
        "small",
        "open",
        "closed",
        "true",
        "false",
        # common compound-adjective neighbours from real prose
        "happy",
        "sad",
        "good",
        "bad",
        "round",
        "trip",
        "drop",
        "kick",
        "roll",
        "follow",
        "hand",
        "look",
        "set",
        "run",
        "fall",
        "fly",
        "go",
        "fit",
        "z",
        "z0",
        "z9",
        # generic English compound-noun "tail" words: when paired with
        # almost anything they form an English compound, not a node
        # identifier. Calibrated against tripwire-v0 noise.
        "block",
        "bracket",
        "bracketed",
        "path",
        "paragraph",
        "area",
        "menu",
        "height",
        "width",
        "format",
        "clipboard",
        "dir",
        "value",
        "key",
        "keys",
        "id",
        "name",
        "count",
        "list",
        "tree",
        "build",
        "message",
        "loaded",
        "verified",
        "found",
        "switch",
        "kit",
        "all",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "well",
        "known",
        "unknown",
        "completing",
        "tripwire",  # appears in tripwire-v0, project-tripwire-ui-init etc.
        "v0",
        "v1",
        "v2",
        "v3",
    }
)

# Joiner words that, when in the middle of a 3-segment kebab, mark it as
# an English phrase rather than a domain identifier ("id-to-dir",
# "copy-to-clipboard", "push-to-main", "out-of-band").
_KEBAB_PHRASE_JOINERS = frozenset(
    {"to", "for", "with", "of", "by", "in", "from", "into", "on", "off"}
)


def _looks_like_english_compound(kebab: str) -> bool:
    """True if the kebab match is most likely an English compound rather
    than a node identifier. Conservative heuristic — calibrated on
    tripwire-v0 to keep real compound-noun nodes like `task-checklist`
    while filtering out `read-only` / `id-to-dir` / `code-block`.
    """
    parts = kebab.split("-")
    # Single-char segments → regex character class or initialism artefact
    # ("a-z", "a-z0-9", "x-y-z").
    if any(len(p) <= 1 for p in parts):
        return True
    # 2-segment: either part being a known modifier → adjective compound.
    if len(parts) == 2 and any(p in _KEBAB_ADJECTIVE_SEGMENTS for p in parts):
        return True
    # 3-segment with a joiner in the middle → English phrase, not an id.
    if len(parts) == 3 and parts[1] in _KEBAB_PHRASE_JOINERS:
        return True
    # 3-segment with 2+ modifier parts → also a phrase ("end-to-end").
    if len(parts) == 3:
        mods = sum(1 for p in parts if p in _KEBAB_ADJECTIVE_SEGMENTS)
        if mods >= 2:
            return True
    return False


@dataclass
class _Candidate:
    """One candidate phrase, accumulated across issues."""

    norm: str  # lower-cased, hyphen-form for matching against nodes
    display: str  # original-case form (first occurrence, for display)
    is_kebab: bool
    issue_counts: dict[str, int] = field(default_factory=dict)

    @property
    def cross_issue_freq(self) -> int:
        return len(self.issue_counts)

    @property
    def max_within_issue(self) -> int:
        return max(self.issue_counts.values(), default=0)

    @property
    def total(self) -> int:
        return sum(self.issue_counts.values())


def _is_acronym_word(word: str) -> bool:
    """A word with fewer than 2 lower-case letters is an acronym ("API",
    "REST", "DTOs", "URLs", "NOT") — usually a noise match in title-case
    detection. Keeping the bar at 2 retains "OAuth" / "iOS" / "macOS".
    """
    lowers = sum(1 for c in word if c.islower())
    return lowers < 2


def _strip_leading_determiner(phrase: str) -> str | None:
    """Drop a leading determiner / imperative verb and any all-caps acronym
    words. Returns None if what's left isn't multi-word.
    """
    words = phrase.split()
    if words and words[0].lower() in _LEADING_DETERMINERS:
        words = words[1:]
    # Reject if any remaining word is an acronym: "Add CLI" → "CLI" remains
    # as a 1-word phrase below; "Define DTOs" → "DTOs" remains and gets
    # rejected by acronym check.
    if any(_is_acronym_word(w) for w in words):
        return None
    if len(words) < 2:
        return None
    return " ".join(words)


def _extract_candidates(prose: str) -> list[tuple[str, bool]]:
    """Return raw candidate strings from prose, with `is_kebab` flag."""
    out: list[tuple[str, bool]] = []
    for m in _MULTIWORD_TITLE.findall(prose):
        cleaned = _strip_leading_determiner(m)
        if cleaned is not None:
            out.append((cleaned, False))
    for m in _KEBAB.findall(prose):
        if _looks_like_english_compound(m):
            continue
        out.append((m, True))
    return out


# ---------------------------------------------------------------------------
# Node index (for filtering).
# ---------------------------------------------------------------------------


def _build_node_index(project_dir) -> set[str]:
    """Set of normalised node identifiers for fast membership checks.

    For every node we add its id and its name (both lower-cased), plus
    space/hyphen-flipped variants so "Project Shell" matches the
    `project-shell` node id without an extra fuzzy step.
    """
    idx: set[str] = set()
    for n in list_nodes(project_dir):
        for raw in (n.id, n.name):
            if not raw:
                continue
            lower = raw.lower()
            idx.add(lower)
            idx.add(lower.replace(" ", "-"))
            idx.add(lower.replace("-", " "))
    return idx


# ---------------------------------------------------------------------------
# Scoring + reporting.
# ---------------------------------------------------------------------------


def _passes_signal_threshold(c: _Candidate) -> bool:
    """Return True if the candidate's signals are strong enough to report."""
    if c.is_kebab:
        if c.cross_issue_freq >= MIN_KEBAB_CROSS_ISSUE_FREQ:
            return True
        if c.max_within_issue >= MIN_KEBAB_WITHIN_ISSUE_FREQ:
            return True
        return False
    if c.cross_issue_freq >= MIN_CROSS_ISSUE_FREQ:
        return True
    if c.max_within_issue >= MIN_WITHIN_ISSUE_FREQ:
        return True
    return False


def _signal_label(c: _Candidate) -> str:
    """Human-readable label for which signals fired (for the message)."""
    bits: list[str] = []
    if c.is_kebab:
        bits.append("kebab-case (likely missing `[[…]]` brackets)")
    cross_min = MIN_KEBAB_CROSS_ISSUE_FREQ if c.is_kebab else MIN_CROSS_ISSUE_FREQ
    within_min = MIN_KEBAB_WITHIN_ISSUE_FREQ if c.is_kebab else MIN_WITHIN_ISSUE_FREQ
    if c.cross_issue_freq >= cross_min:
        bits.append(f"cross-issue: {c.cross_issue_freq} issues")
    if c.max_within_issue >= within_min:
        bits.append(f"within-issue: {c.max_within_issue}x in one issue")
    return "; ".join(bits) or "weak"


def _fix_hint(c: _Candidate) -> str:
    if c.is_kebab:
        return (
            f"Create a node for {c.display!r} (looks like a node id), or add "
            f"the term to lint/concept-allowlist.yaml with a reason."
        )
    return (
        f"Add a node for {c.display!r}, alias it on an existing node, or add "
        f"it to lint/concept-allowlist.yaml with a reason."
    )


# ---------------------------------------------------------------------------
# Rule entry point.
# ---------------------------------------------------------------------------


@register_rule(
    stage="scoping",
    code="lint/concept_drift",
    severity="warning",
)
def _check(ctx):
    nodes = _build_node_index(ctx.project_dir)
    allowlist = load_concept_allowlist(ctx.project_dir)

    # Pass 1: per-issue → list of (norm, display, is_kebab, count).
    by_term: dict[str, _Candidate] = {}
    for issue in list_issues(ctx.project_dir):
        prose = _strip_noise(f"{issue.title or ''}\n{issue.body or ''}")
        for raw, is_kebab in _extract_candidates(prose):
            norm = raw.lower()
            if norm in allowlist or norm in nodes:
                continue
            # Treat "websocket hub" and "websocket-hub" as the same term so
            # cross-issue counts aggregate across both forms.
            canon = norm.replace(" ", "-")
            if canon in allowlist or canon in nodes:
                continue
            slot = by_term.get(canon)
            if slot is None:
                slot = _Candidate(norm=canon, display=raw, is_kebab=is_kebab)
                by_term[canon] = slot
            slot.issue_counts[issue.id] = slot.issue_counts.get(issue.id, 0) + 1

    # Pass 2: rank and emit one finding per term, capped at MAX_FINDINGS.
    ranked = sorted(
        (c for c in by_term.values() if _passes_signal_threshold(c)),
        key=lambda c: (-c.total, -c.cross_issue_freq, c.norm),
    )
    for c in ranked[:MAX_FINDINGS]:
        issue_ids = sorted(c.issue_counts)
        primary = issue_ids[0]
        if len(issue_ids) <= 5:
            where = ", ".join(issue_ids)
        else:
            where = f"{', '.join(issue_ids[:5])}, … (+{len(issue_ids) - 5} more)"
        yield LintFinding(
            code="lint/concept_drift",
            severity="warning",
            message=(
                f"{c.display!r} looks like a load-bearing concept "
                f"({_signal_label(c)}) but isn't covered by any node. "
                f"Mentioned in: {where}."
            ),
            file=f"issues/{primary}/issue.yaml",
            fix_hint=_fix_hint(c),
        )
