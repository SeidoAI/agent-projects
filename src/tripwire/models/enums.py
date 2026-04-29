"""Default enum values for tripwire entities.

These StrEnum classes mirror the YAML enum files shipped under
`templates/enums/` and copied into a project on `tripwire init`.
After init, the project owns its enum YAMLs and can add states, rename
labels, recolor for the UI, or remove states it doesn't use.

Field-type policy (post-KUI-110, v1 hardening): some Pydantic models DO
use these StrEnums as field types — e.g. ``AgentSession.status:
SessionStatus`` — to lock the upstream value set at load time.
Project-side YAML remains the source of truth for *labels and colors*
(and any UI metadata), but value-set drift from the upstream Python
enum now raises ``ValidationError``. The remaining string-typed fields
(notably ``Issue.status``) keep the old "projects can customise enums
without forking" stance and rely on the validator's ``status_in_enum``
rules for enforcement.
"""

from enum import StrEnum


class IssueStatus(StrEnum):
    """Canonical issue states (v0.7b 6-stage flow).

    See `templates/enums/issue_status.yaml` for the authoritative definition.
    """

    BACKLOG = "backlog"
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    IN_REVIEW = "in_review"
    VERIFIED = "verified"
    DONE = "done"
    CANCELED = "canceled"


class Priority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Executor(StrEnum):
    AI = "ai"
    HUMAN = "human"
    MIXED = "mixed"


class Verifier(StrEnum):
    REQUIRED = "required"
    OPTIONAL = "optional"
    NONE = "none"


class NodeType(StrEnum):
    ENDPOINT = "endpoint"
    MODEL = "model"
    CONFIG = "config"
    TF_OUTPUT = "tf_output"
    CONTRACT = "contract"
    DECISION = "decision"
    REQUIREMENT = "requirement"
    SERVICE = "service"
    SCHEMA = "schema"
    CUSTOM = "custom"


class NodeStatus(StrEnum):
    ACTIVE = "active"
    PLANNED = "planned"
    DEPRECATED = "deprecated"
    STALE = "stale"


class SessionStatus(StrEnum):
    """Canonical session states — see `templates/enums/session_status.yaml`."""

    PLANNED = "planned"
    QUEUED = "queued"
    EXECUTING = "executing"
    ACTIVE = "active"
    WAITING_FOR_CI = "waiting_for_ci"
    WAITING_FOR_REVIEW = "waiting_for_review"
    WAITING_FOR_DEPLOY = "waiting_for_deploy"
    RE_ENGAGED = "re_engaged"
    IN_REVIEW = "in_review"
    VERIFIED = "verified"
    COMPLETED = "completed"
    # KUI-110 carve-out: pre-v0.8 sessions that completed under the
    # legacy flat-file artifact layout (no `sessions/<sid>/artifacts/`
    # subdir, and missing the v0.8 `recommended-testing-plan.md` /
    # `post-completion-comments.md` outputs). They're terminal-success
    # but excluded from `MERGED_STATUSES` so `check_artifact_presence`
    # doesn't fabricate missing-artifact errors against the modern
    # contract. New sessions must use `COMPLETED`.
    LEGACY_COMPLETED = "legacy_completed"
    FAILED = "failed"
    PAUSED = "paused"
    ABANDONED = "abandoned"


class ReEngagementTrigger(StrEnum):
    INITIAL_LAUNCH = "initial_launch"
    CI_FAILURE = "ci_failure"
    VERIFIER_REJECTION = "verifier_rejection"
    HUMAN_REVIEW_CHANGES = "human_review_changes"
    BUG_FOUND = "bug_found"
    DEPLOY_FAILURE = "deploy_failure"
    STALE_REFERENCE = "stale_reference"
    SCOPE_CHANGE = "scope_change"
    MERGE_CONFLICT = "merge_conflict"
    DEPENDENCY_CONFLICT = "dependency_conflict"
    HUMAN_RESPONSE = "human_response"
    PLAN_APPROVED = "plan_approved"
    PLAN_REJECTED = "plan_rejected"
    MANUAL = "manual"


class MessageType(StrEnum):
    QUESTION = "question"
    PLAN_APPROVAL = "plan_approval"
    PROGRESS = "progress"
    STUCK = "stuck"
    ESCALATION = "escalation"
    HANDOVER = "handover"
    FYI = "fyi"
    STATUS = "status"


class AgentState(StrEnum):
    """States an agent reports via `status` messages.

    Powers the structured `status` message body so the UI can show
    "what is the agent doing right now" without parsing free-form text.
    """

    INVESTIGATING = "investigating"
    PLANNING = "planning"
    AWAITING_PLAN_APPROVAL = "awaiting_plan_approval"
    IMPLEMENTING = "implementing"
    TESTING = "testing"
    DEBUGGING = "debugging"
    REFACTORING = "refactoring"
    DOCUMENTING = "documenting"
    SELF_VERIFYING = "self_verifying"
    BLOCKED = "blocked"
    HANDED_OFF = "handed_off"
    DONE = "done"


class CommentType(StrEnum):
    STATUS_CHANGE = "status_change"
    QUESTION = "question"
    COMPLETION = "completion"
    OBSERVATION = "observation"
    DECISION = "decision"


# Mapping from enum name (matches YAML file basename) to the StrEnum class.
# Used by the enum loader to fall back to packaged defaults when no
# project-level enum file exists.
DEFAULT_ENUMS: dict[str, type[StrEnum]] = {
    "issue_status": IssueStatus,
    "priority": Priority,
    "executor": Executor,
    "verifier": Verifier,
    "node_type": NodeType,
    "node_status": NodeStatus,
    "session_status": SessionStatus,
    "re_engagement_trigger": ReEngagementTrigger,
    "message_type": MessageType,
    "agent_state": AgentState,
    "comment_type": CommentType,
}
