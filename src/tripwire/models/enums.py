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

v0.9.4 status alignment
-----------------------

``IssueStatus`` and ``SessionStatus`` were collapsed onto one canonical
name per concept:

  backlog → planned     todo → queued        in_progress → executing
  done → completed      canceled → abandoned

Pre-v0.9.4 PT data with the old names continues to load via ``__missing__``
classmethod aliasing (``IssueStatus("done") is IssueStatus.COMPLETED``).
``SessionStatus`` similarly accepts the dead-but-formerly-enum values
``active``/``waiting_for_ci``/``waiting_for_review``/``waiting_for_deploy``/
``re_engaged`` as aliases for the closest canonical state. The dead names
are removed from the enum proper; aliases-on-read keep back-compat. Drop
aliases in v1.0.

See ``tripwire.core.status_contract`` for the issue↔session contract.
"""

from enum import StrEnum


class IssueStatus(StrEnum):
    """Canonical issue states (v0.9.4 contract).

    See `templates/enums/issue_status.yaml` for the authoritative
    definition + label/color metadata. Pre-v0.9.4 names (backlog, todo,
    in_progress, done, canceled) load via ``__missing__`` aliasing for
    back-compat; canonical names emitted on save.
    """

    PLANNED = "planned"
    QUEUED = "queued"
    EXECUTING = "executing"
    IN_REVIEW = "in_review"
    VERIFIED = "verified"
    COMPLETED = "completed"
    ABANDONED = "abandoned"
    DEFERRED = "deferred"

    @classmethod
    def _missing_(cls, value: object) -> "IssueStatus | None":
        """Accept pre-v0.9.4 aliases on read.

        Returns the canonical enum member for legacy strings, or None
        (which lets StrEnum raise ValueError for genuinely unknown
        values).
        """
        if not isinstance(value, str):
            return None
        from tripwire.core.status_contract import normalize_issue_status

        canonical = normalize_issue_status(value)
        if canonical == value:
            return None
        # Re-look-up against the canonical value. Returning the member
        # directly is fine here; StrEnum stores them by value.
        for member in cls:
            if member.value == canonical:
                return member
        return None


class Priority(StrEnum):
    URGENT = "urgent"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Executor(StrEnum):
    AI = "ai"
    HUMAN = "human"
    MIXED = "mixed"


class AgentType(StrEnum):
    PM = "pm"
    EXECUTION_AGENT = "execution-agent"
    VERIFICATION_AGENT = "verification-agent"
    HUMAN = "human"


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
    PRINCIPLE = "principle"
    PRACTICE = "practice"
    GLOSSARY = "glossary"
    METRIC = "metric"
    PERSONA = "persona"
    INVARIANT = "invariant"
    ANTI_PATTERN = "anti_pattern"
    SKILL = "skill"
    CUSTOM = "custom"


# "Definitional" node types live on the concept graph as references
# *for* engineering work rather than as units *of* engineering work.
# They are cited from issues / PRs / agent prompts ad hoc — not via
# the issue → node implementation pipeline that the lint rules
# `coverage/unreferenced_node` and `concept_name_prose/found` were
# designed to police. Counting issue references for them produces
# noise: a `glossary-tripwire` node legitimately has zero issues
# implementing it.
#
# These types are exempted from those two lints. They remain subject
# to every other validator (ref integrity, schema, freshness, etc.).
DEFINITIONAL_NODE_TYPES: frozenset[str] = frozenset(
    {
        NodeType.PRINCIPLE,
        NodeType.PRACTICE,
        NodeType.GLOSSARY,
        NodeType.METRIC,
        NodeType.PERSONA,
        NodeType.INVARIANT,
        NodeType.ANTI_PATTERN,
        NodeType.SKILL,
    }
)


class NodeStatus(StrEnum):
    ACTIVE = "active"
    PLANNED = "planned"
    DEPRECATED = "deprecated"
    STALE = "stale"


class SessionStatus(StrEnum):
    """Canonical session states (v0.9.4) — see
    `templates/enums/session_status.yaml`.

    v0.9.4 prunes 5 dead values that were aspirational v0.7-era names
    never wired into the transition table or any write path: ``active``,
    ``waiting_for_ci``, ``waiting_for_review``, ``waiting_for_deploy``,
    ``re_engaged``. They're accepted on read via ``__missing__`` aliasing
    (collapsing to the closest live state) so any rare legacy data still
    loads, but new writes go to the canonical 9-value set below.
    """

    PLANNED = "planned"
    QUEUED = "queued"
    EXECUTING = "executing"
    IN_REVIEW = "in_review"
    VERIFIED = "verified"
    COMPLETED = "completed"
    PAUSED = "paused"
    FAILED = "failed"
    ABANDONED = "abandoned"

    @classmethod
    def _missing_(cls, value: object) -> "SessionStatus | None":
        """Accept pre-v0.9.4 dead-state aliases on read."""
        if not isinstance(value, str):
            return None
        from tripwire.core.status_contract import normalize_session_status

        canonical = normalize_session_status(value)
        if canonical == value:
            return None
        for member in cls:
            if member.value == canonical:
                return member
        return None


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
    "agent_type": AgentType,
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
