# Keel Containers — Detailed Plan

## Context

This is the execution layer of the agent development platform, living
at `src/keel/containers/` within the tripwire package. Installed as part
of `pip install tripwire`. See `overarching-plan.md` for how it fits with
`keel.core` (data) and `keel.ui` (visibility).

Core responsibility: launch containerised agents that work autonomously, with strict egress, persisted state, and automated re-engagement when feedback arrives.

---

## Customisability — Project Repo as the Source of Truth

`keel.containers` is a thin runtime. It ships no skills, no templates, no defaults of its own. Everything customisable lives in the project repo:

- **Skills** — `<project>/.claude/skills/`
- **Agent definitions** — `<project>/agents/`
- **Orchestration patterns** — `<project>/orchestration/`
- **Enums** — `<project>/enums/`
- **Templates** (artifacts, issues, comments, sessions) — `<project>/templates/`

The project repo is the single source of truth and the centre of customisability, auditability, and version control. `tripwire-containers` clones the project repo, mounts what it needs, runs the orchestration pattern the project repo defines, and stays out of the way.

---

## Feedback Loop Implementation

### The full feedback table

Every type of feedback that can reach a coding agent, how it's delivered, and what the agent does.

#### CI Pipeline Failures

| Trigger | Info needed by agent | Delivery | Agent action |
|---------|---------------------|----------|-------------|
| Lint failure (ruff, biome) | File, line, rule ID, error message | PR comment (structured) | Fix lint errors, push |
| Type check failure (ty, tsc) | File, line, expected vs actual type | PR comment (structured) | Fix type errors, push |
| Unit test failure | Test name, assertion error, stack trace, stdout/stderr | PR comment + link to CI run | Read failure, fix code or test, push |
| Integration test failure | Test name, HTTP status/response, service logs | PR comment + relevant logs | Diagnose, fix, push |
| Build failure (Docker, vite) | Build step, error output, exit code | PR comment with log excerpt | Fix build issue, push |
| Terraform validate/plan failure | Resource, error message, diff | PR comment with plan output | Fix tf config, push |
| Spell check failure (codespell) | File, line, misspelled word, suggestion | PR comment | Fix spelling, push |
| Bundle size exceeded | Current size vs limit, which chunks grew | PR comment | Optimize, push |

#### Verification & Review

| Trigger | Info needed by agent | Delivery | Agent action |
|---------|---------------------|----------|-------------|
| Acceptance criteria not met | Which criteria, evidence, expected | PR review (request-changes) + verified.md | Address each criterion, push |
| Reward hacking detected | What was gamed, examples | PR review comment | Rewrite honestly, push |
| Missing test coverage | Untested paths, missing edge cases | PR review with gaps | Add tests, push |
| Requirements mismatch | Requirement text vs implementation | PR review quoting requirement | Re-read requirements, fix |
| API contract mismatch | Expected vs actual shape, `[[contract-node]]` | PR review with diff | Align with contract, push |
| Security concern | Vulnerability type, affected code | PR review (request-changes) | Fix vulnerability, push |
| Human change request | File/line comments, overall review | PR review (request-changes) | Address each comment, push |
| Architecture concern | What's wrong, relevant DEC-xxx | PR review referencing decision | Refactor per guidance, push |
| Scope creep identified | What's out of scope | PR review comment | Remove out-of-scope, push |
| Bug reviewer finding | Bug description, repro steps, severity | PR comment | Fix bug, push |

#### Deployment & Runtime

| Trigger | Info needed by agent | Delivery | Agent action |
|---------|---------------------|----------|-------------|
| Test env deploy failure | Deploy logs, error, which service | Issue comment + status revert | Diagnose, fix, push |
| Smoke test failure | Test name, HTTP response, expected vs actual | Issue comment with output | Fix regression, push |
| Health check failure | Service, endpoint response, timeout | Issue comment with logs | Fix startup issue, push |
| Terraform apply failure | Resource, error, state lock info | Issue comment with output | Fix tf config, push |
| Rollback triggered | What rolled back, why, previous version | Issue comment | Investigate, fix, push |

#### Cross-Agent & Graph

| Trigger | Info needed by agent | Delivery | Agent action |
|---------|---------------------|----------|-------------|
| Concept node changed | `[[node]]`, old/new hash, file diff | PM agent alert via issue comment | Re-read referenced code, verify assumptions |
| Contract node updated | New/removed fields, diff | PM agent comment with diff | Align implementation with new contract |
| Dependency node deprecated | Node now deprecated | PM agent comment | Find replacement, update |
| PM scope change | Updated issue body, PM comment | Issue update + comment | Re-read issue, adjust |
| Blocked notification | Blocking issue stuck | Issue comment from PM | Evaluate workaround |
| Downstream impact | What broke, which issue | Issue comment from PM | Fix interface/contract, push |
| Merge conflict | Conflicting files, branches | Git conflict on push/rebase | Resolve conflicts, push |

### Re-engagement trigger → context mapping

When a re-engagement is triggered, the PM agent or GitHub Action writes a structured context file that the container reads on startup.

```yaml
# /workspace/config/re_engage.yaml (written before container re-launch)
trigger: ci_failure
timestamp: "2026-03-26T17:15:00"
source: github_actions

# Structured context varies by trigger type
context:
  # For ci_failure:
  ci_run_id: 123456
  ci_run_url: "https://github.com/SeidoAI/web-app-backend/actions/runs/123456"
  failed_checks:
    - name: "ruff"
      conclusion: failure
      summary: |
        src/api/auth.py:45:1: E302 expected 2 blank lines, found 1
        src/api/auth.py:67:5: F841 local variable 'token' is assigned but never used
    - name: "pytest"
      conclusion: failure
      summary: |
        FAILED tests/unit/test_auth.py::test_expired_token - AssertionError:
          assert 200 == 403
          Expected 403 for expired token, got 200

  # For verifier_rejection:
  # review_url: "https://github.com/.../pull/42#pullrequestreview-123"
  # failed_criteria:
  #   - criterion: "Expired token returns 403"
  #     evidence: "Verifier tested with expired JWT, got 200 OK"
  #     verifier_comment: "The token expiry check is missing from..."

  # For human_review_changes:
  # review_url: "https://github.com/.../pull/42#pullrequestreview-456"
  # comments:
  #   - file: "src/api/auth.py"
  #     line: 52
  #     body: "This should use the constant from config, not a magic number"
  #   - body: "Overall: good approach but please add error handling for..."

  # For deploy_failure:
  # deploy_run_id: 789
  # environment: test
  # service: "web-app-backend"
  # error_excerpt: "Container failed to start: port 8080 already in use"

  # For stale_reference:
  # stale_nodes:
  #   - node_id: "auth-token-endpoint"
  #     old_hash: "sha256:abc..."
  #     new_hash: "sha256:def..."
  #     file_diff: |
  #       @@ -45,10 +45,15 @@
  #       ... (relevant diff)
```

### Container entrypoint with re-engagement

```bash
#!/bin/bash
# entrypoint-claude.sh — handles both first launch and re-engagement
set -e

# Configure the same git identity in every cloned repo. The session may have
# multiple repos under /workspace/repos/, all writable by the same agent.
for REPO_DIR in /workspace/repos/*/; do
  if [ -d "$REPO_DIR/.git" ]; then
    git -C "$REPO_DIR" config user.name "$AGENT_GIT_USERNAME"
    git -C "$REPO_DIR" config user.email "$AGENT_GIT_EMAIL"
  fi
done

# Default working directory: the first repo. The agent navigates between
# /workspace/repos/<name>/ as needed based on issue/session context.
cd /workspace/repos/"$(ls /workspace/repos | head -n1)"

RE_ENGAGE_FILE="/workspace/config/re_engage.yaml"
SESSION_ID_FILE="/workspace/config/claude_session_id"
ISSUE_KEY=$(cat /workspace/config/issue_key)

if [ -f "$RE_ENGAGE_FILE" ]; then
  # RE-ENGAGEMENT: resume existing session with feedback context
  TRIGGER=$(python3 -c "import yaml; print(yaml.safe_load(open('$RE_ENGAGE_FILE'))['trigger'])")

  # Format context as a readable prompt section
  CONTEXT=$(python3 -c "
import yaml, json
data = yaml.safe_load(open('$RE_ENGAGE_FILE'))
trigger = data['trigger']
ctx = data.get('context', {})
print(f'Trigger: {trigger}')
if 'failed_checks' in ctx:
    for check in ctx['failed_checks']:
        print(f\"\\nFailed: {check['name']}\")
        print(check['summary'])
if 'comments' in ctx:
    for c in ctx['comments']:
        loc = f\"{c.get('file', '')}:{c.get('line', '')}\" if 'file' in c else 'General'
        print(f\"\\n[{loc}] {c['body']}\")
if 'failed_criteria' in ctx:
    for fc in ctx['failed_criteria']:
        print(f\"\\nFailed: {fc['criterion']}\")
        print(f\"Evidence: {fc['evidence']}\")
")

  if [ -f "$SESSION_ID_FILE" ]; then
    SESSION_ID=$(cat "$SESSION_ID_FILE")
    claude --resume --session-id "$SESSION_ID" \
      -p "You are being re-engaged on issue ${ISSUE_KEY}.

${CONTEXT}

Read the latest PR comments and CI results. Fix the issues and push your changes."
  else
    # Session ID not available — start fresh but in same workspace
    claude -p "You are being re-engaged on issue ${ISSUE_KEY}.

${CONTEXT}

The workspace has your previous work. Fix the issues and push your changes."
  fi

  # Clean up re-engage file after processing
  rm -f "$RE_ENGAGE_FILE"
else
  # FIRST LAUNCH: start fresh
  ISSUE_FILE="/workspace/project/issues/${ISSUE_KEY}.yaml"

  claude -p "You are working on issue ${ISSUE_KEY}. Read the issue at ${ISSUE_FILE}. The project repo is at /workspace/project/. Target repos are under /workspace/repos/<name>/ — cd into the right one based on issue context. Follow the skill instructions in .claude/skills/."
fi

# Capture session ID for future re-engagements
# (Implementation depends on Claude Code exposing session ID — may need to read from .claude/ dir)

# Write completion status
EXIT_CODE=$?
echo "{\"state\": \"$([ $EXIT_CODE -eq 0 ] && echo completed || echo failed)\", \"exit_code\": $EXIT_CODE}" > /tmp/agent-status.json
```

### GitHub Actions workflows for automated re-engagement

These live in target repos (not the project repo). They detect feedback events and trigger re-engagement.

#### on-ci-failure.yml

```yaml
name: Re-engage agent on CI failure

on:
  check_suite:
    types: [completed]

jobs:
  re-engage:
    if: github.event.check_suite.conclusion == 'failure'
    runs-on: ubuntu-latest
    steps:
      - name: Extract issue key from branch
        id: parse
        run: |
          BRANCH="${{ github.event.check_suite.head_branch }}"
          if [[ "$BRANCH" =~ ^(claude|codex|cursor)/([A-Z]+-[0-9]+) ]]; then
            echo "issue_key=${BASH_REMATCH[2]}" >> $GITHUB_OUTPUT
            echo "is_agent=true" >> $GITHUB_OUTPUT
          else
            echo "is_agent=false" >> $GITHUB_OUTPUT
          fi

      - name: Collect failure details
        if: steps.parse.outputs.is_agent == 'true'
        id: failures
        run: |
          FAILURES=$(gh api repos/${{ github.repository }}/check-suites/${{ github.event.check_suite.id }}/check-runs \
            --jq '.check_runs[] | select(.conclusion == "failure") | "- \(.name): \(.output.summary // "no details")"')
          echo "summary<<EOF" >> $GITHUB_OUTPUT
          echo "$FAILURES" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Trigger re-engagement
        if: steps.parse.outputs.is_agent == 'true'
        run: |
          # Find the session for this issue key in the project repo
          # Call tripwire session re-engage
          # Call tripwire-containers launch to restart the agent

          # For now, post to PR as a structured comment
          PR=$(gh pr list --head "${{ github.event.check_suite.head_branch }}" --json number --jq '.[0].number')
          gh pr comment "$PR" --body "## CI Failed — Agent Re-engagement

          **Issue:** ${{ steps.parse.outputs.issue_key }}

          ${{ steps.failures.outputs.summary }}

          Re-engaging coding agent with failure context."
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

#### on-review-changes.yml

```yaml
name: Re-engage agent on review changes requested

on:
  pull_request_review:
    types: [submitted]

jobs:
  re-engage:
    if: github.event.review.state == 'changes_requested'
    runs-on: ubuntu-latest
    steps:
      - name: Extract issue key
        id: parse
        run: |
          BRANCH="${{ github.event.pull_request.head.ref }}"
          if [[ "$BRANCH" =~ ^(claude|codex|cursor)/([A-Z]+-[0-9]+) ]]; then
            echo "issue_key=${BASH_REMATCH[2]}" >> $GITHUB_OUTPUT
            echo "is_agent=true" >> $GITHUB_OUTPUT
          fi

      - name: Collect review comments
        if: steps.parse.outputs.is_agent == 'true'
        id: review
        run: |
          BODY="${{ github.event.review.body }}"
          COMMENTS=$(gh api repos/${{ github.repository }}/pulls/${{ github.event.pull_request.number }}/comments \
            --jq '.[] | "[\(.path):\(.line)] \(.body)"')
          echo "body<<EOF" >> $GITHUB_OUTPUT
          echo "$BODY" >> $GITHUB_OUTPUT
          echo "---" >> $GITHUB_OUTPUT
          echo "$COMMENTS" >> $GITHUB_OUTPUT
          echo "EOF" >> $GITHUB_OUTPUT
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Trigger re-engagement
        if: steps.parse.outputs.is_agent == 'true'
        run: |
          echo "Re-engaging agent for ${{ steps.parse.outputs.issue_key }}"
          echo "Review: ${{ steps.review.outputs.body }}"
          # tripwire session re-engage <session-id> --trigger human_review_changes --context "..."
          # tripwire-containers launch <session-id>
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### PM agent auto-re-engagement rules

The PM agent (whether containerised or running locally) watches for events and decides
whether to re-engage coding agents. These rules map to the `orchestration.auto_launch_on_status`
field in the PM agent definition.

```
Event: CI failure on agent branch
  PM action:
    1. Read CI failure output from GitHub API
    2. Find session for this issue key
    3. Write re-engagement context file
    4. Call: tripwire session re-engage <id> --trigger ci_failure --context-file <path>
    5. Call: tripwire-containers launch <id>
    6. Update session status: re_engaged

Event: Verifier submits "request-changes" review
  PM action:
    1. Read verifier's review from GitHub API
    2. Read verified.md if created (FAIL result)
    3. Find session for this issue key
    4. Write re-engagement context with failed criteria
    5. Call: tripwire session re-engage <id> --trigger verifier_rejection --context-file <path>
    6. Call: tripwire-containers launch <id>

Event: Human submits "request-changes" review
  PM action:
    1. Read review comments from GitHub API
    2. Find session for this issue key
    3. Write re-engagement context with review comments
    4. Call: tripwire session re-engage <id> --trigger human_review_changes --context-file <path>
    5. Call: tripwire-containers launch <id>

Event: Deploy to test fails
  PM action:
    1. Read deploy logs from GitHub Actions
    2. Find all sessions whose PRs were in this deploy
    3. For each: write re-engagement context, re-engage, re-launch

Event: tripwire node check finds stale nodes
  PM action:
    1. Find sessions referencing stale nodes (via graph index)
    2. For active/waiting sessions: write stale_reference context
    3. Re-engage affected coding agents

Event: Session stuck in waiting state > threshold
  PM action:
    1. Alert human (via UI notification or issue comment)
    2. Do NOT auto-re-engage — waiting states that time out likely need human judgment
```

---

## Container Lifecycle with Persistence

### Docker volume strategy

Each session gets a named Docker volume that persists across container restarts:

```
Volume: vol-api-endpoints-core
  /workspace/
  ├── repos/         # NEW: multi-repo (was just `repo/`)
  │   ├── web-app-backend/
  │   └── web-app-infrastructure/
  ├── project/       # project repo clone (unchanged)
  ├── docs/          # read-only — merged from agent + issue + session docs
  ├── artifacts/     # NEW: where the agent writes plan/checklists
  ├── config/        # session config, re-engage context, issue key
  └── .claude/       # skills mounted from project repo .claude/skills/
```

### Multi-repo cloning

Sessions declare an array of repos via `session.repos[*]` (see the Session model in `keel-plan.md`). All repos are equal — there is no primary. Each one is cloned into `/workspace/repos/<repo-name>/`, and each gets the same agent git identity configured. The agent can branch and PR in any of them.

### Document mounting from issues, sessions, and agent definitions

`/workspace/docs/` is the union of three doc lists, deduplicated by path and mounted read-only:

- **Agent-level** — `agent.context.docs` from `<project>/agents/<id>.yaml` (existing)
- **Issue-level** — `Issue.docs` from each issue assigned to the session (NEW, optional)
- **Session-level** — `AgentSession.docs` from the session YAML (NEW, optional)

Each path is relative to the project repo. The container launch code reads the issue + session + agent and unions the three lists before mounting at `/workspace/docs/<path>` read-only.

**First launch:**
```bash
docker volume create vol-api-endpoints-core

# For each repo declared in session.repos[*], the launch code clones into
# /workspace/repos/<repo-name>/ and sets the same agent git identity.
# Each merged doc path from agent + issue + session is bind-mounted read-only
# under /workspace/docs/<path>.

docker run \
  --name agent-api-endpoints-core \
  -v vol-api-endpoints-core:/workspace \
  -v /path/to/project/docs/api-contract.yaml:/workspace/docs/api-contract.yaml:ro \
  -v /path/to/project/docs/auth/jwt-spec.md:/workspace/docs/auth/jwt-spec.md:ro \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e GITHUB_TOKEN_BACKEND="$GITHUB_TOKEN_BACKEND" \
  -e GITHUB_TOKEN_INFRA="$GITHUB_TOKEN_INFRA" \
  -e AGENT_GIT_USERNAME="seido-backend-bot" \
  -e AGENT_GIT_EMAIL="backend-bot@seido.dev" \
  --network agent-net-api-endpoints-core \
  agent-claude-code:latest
```

**Re-engagement (same volume, new container):**
```bash
# Write re-engagement context to volume
docker run --rm -v vol-api-endpoints-core:/workspace alpine \
  sh -c 'cat > /workspace/config/re_engage.yaml << EOF
trigger: ci_failure
timestamp: "2026-03-26T17:15:00"
context:
  failed_checks:
    - name: ruff
      summary: "src/api/auth.py:45 — E302"
EOF'

# Launch new container with same volume — repos already cloned in /workspace/repos/
docker run \
  --name agent-api-endpoints-core-re1 \
  -v vol-api-endpoints-core:/workspace \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e GITHUB_TOKEN_BACKEND="$GITHUB_TOKEN_BACKEND" \
  -e GITHUB_TOKEN_INFRA="$GITHUB_TOKEN_INFRA" \
  -e AGENT_GIT_USERNAME="seido-backend-bot" \
  -e AGENT_GIT_EMAIL="backend-bot@seido.dev" \
  --network agent-net-api-endpoints-core \
  agent-claude-code:latest
```

**Cleanup (session completed):**
```bash
docker volume rm vol-api-endpoints-core  # only after session marked completed
```

---

## Skills — Loaded from the Project Repo

`tripwire-containers` ships **no skills**. Every skill an agent reads comes from the project repo's `.claude/skills/` directory at container launch time. There is no "packaged default skill" baked into the runtime image.

How skills get into the project repo: the `tripwire` package ships them as defaults under `templates/skills/`. `tripwire init` copies the entire `templates/skills/` tree into the new project's `.claude/skills/`. After init, the project owns them — they are committed to git, version-controlled, auditable, and freely editable per project. Two projects can have completely different rules for messaging, both fully under their own control.

### `setup_skills()` — workspace.py

Before the agent starts, `keel_containers/core/workspace.py` calls a `setup_skills()` function that copies the required skills from the project repo into the container workspace.

```python
# keel_containers/core/workspace.py
def setup_skills(workspace_dir: Path, project_dir: Path, agent: AgentDefinition):
    """Copy required skills from the project repo into the container workspace."""
    project_skills_dir = project_dir / ".claude" / "skills"
    workspace_skills_dir = workspace_dir / ".claude" / "skills"

    # Default skills that every agent gets, regardless of agent definition
    default_skills = ["agent-messaging"]

    # Skills the agent definition asks for (e.g. "backend-development", "verification")
    agent_skills = agent.context.skills

    for skill_name in default_skills + agent_skills:
        src = project_skills_dir / skill_name
        if not src.exists():
            raise ConfigError(
                f"Skill '{skill_name}' not found at {src}. "
                f"Run 'tripwire init' to install default skills, "
                f"or add it manually to .claude/skills/."
            )
        copy_tree(src, workspace_skills_dir / skill_name)
```

### Default and per-agent skills

- **Default for every agent**: `["agent-messaging"]` — loaded regardless of what the agent definition says, so every container can talk to the human via the MCP messaging server.
- **Per-agent**: whatever is listed in `agent.context.skills` — typical examples are `backend-development`, `frontend-development`, `verification`, `project-manager`.

If a required skill is missing from `<project>/.claude/skills/`, `setup_skills()` raises a `ConfigError` with a hint to run `tripwire init`. The container does not start with missing skills.

---

## Agent Messaging — MCP Server

### MCP server implementation

A tiny MCP server pre-installed in every container image. It proxies tool calls to the UI backend via HTTP.

```python
# mcp_server/agent_messaging.py (~80 lines)
"""MCP server that exposes send_message and check_messages tools."""

import os
import json
import urllib.request
from mcp.server import Server
from mcp.types import Tool, TextContent

AGENT_MSG_URL = os.environ.get("AGENT_MSG_URL", "http://host.docker.internal:8000/api/messages")
SESSION_ID = os.environ["AGENT_SESSION_ID"]

server = Server("agent-messaging")

@server.list_tools()
async def list_tools():
    return [
        Tool(
            name="send_message",
            description="Send a message to the human operator via the project dashboard. Use 'blocking' priority when you need a response before continuing (you should stop working after sending). Use 'informational' for progress updates (keep working).",
            inputSchema={
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": [
                            "question", "plan_approval", "progress", "stuck", "escalation",
                            "handover", "fyi", "status",   # NEW
                        ],
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["blocking", "informational"],
                    },
                    "body": {
                        "type": "string",
                        "description": "Markdown-formatted message body",
                    },
                },
                "required": ["type", "priority", "body"],
            },
        ),
        Tool(
            name="check_messages",
            description="Check if the human has responded to any of your pending messages. Returns a list of responses.",
            inputSchema={"type": "object", "properties": {}},
        ),
    ]

@server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "send_message":
        payload = json.dumps({
            "session_id": SESSION_ID,
            "type": arguments["type"],
            "priority": arguments["priority"],
            "body": arguments["body"],
        }).encode()
        req = urllib.request.Request(
            AGENT_MSG_URL,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        resp = urllib.request.urlopen(req)
        result = json.loads(resp.read())
        return [TextContent(type="text", text=f"Message sent (id: {result['id']}). "
            + ("STOP WORKING and exit — you will be re-engaged when the human responds."
               if arguments["priority"] == "blocking"
               else "Message delivered. Continue working."))]

    elif name == "check_messages":
        req = urllib.request.Request(
            f"{AGENT_MSG_URL}/pending?session_id={SESSION_ID}",
            method="GET",
        )
        resp = urllib.request.urlopen(req)
        messages = json.loads(resp.read())
        if not messages:
            return [TextContent(type="text", text="No pending responses.")]
        formatted = []
        for msg in messages:
            formatted.append(f"Response to message {msg['in_reply_to']}:\n{msg['body']}")
        return [TextContent(type="text", text="\n---\n".join(formatted))]
```

### Status messages — structured body

Unlike other message types where `body` is free Markdown, `status` has a structured body with two fields: `state` and `summary`.

```json
{
  "type": "status",
  "priority": "informational",
  "body": {
    "state": "implementing",
    "summary": "Wired the JWT middleware into the auth router. Now writing unit tests for the validation logic."
  }
}
```

- **`state`** — drawn from the `AgentState` enum. The enum is defined in `tripwire` and is customisable per project via `<project>/enums/agent_state.yaml`. Default states: `investigating`, `planning`, `awaiting_plan_approval`, `implementing`, `testing`, `debugging`, `refactoring`, `documenting`, `self_verifying`, `blocked`, `handed_off`, `done`.
- **`summary`** — 1-2 sentences, plain text. Captures what just happened and what's next.
- **Priority** — always `informational`. A status message never blocks the agent — it sends and keeps working.

**Convention**: agents send a status message every 5 minutes of active work, plus on every state transition (e.g. moving from `planning` to `implementing`). The orchestrator updates `session.current_state` from the latest status message, and the UI displays the current state as a badge on the session card.

### Container configuration for MCP

In Claude Code containers, the MCP server is registered in `.claude/settings.json`:

```json
{
  "mcpServers": {
    "agent-messaging": {
      "command": "python3",
      "args": ["/usr/local/lib/mcp_server/agent_messaging.py"],
      "env": {
        "AGENT_MSG_URL": "http://host.docker.internal:8000/api/messages",
        "AGENT_SESSION_ID": "${AGENT_SESSION_ID}"
      }
    }
  }
}
```

For LangGraph/custom agents, call the HTTP endpoint directly:

```python
import httpx

def send_message(msg_type: str, priority: str, body: str):
    httpx.post(
        f"{os.environ['AGENT_MSG_URL']}",
        json={"session_id": os.environ["AGENT_SESSION_ID"],
              "type": msg_type, "priority": priority, "body": body},
    )
```

### Fallback shell script

For agents that don't use MCP or Python:

```bash
#!/bin/bash
# /usr/local/bin/agent-msg
# Usage: agent-msg <type> <priority> <body>
curl -s -X POST "${AGENT_MSG_URL:-http://host.docker.internal:8000/api/messages}" \
  -H "Content-Type: application/json" \
  -d "{\"session_id\": \"${AGENT_SESSION_ID}\", \"type\": \"$1\", \"priority\": \"$2\", \"body\": \"$3\"}"
```

### Skill communication protocol

The coding agent and PM agent skills should include instructions on when to use messaging:

```markdown
## Communication with Human Operator

You have a `send_message` MCP tool to communicate with the human operator.

### Mandatory: Plan approval before implementation
Before writing any code, create your implementation plan and send it for approval:
  - Use send_message with type="plan_approval", priority="blocking"
  - Include your full plan as the body (Markdown formatted)
  - STOP after sending — do not write code until approved
  - You will be re-engaged with the approval or feedback

### When to send blocking messages (you must stop after sending):
- You have a question that blocks correct implementation
- You're stuck after trying 3+ approaches
- You need permissions or scope change
- You're handing over to a human

### When to send informational messages (keep working):
- You've reached a milestone (e.g., "tests written, implementing now")
- You found something interesting outside your scope
- Completion notification

### Reading responses
After re-engagement, use the `check_messages` tool to read any responses
from the human before continuing work.
```

### Network egress for messaging

`host.docker.internal:8000` must be allowed in the container network configuration.
This is not external internet — it's the host machine. Add to every agent's implicit
egress whitelist (not user-configurable, always allowed):

```python
# In core/network.py
IMPLICIT_EGRESS = [
    "host.docker.internal:8000",  # UI backend for messaging
]
```

---

## CLI Commands

### Single-container launch and lifecycle

```
tripwire-containers launch <session-id>          # foreground attached to current terminal
tripwire-containers launch <session-id> --detach # background
tripwire-containers stop <session-id>
tripwire-containers list
tripwire-containers status <session-id>
tripwire-containers cleanup <session-id>
```

The `--iterm` flag has been removed from `launch`. The user already runs the CLI from a terminal — spawning another one to attach to the same agent is pointless. Default is foreground; `--detach` runs the container in the background.

### Batch launch

```
tripwire-containers launch-batch <session-id> [<session-id> ...]  # all detached
tripwire-containers launch-batch <session-id> [<session-id> ...] --terminal  # spawn one terminal per agent
```

`launch-batch` brings up multiple containers at once. With `--terminal`, the configured terminal launcher (see below) opens a tab/window per agent.

### Open a terminal for a running container

```
tripwire-containers terminal <session-id>      # opens a terminal attached to one container
tripwire-containers terminal-all               # opens terminals for all running containers
```

These replace the removed `iterm` and `iterm-all` subcommands. Both use the configured terminal launcher and run `docker exec -it <container> /bin/bash` inside.

### Terminal launcher — configurable

Different users use different terminals. The launcher is configured in `~/.tripwire-containers/config.yaml`:

```yaml
# ~/.tripwire-containers/config.yaml
terminal_launcher:
  command: iterm           # iterm | terminal | ghostty | alacritty | kitty | wezterm | tmux | none
  # OR fully custom:
  custom: |
    osascript -e 'tell application "Ghostty" to ...'
```

Built-in launchers:

| Name | macOS | Linux | Notes |
|------|-------|-------|-------|
| `iterm` | osascript → iTerm2 | n/a | macOS only |
| `terminal` | osascript → Terminal.app | n/a | macOS only |
| `ghostty` | osascript → Ghostty | xdotool / dbus | cross-platform |
| `alacritty` | `alacritty -e ...` | `alacritty -e ...` | spawns new windows |
| `kitty` | `kitty @ launch ...` | same | uses kitty remote control |
| `wezterm` | `wezterm cli spawn ...` | same | |
| `tmux` | new tmux window | new tmux window | requires existing tmux session |
| `none` | no terminal spawning | no terminal spawning | run all `--detach` |

If no config file is present, the default is `none` (run detached, user opens terminals manually if desired). Users can opt in to a specific launcher.

For fully custom setups, set `terminal_launcher.custom` with a shell command template. The launcher abstraction passes the `docker exec` command in via a placeholder.

---

## Orchestration Runtime

A new Python module `keel_containers/core/orchestration.py` is the orchestration runtime. It **lives in tripwire-containers but is configured by the project repo**. The patterns and hooks live in `<project>/orchestration/`. The runtime reads them on every event.

This matches the broader principle: the project repo is the configuration; `tripwire-containers` is the engine that executes that configuration.

### Key functions

- **`load_pattern(project_dir, name)`** — reads `<project>/orchestration/<name>.yaml`
- **`merge_overrides(pattern, session)`** — applies session-level overrides on top of project default
- **`evaluate_event(pattern, event, ctx)`** — looks up matching event, evaluates conditions, returns action list
- **`run_action(action, ctx)`** — executes a built-in action: `re_engage`, `launch_agent`, `send_message`, `wait_for`, `merge_pr`, `notify_human`, `require_artifact`, `update_session_status_summary`, `publish_to_ui`, plus `if/then/else` branches
- **`call_hook(hook_name, event, ctx)`** — invokes a Python hook from `<project>/orchestration/hooks/`

### Event sources

The orchestrator reacts to events from:

- File watcher on the project repo (issue/session/artifact changes)
- WebSocket messages from running containers (agent status updates)
- GitHub webhook polling (CI status, PR reviews)
- MCP messages from agents (plan ready, status updates, blocking questions)

### Deterministic runtime + Claude-driven PM agent

The PM agent (a Claude-driven container) handles judgement-heavy decisions: plan review, scope changes, conflict resolution. The deterministic orchestrator handles the simple event → action flows defined in the YAML pattern. They work together — the YAML rules can call out to the PM agent (via `launch_agent`) for any decision that needs reasoning.

---

## PM Agent Project-Repo PR Review

Coding agents push PRs to two places:

- **Target repos** — `web-app-backend`, `web-app-infrastructure`, etc. — containing the actual code changes.
- **Project repo** — containing updates to issues, sessions, concept nodes, comments, and artifacts produced during the session.

The PM agent's job is to review the **project-repo PRs** before they land. Code-PR review on target repos is handled by the verifier agent (separate flow).

### Checks

When a coding agent opens a PR to the project repo, the PM agent runs the following checks:

1. **Schema validation** — every changed YAML file passes pydantic validation
2. **Reference integrity** — all `[[node-id]]` references in changed files resolve to existing nodes
3. **Status transition validity** — issue/session status transitions match `project.yaml` rules
4. **Required-fields check** — issues have all required frontmatter (executor, verifier, repo, etc.)
5. **Markdown structure** — issue bodies have all required sections (Context, Acceptance criteria, etc.)
6. **Concept node freshness** — newly added/edited nodes have valid `source` (file exists, hash computed)
7. **Artifact presence** — sessions in `completed` state have all artifacts marked `required: true` in `templates/artifacts/manifest.yaml` (default set: `plan.md`, `task-checklist.md`, `verification-checklist.md`, `recommended-testing-plan.md`, `post-completion-comments.md`)
8. **No orphan additions** — new nodes are referenced by at least one issue or marked `planned`
9. **Comment provenance** — new comments have valid author + type
10. **Project standards** — free-form rules in `templates/standards.md`

### Outcomes

- **All pass** → PM posts an approval review on the PR. If `auto_merge_on_pass` is enabled in the active orchestration pattern, the PM also merges.
- **Any fail** → PM posts a `request_changes` review with specific feedback per failing check, and the orchestrator re-engages the coding agent with the failures as context.

### Invocation

The PM agent invokes the tripwire CLI:

```
tripwire pm review-pr <pr-number> --repo <project-repo>
```

This command runs all checks against the diff, prints results, and returns a non-zero exit code on any failure. The PM agent (containerised or not) calls it directly.

---

## Package structure

```
tripwire-containers/
├── pyproject.toml
├── src/
│   └── keel_containers/
│       ├── __init__.py
│       ├── cli/
│       │   ├── main.py              # Click CLI root
│       │   ├── launch.py            # launch, launch-batch
│       │   ├── manage.py            # list, status, stop, cleanup
│       │   └── terminal.py          # terminal, terminal-all
│       ├── core/
│       │   ├── container.py         # Docker container lifecycle (create, start, stop, rm)
│       │   ├── volume.py            # Docker volume management (create, mount, cleanup)
│       │   ├── network.py           # Egress policy enforcement (network create, iptables)
│       │   ├── workspace.py         # Multi-repo cloning, doc mounting, setup_skills() (loads
│       │   │                        #   skills from <project>/.claude/skills/), config injection
│       │   ├── orchestration.py     # NEW: orchestration runtime — reads patterns from
│       │   │                        #   <project>/orchestration/, evaluates events, runs actions
│       │   ├── re_engage.py         # Write re-engagement context, format triggers
│       │   ├── permissions.py       # Parse agent permissions from agent definition
│       │   └── status.py            # Read/write container + session status
│       ├── integrations/
│       │   ├── terminals/           # Terminal launcher abstraction (one file per launcher)
│       │   │   ├── launcher.py      # Abstract base + dispatch from config
│       │   │   ├── iterm.py
│       │   │   ├── terminal.py
│       │   │   ├── ghostty.py
│       │   │   ├── alacritty.py
│       │   │   ├── kitty.py
│       │   │   ├── wezterm.py
│       │   │   ├── tmux.py
│       │   │   └── none.py
│       │   └── docker_cli.py        # Docker CLI wrapper (subprocess-based)
│       └── templates/                # Jinja2 templates for shell scripts ONLY.
│                                     # No skills, no agent defaults — those live in the
│                                     # project repo (shipped via the tripwire package).
│           ├── entrypoint-claude.sh.j2
│           ├── entrypoint-langgraph.sh.j2
│           └── entrypoint-custom.sh.j2
├── mcp_server/                       # Runtime binary that runs INSIDE the container.
│   └── agent_messaging.py            #   The skill that teaches its use ships in the
│                                     #   tripwire templates, NOT here.
├── scripts/
│   └── agent-msg                    # Fallback shell script (curl wrapper)
├── docker/
│   ├── Dockerfile.base
│   ├── Dockerfile.claude-code
│   └── Dockerfile.langgraph
└── tests/
    ├── unit/
    │   ├── test_permissions.py
    │   ├── test_re_engage.py
    │   ├── test_workspace.py
    │   ├── test_orchestration.py
    │   └── test_network.py
    └── integration/
        ├── test_container_lifecycle.py
        └── test_re_engagement_flow.py
```
