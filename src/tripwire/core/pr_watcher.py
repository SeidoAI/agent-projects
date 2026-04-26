"""Post-PR auto-check watcher (v0.7.9 §A8).

Polls open PRs across active sessions and emits :class:`WatcherAction`
records when one of three tripwires fires:

  #15      code PR open + matching PT PR doesn't exist after 10 min
  #17      PR merged but ``session.status`` is still ``executing``
  #18-19   PT PR opens but the diff doesn't include all required artifacts

Designed as a pure-function over its inputs: the caller injects
``fetch_pr`` and ``fetch_pr_files`` callables so tests supply canned
GitHub responses, and the watcher returns ``WatcherAction`` records
the executor turns into side effects (plan-md follow-up, status
writeback, GH issue comment, agent re-engagement).

The runtime daemon (``tripwire watch start``) builds the
:class:`WatchedSession` list each tick from the live session-store,
calls :meth:`PRWatcher.tick`, and dispatches the actions.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------- DTOs ----------------------------------------------------------


@dataclass
class PRState:
    number: int
    state: str  # "open" | "closed"
    merged: bool
    head_branch: str
    title: str = ""
    url: str = ""
    # Aggregate CI status for the PR's relevant commit. ``"PASS"`` /
    # ``"FAIL"`` / ``"PENDING"`` / ``None`` when unknown. Used by the
    # post-merge CI failure tripwire (v0.7.10 §B2).
    check_status: str | None = None


@dataclass
class WatchedSession:
    session_id: str
    project_dir: Path
    code_repo: str
    code_branch: str
    code_pr_number: int | None
    code_pr_opened_at: datetime | None
    pt_repo: str
    pt_branch: str
    pt_pr_number: int | None
    required_artifacts: list[str] = field(default_factory=list)
    session_status: str = "executing"


# ---------- Action types --------------------------------------------------


@dataclass
class InjectFollowUp:
    session_id: str
    tripwire_id: str
    message: str


@dataclass
class TransitionStatus:
    session_id: str
    tripwire_id: str
    new_status: str
    reason: str


@dataclass
class CommentOnPR:
    repo: str
    pr_number: int
    tripwire_id: str
    body: str


@dataclass
class ReengageAgent:
    session_id: str
    reason: str


WatcherAction = InjectFollowUp | TransitionStatus | CommentOnPR | ReengageAgent


# ---------- Type aliases for injected fetchers ----------------------------


FetchPR = Callable[..., PRState]
FetchPRFiles = Callable[..., list[dict]]


_TEN_MINUTES = timedelta(minutes=10)


# Sessions in any of these statuses count as "inactive" for the post-
# merge CI failure tripwire — the agent has already exited and a fresh
# red CI on main means a regression that needs PM follow-up. Sessions
# in ``executing`` belong to the in-flight CI-aware-exit (§B1) instead.
_POST_MERGE_INACTIVE_STATUSES = frozenset(
    {"paused", "in_review", "verified", "completed", "done"}
)


class PRWatcher:
    """Pure-function watcher: WatchedSession list in, WatcherAction list out.

    Stateful only in the "fired-already" deduplication sets, so the
    same condition doesn't re-emit on every poll. Tests call
    :meth:`tick` directly with canned fetch functions; the daemon
    wraps a real GitHub-API fetcher.
    """

    def __init__(
        self,
        *,
        fetch_pr: FetchPR,
        fetch_pr_files: FetchPRFiles,
        token: str | None = None,
    ) -> None:
        self._fetch_pr = fetch_pr
        self._fetch_pr_files = fetch_pr_files
        self._token = token
        # Per-session/per-condition firing state — keep tripwires
        # idempotent across consecutive ticks.
        self._fired_no_pt: set[str] = set()
        self._fired_merged_executing: set[str] = set()
        self._fired_pt_missing: set[int] = set()  # pt_pr_number
        self._fired_post_merge_ci_failure: set[str] = set()  # session_id

    def tick(
        self, sessions: Iterable[WatchedSession], *, now: datetime
    ) -> list[WatcherAction]:
        actions: list[WatcherAction] = []
        for ws in sessions:
            try:
                actions.extend(self._tick_session(ws, now))
            except Exception:
                logger.exception(
                    "pr_watcher: tick raised for session %r — skipping",
                    ws.session_id,
                )
        return actions

    # --- per-session evaluation ----------------------------------------

    def _tick_session(self, ws: WatchedSession, now: datetime) -> list[WatcherAction]:
        if ws.code_pr_number is None:
            return []
        owner, repo = self._split_repo(ws.code_repo)
        code_state = self._fetch_pr((owner, repo), ws.code_pr_number, token=self._token)
        actions: list[WatcherAction] = []
        # #17 — code PR merged but status still executing
        if code_state.merged and ws.session_status == "executing":
            self._maybe_fire_merged_executing(ws, actions)
        # B2 — post-merge CI red on an inactive session
        if (
            code_state.merged
            and code_state.check_status == "FAIL"
            and ws.session_status in _POST_MERGE_INACTIVE_STATUSES
        ):
            self._maybe_fire_post_merge_ci_failure(ws, code_state, actions)
        # #15 — code PR open, no PT PR after 10 min
        if (
            code_state.state == "open"
            and not code_state.merged
            and ws.pt_pr_number is None
            and ws.code_pr_opened_at is not None
            and now - ws.code_pr_opened_at >= _TEN_MINUTES
        ):
            self._maybe_fire_no_pt_pr(ws, actions)
        # #18-19 — PT PR exists but missing required artifacts
        if ws.pt_pr_number is not None:
            self._check_pt_artifacts(ws, actions)
        return actions

    def _maybe_fire_merged_executing(
        self, ws: WatchedSession, actions: list[WatcherAction]
    ) -> None:
        if ws.session_id in self._fired_merged_executing:
            return
        self._fired_merged_executing.add(ws.session_id)
        actions.append(
            TransitionStatus(
                session_id=ws.session_id,
                tripwire_id="watcher/merged_executing",
                new_status="paused",
                reason=(
                    f"Code PR #{ws.code_pr_number} merged but "
                    "session.status is still 'executing' — pausing so the "
                    "agent can run completion bookkeeping."
                ),
            )
        )
        actions.append(
            InjectFollowUp(
                session_id=ws.session_id,
                tripwire_id="watcher/merged_executing",
                message=(
                    "## PM follow-up — PR merged while still executing\n\n"
                    f"Code PR #{ws.code_pr_number} was merged to main but "
                    "the session is still in `executing` state. The runtime "
                    "watcher transitioned to `paused`. Resume to run the "
                    "completion protocol (self-review.md, insights.yaml, "
                    "PT PR, `tripwire session complete`)."
                ),
            )
        )

    def _maybe_fire_post_merge_ci_failure(
        self,
        ws: WatchedSession,
        code_state: PRState,
        actions: list[WatcherAction],
    ) -> None:
        if ws.session_id in self._fired_post_merge_ci_failure:
            return
        self._fired_post_merge_ci_failure.add(ws.session_id)
        pr_url = code_state.url or f"https://github.com/{ws.code_repo}/pull/{ws.code_pr_number}"
        actions.append(
            InjectFollowUp(
                session_id=ws.session_id,
                tripwire_id="watcher/post_merge_ci_failure",
                message=(
                    "## PM follow-up — post-merge CI failure (auto-injected)\n\n"
                    f"Code PR #{ws.code_pr_number} on `{ws.code_repo}` was merged "
                    "but CI on the merge commit is red. The session was already "
                    f"in `{ws.session_status}` when this regression surfaced.\n\n"
                    f"PR: {pr_url}\n\n"
                    "Read the failing job's log via `gh run view <run-id> --log-failed` "
                    "(run-id from `gh pr view "
                    f"{ws.code_pr_number} --json statusCheckRollup`), identify the "
                    "*pattern* of the failure, `grep` the test suite for siblings, "
                    "and patch every occurrence in one fix commit. The runtime has "
                    "already paused this session and will spawn `--resume` so you "
                    "pick up from here."
                ),
            )
        )
        actions.append(
            TransitionStatus(
                session_id=ws.session_id,
                tripwire_id="watcher/post_merge_ci_failure",
                new_status="paused",
                reason=(
                    f"Post-merge CI red on PR #{ws.code_pr_number} "
                    f"({ws.code_repo}); session was {ws.session_status}."
                ),
            )
        )
        actions.append(
            ReengageAgent(
                session_id=ws.session_id,
                reason="watcher/post_merge_ci_failure",
            )
        )

    def _maybe_fire_no_pt_pr(
        self, ws: WatchedSession, actions: list[WatcherAction]
    ) -> None:
        if ws.session_id in self._fired_no_pt:
            return
        self._fired_no_pt.add(ws.session_id)
        actions.append(
            InjectFollowUp(
                session_id=ws.session_id,
                tripwire_id="watcher/code_pr_no_pt_pr",
                message=(
                    "## PM follow-up — code PR opened, project-tracking PR missing\n\n"
                    f"Code PR #{ws.code_pr_number} on `{ws.code_repo}` was "
                    "opened more than 10 minutes ago, but no project-"
                    f"tracking PR exists for branch `{ws.pt_branch}` on "
                    f"`{ws.pt_repo}`. Per the v0.7.9 exit protocol, both "
                    "PRs must exist. Author the PT-side artifacts "
                    "(developer.md, verified.md, self-review.md, "
                    "insights.yaml) and open the PT PR."
                ),
            )
        )
        actions.append(
            ReengageAgent(
                session_id=ws.session_id,
                reason="watcher/code_pr_no_pt_pr",
            )
        )

    def _check_pt_artifacts(
        self, ws: WatchedSession, actions: list[WatcherAction]
    ) -> None:
        if ws.pt_pr_number in self._fired_pt_missing:
            return
        if not ws.required_artifacts:
            return
        owner, repo = self._split_repo(ws.pt_repo)
        files = self._fetch_pr_files((owner, repo), ws.pt_pr_number, token=self._token)
        present = {entry.get("filename") for entry in files if entry.get("filename")}
        missing = [a for a in ws.required_artifacts if a not in present]
        if not missing:
            return
        self._fired_pt_missing.add(ws.pt_pr_number)
        body = (
            "Tripwire `watcher/pt_pr_missing_artifacts`: this PR is missing "
            "the following required session artifacts:\n\n"
            + "\n".join(f"- `{m}`" for m in missing)
            + "\n\nPlease add them and push, or close this PR if the "
            "session was abandoned."
        )
        actions.append(
            CommentOnPR(
                repo=ws.pt_repo,
                pr_number=ws.pt_pr_number,
                tripwire_id="watcher/pt_pr_missing_artifacts",
                body=body,
            )
        )
        actions.append(
            ReengageAgent(
                session_id=ws.session_id,
                reason="watcher/pt_pr_missing_artifacts",
            )
        )

    @staticmethod
    def _split_repo(slug: str) -> tuple[str, str]:
        owner, _, repo = slug.partition("/")
        return owner, repo


__all__ = [
    "CommentOnPR",
    "FetchPR",
    "FetchPRFiles",
    "InjectFollowUp",
    "PRState",
    "PRWatcher",
    "ReengageAgent",
    "TransitionStatus",
    "WatchedSession",
    "WatcherAction",
]
