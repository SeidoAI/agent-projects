# Agent Containers — Detailed Plan

## Context

This is the execution layer of the agent development platform. See `overarching-plan.md` for how it fits with agent-project (data) and agent-projects-ui (visibility).

Core responsibility: launch containerised agents that work autonomously, with strict egress, persisted state, and automated re-engagement when feedback arrives.

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

cd /workspace/repo
git config user.name "$AGENT_GIT_USERNAME"
git config user.email "$AGENT_GIT_EMAIL"

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

  claude -p "You are working on issue ${ISSUE_KEY}. Read the issue at ${ISSUE_FILE}. The project repo is at /workspace/project/. Follow the skill instructions in .claude/skills/."
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
          # Call agent-project session re-engage
          # Call agent-containers launch to restart the agent

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
          # agent-project session re-engage <session-id> --trigger human_review_changes --context "..."
          # agent-containers launch <session-id>
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
    4. Call: agent-project session re-engage <id> --trigger ci_failure --context-file <path>
    5. Call: agent-containers launch <id>
    6. Update session status: re_engaged

Event: Verifier submits "request-changes" review
  PM action:
    1. Read verifier's review from GitHub API
    2. Read verified.md if created (FAIL result)
    3. Find session for this issue key
    4. Write re-engagement context with failed criteria
    5. Call: agent-project session re-engage <id> --trigger verifier_rejection --context-file <path>
    6. Call: agent-containers launch <id>

Event: Human submits "request-changes" review
  PM action:
    1. Read review comments from GitHub API
    2. Find session for this issue key
    3. Write re-engagement context with review comments
    4. Call: agent-project session re-engage <id> --trigger human_review_changes --context-file <path>
    5. Call: agent-containers launch <id>

Event: Deploy to test fails
  PM action:
    1. Read deploy logs from GitHub Actions
    2. Find all sessions whose PRs were in this deploy
    3. For each: write re-engagement context, re-engage, re-launch

Event: agent-project node check finds stale nodes
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
Volume: vol-wave1-agent-a
  /workspace/
  ├── repo/          # git clone, with agent's commits and working changes
  ├── project/       # project repo clone
  ├── docs/          # read-only bind mount from project docs
  ├── config/        # session config, re-engage context, issue key
  └── .claude/       # Claude Code session data, skills, settings
```

**First launch:**
```bash
docker volume create vol-wave1-agent-a
docker run \
  --name agent-wave1-a \
  -v vol-wave1-agent-a:/workspace \
  -v /path/to/project/docs:/workspace/docs:ro \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e GITHUB_TOKEN="$GITHUB_TOKEN_BACKEND" \
  -e AGENT_GIT_USERNAME="seido-backend-bot" \
  -e AGENT_GIT_EMAIL="backend-bot@seido.dev" \
  --network agent-net-wave1-a \
  agent-claude-code:latest
```

**Re-engagement (same volume, new container):**
```bash
# Write re-engagement context to volume
docker run --rm -v vol-wave1-agent-a:/workspace alpine \
  sh -c 'cat > /workspace/config/re_engage.yaml << EOF
trigger: ci_failure
timestamp: "2026-03-26T17:15:00"
context:
  failed_checks:
    - name: ruff
      summary: "src/api/auth.py:45 — E302"
EOF'

# Launch new container with same volume
docker run \
  --name agent-wave1-a-re1 \
  -v vol-wave1-agent-a:/workspace \
  -v /path/to/project/docs:/workspace/docs:ro \
  -e ANTHROPIC_API_KEY="$ANTHROPIC_API_KEY" \
  -e GITHUB_TOKEN="$GITHUB_TOKEN_BACKEND" \
  -e AGENT_GIT_USERNAME="seido-backend-bot" \
  -e AGENT_GIT_EMAIL="backend-bot@seido.dev" \
  --network agent-net-wave1-a \
  agent-claude-code:latest
```

**Cleanup (session completed):**
```bash
docker volume rm vol-wave1-agent-a  # only after session marked completed
```

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
                        "enum": ["question", "plan_approval", "progress", "stuck", "escalation", "handover", "fyi"],
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

## Package structure

```
agent-containers/
├── pyproject.toml
├── src/
│   └── agent_containers/
│       ├── __init__.py
│       ├── cli/
│       │   ├── main.py              # Click CLI root
│       │   ├── launch.py            # launch, launch-wave
│       │   ├── manage.py            # list, status, stop, cleanup
│       │   └── terminal.py          # attach, iterm, iterm-all
│       ├── core/
│       │   ├── container.py         # Docker container lifecycle (create, start, stop, rm)
│       │   ├── volume.py            # Docker volume management (create, mount, cleanup)
│       │   ├── network.py           # Egress policy enforcement (network create, iptables)
│       │   ├── workspace.py         # Repo cloning, skill copying, config injection
│       │   ├── re_engage.py         # Write re-engagement context, format triggers
│       │   ├── permissions.py       # Parse agent permissions from agent definition
│       │   └── status.py            # Read/write container + session status
│       ├── integrations/
│       │   ├── iterm.py             # iTerm2 osascript integration
│       │   └── docker_cli.py        # Docker CLI wrapper (subprocess-based)
│       └── templates/
│           ├── entrypoint-claude.sh.j2
│           ├── entrypoint-langgraph.sh.j2
│           └── entrypoint-custom.sh.j2
├── mcp_server/
│   └── agent_messaging.py          # MCP server for agent ↔ human messaging
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
    │   └── test_network.py
    └── integration/
        ├── test_container_lifecycle.py
        └── test_re_engagement_flow.py
```
