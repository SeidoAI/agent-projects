# Overarching Plan: Agent Development Platform

## Vision

Three interconnected projects that together replace Linear + Notion + manual agent orchestration with a fully autonomous, git-native agent development platform.

| Project | What it does | Depends on |
|---------|-------------|------------|
| **agent-project** | Data layer: issues, concept graph, dependencies, status — all as files in git | Nothing (foundation) |
| **agent-containers** | Execution layer: containerised Claude Code agents with strict egress, repo isolation | agent-project (reads issues/sessions, writes status) |
| **agent-projects-ui** | Visibility layer: dashboard for projects, issues, graph, live agent status | agent-project (data) + agent-containers (live status) |

```
┌─────────────────────────────────────────────────────────────┐
│                    agent-projects-ui                         │
│  React 19 · React Flow · Kanban · Agent Monitor · Terminal  │
│                                                             │
│  reads from ↓                              reads from ↓     │
├──────────────────────────┬──────────────────────────────────┤
│     agent-project        │       agent-containers           │
│  Git-native PM data      │  Docker execution environments   │
│  Issues · Nodes · Graph  │  Claude Code · Egress policies   │
│  CLI: agent-project      │  CLI: agent-containers           │
│                          │                                  │
│  ← writes status/comments back to project repo ←           │
└──────────────────────────┴──────────────────────────────────┘
```

---

## How They Interact

### 1. agent-project → agent-containers

The project repo defines **what** work to do. agent-containers reads it to know **how** to execute.

- `sessions/wave1-agent-a.yaml` defines which issues, which repo, which agent type
- `project.yaml` defines repos (with GitHub slugs for cloning), base branches
- `issues/<KEY>.yaml` contains the full issue spec the agent will work from
- `.claude/skills/project-manager/` contains the PM agent skill

Agent definitions live in `agents/` directory — see "Agent Definitions" section below for the full schema. Sessions reference agents by ID.

### 2. agent-containers → agent-project

Agents write back to the project repo via git (PRs):
- Status transitions (issue status updated in YAML)
- Comments (new files in `docs/issues/<KEY>/comments/`)
- Concept nodes (new/updated files in `graph/nodes/`)
- Completion artifacts (`docs/issues/<KEY>/developer.md`)

All changes happen via PRs to the project repo — the PM agent reviews them.

### 3. agent-project + agent-containers → agent-projects-ui

The UI reads from two sources:

**From git (agent-project data):**
- Issue list, statuses, priorities, dependencies
- Concept graph nodes and edges
- Agent session definitions and wave plans
- Project config

**From agent-containers runtime:**
- Which containers are running right now
- Which issue each container is working on
- Container health, logs, resource usage
- Terminal session access (for human intervention)

---

## Agent Definitions (lives in agent-project)

Agents are defined in the project repo under `agents/`. This is distinct from sessions (which assign issues to agents) — agent definitions describe **what kind of agent** something is, what runtime it uses, and what permissions it has.

```yaml
# agents/backend-coder.yaml
---
id: backend-coder
name: "Backend Coding Agent"
description: "Implements backend issues in Python repos"
runtime: claude-code                  # claude-code | langgraph | custom
skill: backend-development            # skill to load (from ide-config or bundled)

# GitHub identity — each agent gets its own bot account or app installation
github_identity:
  username: seido-backend-bot         # GitHub username or app name
  email: backend-bot@seido.dev        # commit email
  token_env: GITHUB_TOKEN_BACKEND     # env var name for the scoped token
  # Branch protection rules prevent pushing to main/test —
  # agents can only push to feature branches and open PRs.

# Permissions and resources (override project-level defaults)
permissions:
  github: read-write
  gcp: none
  network:
    - "github.com"
    - "api.github.com"
    - "pypi.org"
resources:
  memory: "8Gi"
  cpus: 4
tools:
  - git
  - gh
  - uv
  - ruff

# What this agent gets in its workspace
context:
  skills:                             # skills copied into .claude/skills/
    - backend-development
  docs:                               # project docs mounted read-only
    - docs/api-contract.yaml
    - docs/architecture/
  mcp_servers: []                     # MCP servers to start in container

# Multi-ticket capability
multi_ticket: true                    # can handle multiple related issues
max_concurrent_issues: 5              # max issues in one session
grouping_rules:                       # when to group issues for this agent
  same_repo: required                 # must be same repo
  file_overlap: preferred             # prefer overlapping files
  sequential_deps: preferred          # prefer sequential dependency chains
---
```

```yaml
# agents/verifier.yaml
---
id: verifier
name: "Verification Agent"
runtime: claude-code
skill: verification

github_identity:
  username: seido-verifier-bot
  email: verifier-bot@seido.dev
  token_env: GITHUB_TOKEN_VERIFIER

permissions:
  github: read                        # can read PRs, CANNOT push
  gcp: none
  network:
    - "github.com"
    - "api.github.com"
resources:
  memory: "4Gi"
  cpus: 2
tools:
  - git
  - gh
  - uv

context:
  skills:
    - verification
  docs:
    - docs/api-contract.yaml

multi_ticket: false
---
```

```yaml
# agents/pm.yaml
---
id: pm
name: "Project Manager Agent"
runtime: claude-code
skill: project-manager

github_identity:
  username: seido-pm-bot
  email: pm-bot@seido.dev
  token_env: GITHUB_TOKEN_PM

permissions:
  github: read-write                  # can open PRs to project repo
  gcp: none
  network:
    - "github.com"
    - "api.github.com"
resources:
  memory: "4Gi"
  cpus: 2
tools:
  - git
  - gh
  - agent-project                     # PM agent uses the project CLI

context:
  skills:
    - project-manager
  docs:
    - docs/                           # all project docs

# PM-specific: orchestration capabilities
orchestration:
  can_launch_agents: true             # can trigger agent-containers launch
  max_concurrent_agents: 4            # limit on how many agents PM can spin up
  auto_launch_on_status:              # auto-launch rules
    - trigger: "issue moved to todo"
      action: "assign to matching agent, add to next session"
    - trigger: "PR opened"
      action: "launch verifier agent"
    - trigger: "verifier approved"
      action: "notify human for review"
    - trigger: "CI failed on PR"
      action: "re-engage coding agent with failure context"

multi_ticket: false                   # PM handles the whole project, not individual tickets
---
```

### Key design decisions

**Why agent definitions live in the project repo (not in agent-containers):**
- They are project-specific — different projects may have different agent configs
- They are versioned in git — changes to permissions are auditable
- The PM agent can read them to know what agents are available for dispatching
- Sessions reference agent definitions by `id`

**GitHub identities — why separate bot accounts:**
- Each agent type gets its own GitHub identity (username + email)
- Commits are attributed to the right agent: `git log` shows "seido-backend-bot" vs "seido-verifier-bot"
- Scoped tokens per agent: backend bot gets read-write, verifier gets read-only
- Branch protection rules on `main` and `test` prevent direct pushes — agents can only push feature branches and open PRs
- This is enforced at the GitHub level, not just in the container — even if an agent tries to push to main, GitHub rejects it

**Runtime abstraction — not locked to Claude Code:**
- `runtime: claude-code` — runs Claude Code CLI inside the container
- `runtime: langgraph` — runs a LangGraph agent (e.g., the ml-business-agent pattern)
- `runtime: custom` — runs an arbitrary entrypoint script
- The container image varies by runtime, but the workspace layout is the same
- For LangGraph agents: the container starts the graph server, feeds it the issue as input, collects output
- For custom: user provides an entrypoint script in the agent definition

**PM agent orchestration — how it deploys other agents:**
- The PM agent can run from a container OR from a local Claude Code session (just load the skill)
- When containerised, the PM has access to `agent-containers` CLI
- The `orchestration` section defines what the PM is allowed to launch
- `max_concurrent_agents` prevents runaway agent spawning
- `auto_launch_on_status` defines event-driven automation (what triggers agent launches)
- This is the key to removing human-in-the-loop: PM watches for status transitions and auto-dispatches

**Documentation as container input:**
- Agent definitions specify which `docs/` files are mounted into the container
- These are mounted **read-only** — agents can read API contracts, architecture docs, etc.
- This solves the alignment problem: agents always read the latest docs from the project repo
- The concept graph `[[references]]` in docs and issues mean agents can navigate to the actual code

### How sessions reference agents

Sessions point to an agent definition and carry runtime state across re-engagements:

```yaml
# sessions/wave1-agent-a.yaml
---
id: wave1-agent-a
name: "Agent A: Auth + User Model"
agent: backend-coder                  # references agents/backend-coder.yaml
issues: [SEI-40, SEI-42]
wave: 1
repo: SeidoAI/web-app-backend
status: waiting_for_ci                # see "Session Status Lifecycle" below

# Runtime state — persisted across container restarts
runtime_state:
  claude_session_id: "sess_abc123"    # for claude --resume
  langgraph_thread_id: null           # for langgraph checkpoint resume
  workspace_volume: "vol-wave1-a"     # Docker volume preserving workspace
  branch: "claude/SEI-40-auth"
  pr_number: 42

# Re-engagement history — append-only log of every container start
engagements:
  - started_at: "2026-03-26T14:00:00"
    trigger: initial_launch
    ended_at: "2026-03-26T16:30:00"
    outcome: pr_opened

  - started_at: "2026-03-26T17:15:00"
    trigger: ci_failure
    context: "Lint failure in src/api/auth.py:45 — ruff E302"
    ended_at: "2026-03-26T17:25:00"
    outcome: fix_pushed

  - started_at: "2026-03-26T18:00:00"
    trigger: verifier_rejection
    context: "Acceptance criteria #3 not met: expired token returns 200 not 403"
    ended_at: null                     # currently active
    outcome: null
---
```

### Updated project directory structure

```
my-project/
├── project.yaml
├── CLAUDE.md
├── .claude/skills/project-manager/
├── agents/                           # NEW: agent definitions
│   ├── backend-coder.yaml
│   ├── frontend-coder.yaml
│   ├── verifier.yaml
│   └── pm.yaml
├── issues/
├── graph/nodes/
├── docs/
│   ├── issues/
│   ├── api-contract.yaml             # consumed by agents via context.docs
│   └── architecture/
└── sessions/
```

---

## Controlling Everything from the UI

The UI is the human's primary interface for the entire platform. Key control flows:

**Launch agents from UI:**
1. Human selects issues on the Kanban board
2. Clicks "Launch Agent" → UI shows available agent definitions that match (by repo, executor type)
3. Human picks agent + confirms → backend calls `agent-containers launch`
4. Container starts, iTerm tab opens, agent monitor shows live status

**PM agent auto-orchestration (visible in UI):**
1. PM agent proposes a wave plan → visible as a PR in the UI
2. Human approves → PM agent launches agents for wave 1
3. UI shows wave progress: which agents are running, which issues are in progress
4. As agents complete → PM agent auto-launches wave 2 (if plan approved)
5. Human can intervene at any point: stop agent, reassign issue, modify plan

**Manual actions from UI:**
- Stop/restart any agent container
- Open iTerm to any container
- Approve/reject PRs (calls `gh pr merge` or `gh pr close`)
- Edit issue status (drag-and-drop on Kanban)
- Launch validation (`agent-project validate`)
- View and approve PM agent plans
- Delete branches, cleanup containers

---

## Feedback Loops & Agent Re-engagement

### The principle

**Agent context is valuable. Never throw it away. Persist across re-engagements.**

When a coding agent opens a PR and exits, it has built up a mental model of the codebase, the issue, and decisions it made. When CI fails or a reviewer requests changes, the agent should resume with that full context — not start from scratch.

### State persistence model

The container is disposable. The agent state is not.

- **Docker volume** persists the workspace (`/workspace/repo`, `/workspace/project`, `/workspace/.claude/`) across container restarts. Named per-session: `vol-wave1-a`.
- **Claude Code sessions** resume via `claude --resume --session-id <id>`. The session ID is stored in the session YAML.
- **LangGraph checkpoints** resume via thread ID from the checkpoint store. The thread ID is stored in the session YAML.
- **Session YAML** (`sessions/<id>.yaml`) is the persistence anchor — it tracks runtime state, re-engagement history, and current status.

### Session status lifecycle

```
planned → active → waiting_for_ci ──→ re_engaged → active → waiting_for_ci → ...
                 → waiting_for_review → re_engaged → active → ...
                 → waiting_for_deploy → re_engaged → active → ...
                 → completed
                 → failed
```

Statuses:
- `planned` — session defined but not launched yet
- `active` — container running, agent working
- `waiting_for_ci` — PR opened, waiting for CI results
- `waiting_for_review` — CI passed, waiting for verifier/human review
- `waiting_for_deploy` — merged, waiting for deployment result
- `re_engaged` — feedback received, container re-launching (transient)
- `completed` — all issues done, artifacts delivered
- `failed` — unrecoverable failure, human intervention needed

### Re-engagement flow

```
Feedback event (CI failure, review comment, deploy failure, stale node, ...)
    │
    ▼
PM agent or GitHub Action detects event
    │
    ▼
Writes re-engagement entry to session YAML:
  - trigger type (ci_failure, verifier_rejection, human_review_changes, ...)
  - context (error output, review comments, deploy logs, ...)
  - updates session status → re_engaged
    │
    ▼
Calls: agent-containers launch <session-id>
    │
    ▼
Container starts with SAME Docker volume (workspace preserved)
    │
    ▼
Agent resumes with full prior context + new re-engagement prompt:
  "You are being re-engaged. Trigger: ci_failure. Context: <error details>.
   Read the PR comments and CI results, then fix the issues."
```

### Feedback sources → re-engagement triggers

| Source | Trigger type | Session status while waiting | Context injected |
|--------|-------------|------------------------------|-----------------|
| Lint failure | `ci_failure` | `waiting_for_ci` | Failed check name, file, line, error |
| Test failure | `ci_failure` | `waiting_for_ci` | Test name, assertion error, stack trace |
| Build failure | `ci_failure` | `waiting_for_ci` | Build step, error output |
| Type check failure | `ci_failure` | `waiting_for_ci` | File, line, expected vs actual type |
| Verifier rejects | `verifier_rejection` | `waiting_for_review` | Which criteria failed, verifier's review |
| Human requests changes | `human_review_changes` | `waiting_for_review` | Review comments, file/line comments |
| Bug reviewer finding | `bug_found` | `waiting_for_review` | Bug description, affected code, severity |
| Deploy failure | `deploy_failure` | `waiting_for_deploy` | Deploy logs, which service, error |
| Smoke test failure | `deploy_failure` | `waiting_for_deploy` | Test name, expected vs actual |
| Concept node stale | `stale_reference` | any waiting state | Which `[[node]]` changed, diff |
| PM scope change | `scope_change` | any waiting state | Updated issue body, PM's comment |
| Merge conflict | `merge_conflict` | `waiting_for_ci` | Conflicting files, which branch |
| Dependency conflict | `dependency_conflict` | any waiting state | Upstream change details |

Full implementation details (entrypoint scripts, GitHub Actions workflows, context formatting) in `docs/agent-containers.md`.

---

## Agent ↔ Human Messaging

### Principle

Messages between agents and humans are **direct HTTP** from the container to the UI backend. Not git. Messages are ephemeral communication for real-time coordination. The permanent record (decisions, outcomes) ends up in issue comments and completion artifacts which are in git. A message log is persisted to the project repo when a session completes — but individual messages are never committed as they happen.

### How it works

```
Container                    Host machine                Browser
┌──────────┐    HTTP POST    ┌───────────────┐  WebSocket  ┌─────────┐
│ MCP tool: │───────────────→│  UI backend   │────────────→│ React   │
│ send_msg  │                │  :8000        │             │ UI      │
│           │  GET /pending  │  SQLite store │             │         │
│ check_msg │←───────────────│               │             │ Desktop │
│           │                │               │←────────────│ notif   │
└──────────┘                 └───────┬───────┘  respond    └─────────┘
                                     │
                          On session complete:
                          Write messages.yaml
                          to project repo + commit
```

### MCP server in containers

Each container runs a tiny MCP server that exposes two tools to the agent:

**`send_message`** — agent sends a message to the human:
```json
{
  "name": "send_message",
  "description": "Send a message to the human operator via the project dashboard",
  "parameters": {
    "type": { "enum": ["question", "plan_approval", "progress", "stuck", "escalation", "handover", "fyi"] },
    "priority": { "enum": ["blocking", "informational"] },
    "body": { "type": "string", "description": "Markdown-formatted message body" }
  }
}
```

**`check_messages`** — agent checks for pending responses:
```json
{
  "name": "check_messages",
  "description": "Check if the human has responded to any of your messages",
  "parameters": {}
}
```

The MCP server is a single Python file (~80 lines) that proxies these tool calls to `http://host.docker.internal:8000/api/messages`. The session ID is injected via `AGENT_SESSION_ID` env var.

Fallback for non-MCP agents: `/usr/local/bin/agent-msg` shell script (curl wrapper).

### Message types

| Type | When | Priority | Agent behavior after sending |
|------|------|----------|------------------------------|
| `plan_approval` | Before starting implementation | `blocking` | Stop, exit, wait for re-engagement |
| `question` | Needs human input to proceed | `blocking` | Stop, exit, wait for re-engagement |
| `stuck` | Tried multiple approaches, can't proceed | `blocking` | Stop, exit, wait for re-engagement |
| `escalation` | Needs elevated permissions or scope change | `blocking` | Stop, exit, wait for re-engagement |
| `handover` | Giving up, passing to human | `blocking` | Stop, exit |
| `progress` | Milestone reached | `informational` | Keep working |
| `fyi` | Found something interesting, not blocking | `informational` | Keep working |

### Response flow and re-engagement

When human responds to a blocking message:
1. Human types response in UI → `POST /api/messages/:id/respond`
2. UI backend stores response in SQLite
3. UI backend calls `agent-project session re-engage <id> --trigger human_response --context "..."`
4. `agent-containers launch <id>` restarts the container
5. Agent resumes, calls `check_messages` MCP tool, reads the response

New re-engagement triggers:
- `human_response` — generic response to a question
- `plan_approved` — plan was approved (with optional notes)
- `plan_rejected` — plan was rejected (with feedback)

### Message log persistence

Messages live in SQLite for real-time delivery. When a session completes or fails, the UI backend writes the full conversation to `sessions/<session-id>/messages.yaml` in the project repo and commits it. This is the permanent audit trail.

```yaml
# sessions/wave1-agent-a/messages.yaml (committed on session complete)
- id: "001"
  direction: agent_to_human
  type: plan_approval
  priority: blocking
  author: backend-coder
  created_at: "2026-03-26T14:05:00"
  body: |
    ## Implementation Plan
    1. Add token validation middleware...
  response:
    author: maia
    created_at: "2026-03-26T14:12:00"
    body: "Approved. Also validate email format."
    decision: approved

- id: "002"
  direction: agent_to_human
  type: question
  priority: blocking
  author: backend-coder
  created_at: "2026-03-26T15:30:00"
  body: "Which validation approach? Option A or B?"
  response:
    author: maia
    created_at: "2026-03-26T15:45:00"
    body: "Go with Option A."
```

Full implementation details (MCP server code, skill protocol, UI components) in `docs/agent-containers.md` and `docs/agent-projects-ui.md`.

---

## Project 1: agent-project (Data Layer)

**Status:** Detailed plan exists at `docs/agent-projects-plan.md`

**Summary:** Git-native PM with concept graph. Installable Python package with CLI.

**Key outputs consumed by other projects:**
- `project.yaml` — project config, repo registry, agent permissions, status flow
- `issues/` — issue files (YAML frontmatter + Markdown body with `[[references]]`)
- `graph/nodes/` — concept nodes with content hashes for staleness detection
- `sessions/` — agent session definitions (wave-based parallelism)
- `.claude/skills/project-manager/` — PM agent skill for generated repos

**CLI:** `agent-project init`, `issue`, `node`, `refs`, `status`, `graph`, `session`

---

## Project 2: agent-containers (Execution Layer)

### The problems this solves

From the notes:
1. **"Claude requires WAY too many approvals"** — containerisation means agents can't damage the host. You approve the container definition once, then let it run.
2. **"Feedback loops are slow with human-in-the-loop"** — agents run autonomously in containers, CI failures auto-route back to the agent.
3. **"Cloud agents are a necessity"** — define startup script, context, MCP servers. Container IS the reproducible execution environment.
4. **"Need monitoring for agents superior to Claude Code"** — UI shows all containers, their status, and you can SSH in via iTerm2.

### What it does

`agent-containers` is a Python CLI that:
1. **Launches Docker containers** with Claude Code + a repo clone + skills + MCP servers
2. **Enforces strict egress** via Docker network policies (iptables/firewall rules)
3. **Reports container status** via a lightweight status file or API
4. **Integrates with iTerm2** to open terminal tabs for each running agent

### Container architecture

```
┌─────────────────────────────────────────────┐
│  agent-container: backend-coder/SEI-42      │
│                                             │
│  /workspace/                                │
│  ├── repo/          (git clone of target)   │
│  ├── project/       (git clone of project)  │
│  ├── docs/          (read-only mount)       │
│  └── .claude/       (skills, settings)      │
│                                             │
│  Git identity: seido-backend-bot            │
│  Tools: git, gh, uv, node (per agent def)   │
│  Egress: github.com, pypi.org (per agent)   │
│  API keys: ANTHROPIC_API_KEY (injected)     │
│                                             │
│  Runtime: claude-code | langgraph | custom   │
│  Entry varies by runtime:                   │
│    claude-code → claude -p "..."            │
│    langgraph → python -m agent_server       │
│    custom → /workspace/entrypoint.sh        │
│                                             │
│  Status: /tmp/agent-status.json             │
│  └── {state, issue_key, started_at, ...}    │
└─────────────────────────────────────────────┘
```

### Container lifecycle

```
agent-containers launch <session-id>
  1. Read session from project repo: sessions/<session-id>.yaml
  2. Read agent definition from project repo: agents/<agent-id>.yaml
  3. Configure git identity (agent's GitHub username + email + scoped token)
  4. Clone target repo (from session.repo) into container workspace
  5. Clone project repo into container workspace
  6. Mount docs (from agent definition context.docs) as read-only
  7. Copy skills (from agent definition context.skills) into .claude/
  8. Inject API keys (ANTHROPIC_API_KEY, scoped GITHUB_TOKEN — from host env)
  9. Configure egress firewall (Docker network rules from agent permissions)
  10. Select runtime entrypoint:
      - claude-code: start Claude Code with issue as prompt
      - langgraph: start LangGraph server with issue as input
      - custom: run user-provided entrypoint script
  11. Open iTerm2 tab (if --iterm flag or config)
  12. Write container metadata to ~/.agent-containers/active/<session-id>.json
```

### Egress enforcement

Three levels of network control:

**Level 1 — Docker network isolation:**
- Each container on its own bridge network
- No inter-container communication by default
- Host network access blocked

**Level 2 — Egress whitelist (iptables/nftables):**
- Only allow connections to domains in `agents.<role>.permissions.network`
- DNS resolution allowed only for whitelisted domains
- All other outbound traffic dropped

**Level 3 — API-level permissions:**
- `gh` configured with a scoped token (read-only vs read-write per role)
- `gcloud` configured with a scoped service account (or not present at all)
- No ambient credentials from host — everything explicitly injected

### Runtime entrypoints

**Claude Code runtime** (primary):
```bash
#!/bin/bash
cd /workspace/repo
git config user.name "$AGENT_GIT_USERNAME"
git config user.email "$AGENT_GIT_EMAIL"

ISSUE_KEY=$(cat /workspace/config/issue_key)
ISSUE_FILE="/workspace/project/issues/${ISSUE_KEY}.yaml"

# Start Claude Code with the issue as context
claude -p "You are working on issue ${ISSUE_KEY}. Read the issue at ${ISSUE_FILE}. The project repo is at /workspace/project/. Follow the skill instructions."

echo '{"state": "completed", "exit_code": '$?'}' > /tmp/agent-status.json
```

For interactive monitoring (human attaches via iTerm2):
```bash
claude --resume
```

**LangGraph runtime:**
```bash
#!/bin/bash
cd /workspace/repo
git config user.name "$AGENT_GIT_USERNAME"
git config user.email "$AGENT_GIT_EMAIL"

# Start LangGraph agent with issue context as input
python -m agent_server \
  --issue-file "/workspace/project/issues/${ISSUE_KEY}.yaml" \
  --project-dir "/workspace/project" \
  --repo-dir "/workspace/repo"
```

**Custom runtime:**
```bash
#!/bin/bash
# User-provided entrypoint from agent definition
# Gets same workspace layout and environment variables
exec /workspace/config/entrypoint.sh
```

### iTerm2 integration

```python
# Uses osascript to control iTerm2
def open_iterm_tab(container_id: str, session_name: str):
    """Open a new iTerm2 tab attached to a running container."""
    script = f'''
    tell application "iTerm2"
        tell current window
            create tab with default profile
            tell current session of current tab
                set name to "{session_name}"
                write text "docker exec -it {container_id} /bin/bash"
            end tell
        end tell
    end tell
    '''
    subprocess.run(["osascript", "-e", script])
```

For multiple agents, open a split layout:
```
agent-containers launch-wave 1 --iterm
# Opens iTerm2 window with one tab per agent in the wave
# Each tab is docker exec -it <container> bash
```

### CLI commands

```
agent-containers launch <session-id>
  --project-dir TEXT   Path to project repo [default: .]
  --iterm              Open iTerm2 tab for the container
  --detach             Run in background (no iTerm)
  --dry-run            Show what would happen without launching

agent-containers launch-wave <wave-number>
  --project-dir TEXT   Path to project repo
  --plan TEXT          Division plan file (if multiple plans exist)
  --iterm              Open iTerm2 tabs for all agents in wave
  --max-parallel INT   Limit concurrent containers [default: from plan]

agent-containers list
  --format TEXT        table/json [default: table]
  # Shows: session-id, issue, status, container-id, uptime, resource usage

agent-containers status <session-id>
  # Detailed status of one container: logs tail, resource usage, Claude Code state

agent-containers logs <session-id>
  --follow             Stream logs
  --tail INT           Last N lines [default: 50]

agent-containers stop <session-id>
  # Gracefully stop a container

agent-containers stop-all
  # Stop all running agent containers

agent-containers attach <session-id>
  # Docker exec into the container (interactive bash)

agent-containers iterm <session-id>
  # Open iTerm2 tab for an already-running container

agent-containers iterm-all
  # Open iTerm2 tabs for all running containers

agent-containers cleanup
  # Remove stopped containers and dangling images
```

### Container images

**Base image** (shared by all runtimes):
```dockerfile
# docker/Dockerfile.base — common tools for all agents
FROM ubuntu:24.04
RUN apt-get update && apt-get install -y \
    git curl wget jq openssh-client python3 python3-pip nodejs npm \
    && rm -rf /var/lib/apt/lists/*
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
# GitHub CLI
RUN (curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg | \
    dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg) && \
    apt-get update && apt-get install -y gh
RUN pip install agent-project
RUN mkdir -p /workspace/{repo,project,config,docs}
WORKDIR /workspace/repo
```

**Claude Code image** (extends base):
```dockerfile
# docker/Dockerfile.claude-code
FROM agent-base:latest
RUN npm install -g @anthropic-ai/claude-code
COPY entrypoint-claude.sh /usr/local/bin/
ENTRYPOINT ["entrypoint-claude.sh"]
```

**LangGraph image** (extends base):
```dockerfile
# docker/Dockerfile.langgraph
FROM agent-base:latest
RUN pip install langgraph langchain-google-genai
COPY entrypoint-langgraph.sh /usr/local/bin/
ENTRYPOINT ["entrypoint-langgraph.sh"]
```

`agent-containers` selects the right image based on the agent definition's `runtime` field.

### Package structure

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
│       │   ├── container.py         # Docker container lifecycle
│       │   ├── network.py           # Egress policy enforcement
│       │   ├── workspace.py         # Repo cloning, skill copying, config injection
│       │   ├── permissions.py       # Parse agent permissions from project.yaml
│       │   └── status.py            # Read/write container status
│       ├── integrations/
│       │   ├── iterm.py             # iTerm2 osascript integration
│       │   └── docker_client.py     # Docker SDK wrapper
│       └── templates/
│           ├── Dockerfile.agent-base
│           └── entrypoint.sh.j2     # Per-launch entrypoint script
├── tests/
└── docker/
    └── Dockerfile.agent-base
```

---

## Project 3: agent-projects-ui (Visibility Layer)

### The problems this solves

From the notes:
1. **"Need monitoring for agents that is superior to Claude Code"** — a UI showing where agents are, what's running, CI/CD status
2. **"Should be able to take manual actions"** — delete branch, approve plan, cleanup
3. **"Review Claude Code agent plans and approve — in a render of md files"** — Markdown rendering of plans/issues
4. **"Kanban board"** — issues by status
5. **"React Flow Graph"** — concept graph + dependency graph visualised

### Tech stack

Match existing Seido frontend patterns:
- **React 19** + **TypeScript 5.8** + **Vite 7**
- **Tailwind CSS v4** + **shadcn/ui**
- **XyFlow (React Flow)** — already used for graph viz in web-app
- **TanStack Query v5** — data fetching
- **Biome** — linting
- **Vitest** — testing

### Architecture

The UI is a **local development tool** (not a deployed web app). It runs on localhost and reads from:
1. **Git** (project repo on disk) — for issues, nodes, sessions, project config
2. **agent-containers status API** — for live container state
3. **GitHub API** — for PR status, CI checks

```
┌──────────────────────────────────┐
│   agent-projects-ui (React)      │
│   localhost:3000                  │
│                                  │
│   ├── Project Switcher           │
│   ├── Kanban Board (issues)      │
│   ├── Concept Graph (React Flow) │
│   ├── Issue Detail (MD render)   │
│   ├── Node Detail                │
│   ├── Agent Monitor              │
│   │   ├── Running containers     │
│   │   ├── Resource usage         │
│   │   └── Open in iTerm button   │
│   └── Actions                    │
│       ├── Approve plan           │
│       ├── Delete branch          │
│       └── Launch agent           │
└──────────┬───────────────────────┘
           │
           ▼
┌──────────────────────────────────┐
│  Backend: lightweight Python API │
│  (FastAPI, runs alongside UI)    │
│                                  │
│  GET /api/project                │
│  GET /api/issues                 │
│  GET /api/issues/:key            │
│  GET /api/nodes                  │
│  GET /api/graph                  │
│  GET /api/sessions               │
│  GET /api/containers             │  ← reads from agent-containers status
│  POST /api/containers/launch     │  ← calls agent-containers CLI
│  POST /api/actions/approve       │  ← git operations
│  GET /api/github/prs             │  ← gh CLI wrapper
│  WS /api/containers/stream       │  ← live container status updates
└──────────────────────────────────┘
```

Why a backend API instead of reading git directly from the frontend:
- Git operations are filesystem I/O — can't do from a browser
- Docker status requires Docker SDK — server-side only
- GitHub API calls need auth tokens — don't expose to frontend
- WebSocket for live container updates

### UI views

**1. Project Switcher** (sidebar/header)
- List projects found in a configured root directory
- Show project name, key prefix, issue count
- Switch active project

**2. Kanban Board** (main view)
- Columns = statuses from project.yaml (configurable)
- Cards = issues, showing: key, title, priority badge, executor badge, agent name
- Cards colored by staleness (red border if referencing stale nodes)
- Drag-and-drop to change status (calls `agent-project issue update`)
- Filter by: executor, label, parent epic, assignee
- Active agent indicator on cards (green dot if a container is working on this issue)

**3. Concept Graph** (React Flow view)
- Nodes = issues (rectangles) + concept nodes (circles/diamonds by type)
- Edges = `[[references]]` (issue→node), `blocked_by` (issue→issue), `related` (node→node)
- Node coloring: by status (issues), by type (concept nodes), by staleness
- Click node → detail panel
- Filter by: node type, status, epic
- Layout: dagre for hierarchy, force-directed for exploration

**4. Issue Detail** (slide-over panel)
- Rendered Markdown body (with `[[references]]` as clickable links to nodes)
- Frontmatter fields in structured display
- Comments timeline
- Linked PRs and CI status (from GitHub API)
- Agent activity (if container is working on this issue)
- Actions: edit status, edit fields, open in editor

**5. Agent Monitor** (dedicated view or sidebar panel)
- List of running containers: session name, issue key, uptime, memory/CPU
- Status indicators: running, completed, failed, blocked
- Wave visualization: which wave is active, which sessions are complete
- Per-container actions:
  - "Open in iTerm" button (calls `agent-containers iterm`)
  - "View logs" (streams container logs)
  - "Stop" button
- History of completed sessions

**6. Actions Panel**
- Quick actions that would otherwise require terminal:
  - Delete branch + cleanup (`gh` + `git`)
  - Launch agent session (`agent-containers launch`)
  - Approve plan (merge PR via `gh pr merge`)
  - Run validation (`agent-project validate`)
  - Rebuild graph index (`agent-project refs rebuild`)

### Package structure

```
agent-projects-ui/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── biome.json
├── src/
│   ├── app/
│   │   ├── App.tsx
│   │   └── routes.tsx
│   ├── features/
│   │   ├── kanban/                  # Kanban board
│   │   ├── graph/                   # Concept graph (React Flow)
│   │   ├── issues/                  # Issue detail, list
│   │   ├── nodes/                   # Node detail, list
│   │   ├── agents/                  # Agent monitor, container status
│   │   ├── projects/                # Project switcher
│   │   └── actions/                 # Quick actions panel
│   ├── components/
│   │   └── ui/                      # shadcn/ui components
│   ├── hooks/                       # Data fetching hooks
│   ├── lib/
│   │   └── api/                     # API client
│   └── types/
├── backend/                         # Lightweight Python API
│   ├── pyproject.toml
│   ├── src/
│   │   └── agent_projects_api/
│   │       ├── main.py              # FastAPI app
│   │       ├── routes/
│   │       │   ├── project.py
│   │       │   ├── issues.py
│   │       │   ├── nodes.py
│   │       │   ├── graph.py
│   │       │   ├── containers.py
│   │       │   └── actions.py
│   │       └── services/
│   │           ├── git_reader.py    # Read project data from git
│   │           ├── container_status.py
│   │           └── github_client.py
└── tests/
```

---

## Build Order and Dependencies

```
Phase 1: agent-project (data layer)
  ├── Python package: models, parser, store, validator, graph, CLI
  ├── Templates: project scaffold, PM agent skill, issue templates
  └── Deliverable: `pip install agent-project` works, `agent-project init` generates projects

Phase 2: agent-containers (execution layer)  ← depends on agent-project
  ├── Base Docker image with Claude Code + tools
  ├── Python package: container lifecycle, egress, workspace setup, CLI
  ├── iTerm2 integration
  └── Deliverable: `agent-containers launch <session>` runs an autonomous agent

Phase 3: agent-projects-ui (visibility layer)  ← depends on both
  ├── Backend API (FastAPI, wraps git + docker + github)
  ├── React frontend (kanban, graph, agent monitor)
  └── Deliverable: `agent-projects-ui` starts local dashboard

Each phase is independently useful:
  - Phase 1 alone: manage projects via CLI + git
  - Phase 1+2: agents run autonomously, monitor via terminal
  - Phase 1+2+3: full visual dashboard with agent monitoring
```

---

## What lives where

All three projects live in the same directory:

```
/Users/maia/Code/seido/projects/agent-projects/
├── docs/
│   ├── overarching-plan.md          # This document (high-level)
│   ├── agent-projects-plan.md       # Detailed plan for agent-project
│   ├── agent-projects-ui.md         # Detailed plan for UI (to be written)
│   └── agent-containers.md          # Detailed plan for containers (to be written)
│
├── agent-project/                   # Python package: data layer
│   ├── pyproject.toml
│   ├── src/agent_project/
│   └── tests/
│
├── agent-containers/                # Python package: execution layer
│   ├── pyproject.toml
│   ├── src/agent_containers/
│   ├── docker/
│   └── tests/
│
└── agent-projects-ui/               # React + Python: visibility layer
    ├── package.json                 # Frontend
    ├── src/                         # React app
    ├── backend/                     # FastAPI backend
    │   ├── pyproject.toml
    │   └── src/agent_projects_api/
    └── tests/
```

---

## Resolved Decisions

1. **Container runtime**: Any Docker-compatible runtime (Docker Desktop, OrbStack, Colima, Podman). We code against the `docker` CLI which is identical across all runtimes — zero overhead to support all of them. Recommend OrbStack for macOS (lighter than Docker Desktop).
2. **Remote execution**: Local Docker only for Phase 2. Cloud execution (Cloud Run, remote Docker) is a future extension.
3. **UI backend → agent-project**: Import `agent_project` as a Python library directly. Faster, type-safe, no subprocess overhead. The UI backend depends on `agent-project` as a pip dependency.
4. **Auth for UI**: None — local dev tool, bind to localhost only.
5. **Project discovery**: UI scans a configured root directory for projects (any directory containing `project.yaml`).
