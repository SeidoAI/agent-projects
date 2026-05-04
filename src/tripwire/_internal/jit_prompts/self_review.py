"""The canonical first JIT prompt — self-review on ``session.complete``.

Three prompt variations exist; ``fire(ctx)`` picks one
deterministically from ``hash(project_id, session_id)`` so the same
session always sees the same prompt across re-runs but different
sessions pick different ones.

The four-lens prompt content lives ONLY in this module per
``2026-04-21-v08-jit-prompts-as-primitive.md`` §8 — by design it does
not appear in any spec, plan, issue, or other doc that the executing
agent's read path includes.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import ClassVar

from tripwire._internal.jit_prompts import JitPrompt, JitPromptContext

_VARIATIONS: tuple[str, ...] = (
    """\
A pull request that wraps this session is about to land. Before it
does — pause and walk these four lenses against your own work, as if
a colleague had asked you to review the PR cold. Be specific:

  1. AC met but not really. Walk every "[x]" in your
     verification-checklist.md against the actual diff and tests.
     Downgrade soft-yeses to "[ ]" and explain the gap.
  2. Unilateral decisions. List every design call you made that
     diverges from the issue spec or session plan, with rationale.
  3. Skipped workflow. What did the skill / process mandate that you
     skipped, and why?
  4. Quality drift across the session. Compare your last commit's
     test density / naming hygiene / care to your first.

When done, write your findings into the project-tracking session
artifact `sessions/<sid>/self-review.md`. Then re-run this command
with `--ack`. If --ack reports "marker not substantive", you
forgot to either (a) reference fix-commit SHAs OR (b) explicitly
declare `declared_no_findings: true` — pick one and try again.
""",
    """\
Stop. Before this PR is reviewed by anyone else, do a four-lens
self-review of your own diff. The four lenses, applied with rigour:

  - Lens 1 — checklist coherence. For every ticked acceptance
    criterion in verification-checklist.md, find the line(s) of code
    or the test that justify the tick. If there isn't one, untick it
    and write one sentence explaining the gap.
  - Lens 2 — divergence from plan. Where did you make a call the
    plan didn't cover? Each one gets a one-paragraph note in
    decisions.md.
  - Lens 3 — process integrity. The skill instructions you were
    handed at session start specified workflows. Which ones did you
    follow loosely vs. tightly? If "loosely", say why.
  - Lens 4 — fatigue check. Diff your most recent commit against the
    first commit of this session. Same care? Same test density? Same
    naming discipline? If not, the late work needs another pass.

Persist your findings to `sessions/<sid>/self-review.md`. Re-run
this command with `--ack` after the file exists and either lists
fix-commit SHAs or declares `declared_no_findings: true`.
""",
    """\
You're about to claim this session is done. Before that claim
crystallises into a merge — engage these four lenses on your own
work. Each one matters; don't skip any.

  Lens A. The "ticked-but-not-true" check. Re-walk
  verification-checklist.md and confirm each item that says "[x]"
  is actually true in the code as it stands right now. Soft yeses
  get downgraded.

  Lens B. The "I-decided-this-myself" check. Enumerate the calls
  you made without explicit plan / spec authority. For each, name
  the choice, name the alternative, and name the rationale. This
  goes in decisions.md.

  Lens C. The "did-I-cut-corners" check. The skill / harness
  instructions you were handed prescribed certain behaviours
  (commit cadence, TDD discipline, etc.). Which did you follow,
  and which did you elide? Be honest.

  Lens D. The "first-commit-vs-last-commit" check. Pull both up.
  Are they the same hand? Did the late work get the same care as
  the early work? If not, name the gap.

Write up your findings in `sessions/<sid>/self-review.md`, then
re-run with `--ack`. The marker check requires either
fix-commit SHAs or `declared_no_findings: true`.
""",
)


class SelfReviewJitPrompt(JitPrompt):
    """Self-review JIT prompt — fires on ``session.complete``.

    The marker file (``.tripwire/acks/self-review-<sid>.json``) must
    contain ``fix_commits: [...]`` (≥1 SHA) OR
    ``declared_no_findings: true``. An empty marker is rejected — the
    spec calls this the "substantiveness check" (§8 + AC bullet 3).
    """

    id: ClassVar[str] = "self-review"
    fires_on: ClassVar[str] = "session.complete"
    blocks: ClassVar[bool] = True

    def fire(self, ctx: JitPromptContext) -> str:
        idx = ctx.variation_index(len(_VARIATIONS))
        return _VARIATIONS[idx]

    def is_acknowledged(self, ctx: JitPromptContext) -> bool:
        marker = ctx.ack_path(self.id)
        if not marker.is_file():
            return False
        return self._marker_substantive(marker)

    @staticmethod
    def _marker_substantive(marker_path: Path) -> bool:
        try:
            data = json.loads(marker_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
        if not isinstance(data, dict):
            return False
        commits = data.get("fix_commits")
        declared = data.get("declared_no_findings")
        has_commits = isinstance(commits, list) and any(
            isinstance(s, str) and s.strip() for s in commits
        )
        return bool(has_commits or declared is True)
