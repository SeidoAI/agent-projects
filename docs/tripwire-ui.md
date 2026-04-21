# Keel UI — Detailed Plan

## Context

Command-and-control centre for the agent development platform. Local
development tool (localhost only). Part of the `tripwire` package — lives
at `src/keel/ui/` alongside `keel.core` and `keel.cli`.

**Tech stack**: React 19, TypeScript 5.8, Vite 7, Tailwind CSS v4,
shadcn/ui, React Flow (XyFlow), TanStack Query v5, Biome, Vitest.
Backend: FastAPI (Python), imported directly from `keel.core`.

**Source-of-truth principle**: All customisable data — enums, templates,
orchestration patterns, artifact manifests, skills — comes from the
project repo, not from the tripwire package. The UI is purely a visualizer
and command surface; it never owns config.

---

## v1 Scope

**v1 ships with:** Project list/switch, kanban board, concept graph
visualisation, issue detail, node detail, session list/detail,
artifact viewer, validation status, phase display, WebSocket live
updates from file watching.

**v2 (future):** Container management, agent messaging, GitHub PR
integration, approval queue, PM reviews, desktop notifications. These
features depend on `keel.containers` which is not yet implemented.
The v1 architecture is designed to accommodate them — routes, services,
and WebSocket events are defined but stubbed.

---

## 1. Startup Experience

### For new users — zero config

```bash
pip install tripwire-pm       # installs everything including UI
tripwire ui                   # starts dashboard, opens browser
```

What happens:
1. FastAPI backend starts on `localhost:8000`
2. Pre-built frontend static files served by backend at `localhost:8000`
3. Browser opens automatically
4. Auto-discovers projects — scans for `project.yaml` in:
   - Current directory
   - `~/.tripwire/config.yaml` configured roots (if file exists)
   - Common locations: `~/Code/**/project.yaml` (shallow, max 2 levels)
5. One project found → go straight to it
6. Multiple → project switcher
7. None → "No projects found" with instructions to run `tripwire init`

If tripwire was installed with `pip install "tripwire-pm[projects]"` (minimal),
`tripwire ui` prints: "UI requires the full tripwire install. Run: pip install tripwire-pm"

### Configuration (optional)

```yaml
# ~/.tripwire/config.yaml
project_roots:
  - ~/Code/seido/projects
  - ~/Code/other-org/projects
default_project: ~/Code/seido/projects/seido-mvp
port: 8000
open_browser: true
```

### CLI

```
tripwire ui
  --project-dir TEXT    Open directly to this project [default: auto-discover]
  --port INT            Port [default: 8000]
  --no-browser          Don't auto-open browser
  --dev                 Dev mode: Vite on :3000 proxying to backend on :8000
```

### For UI developers

```bash
cd src/keel/ui/frontend   # React source (within the tripwire repo)
npm install && npm run dev        # Vite :3000, proxies /api → :8000
# Separate terminal:
tripwire ui --dev             # FastAPI backend on :8000 with auto-reload
```

### Packaging

The pip package bundles pre-built frontend statics at
`src/keel/ui/static/`. Backend serves them directly — no Node.js
process needed. The `static/` directory is git-ignored; CI builds it
from `src/keel/ui/frontend/` before publishing to PyPI.

```python
# src/keel/ui/server.py
if not dev_mode:
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True))
```

---

## 2. Backend Architecture

### Stack

- **FastAPI** (async, WebSocket built-in)
- **keel.core** imported directly (same package)
- **Docker CLI** via subprocess for container management (v2)
- **`gh` CLI** via subprocess for GitHub API (v2)
- **SQLite** for message storage (`~/.tripwire/messages.db`) (v2)
- **watchdog** for filesystem monitoring
- **uvicorn** as ASGI server

### Service layer

```
src/keel/ui/
├── __init__.py
├── server.py                  # FastAPI app, lifespan, static file serving
├── config.py                  # Load ~/.tripwire/config.yaml
├── dependencies.py            # FastAPI Depends() — project context, services
│
├── routes/
│   ├── projects.py            # GET /api/projects[/:id]
│   ├── issues.py              # GET/PATCH /api/projects/:id/issues[/:key], validate
│   ├── nodes.py               # GET /api/projects/:id/nodes[/:nodeId], check freshness
│   ├── graph.py               # GET /api/projects/:id/graph/{deps,concept}
│   ├── sessions.py            # GET /api/projects/:id/sessions[/:sid]
│   ├── agents.py              # GET /api/projects/:id/agents[/:aid]
│   ├── containers.py          # (v2) GET/POST /api/containers — launch, stop, stats, logs
│   ├── messages.py            # (v2) POST/GET /api/messages — agent messaging
│   ├── github.py              # (v2) GET /api/github/prs, checks, reviews
│   ├── artifacts.py           # GET/POST /api/projects/:id/sessions/:sid/artifacts[/:name]
│   ├── pm_reviews.py          # (v2) GET/POST /api/projects/:id/pm-reviews[/:pr]
│   ├── orchestration.py       # GET /api/projects/:id/orchestration/pattern
│   ├── enums.py               # GET /api/projects/:id/enums/:name
│   ├── actions.py             # POST /api/actions/{action}
│   └── ws.py                  # WebSocket /api/ws
│
├── services/
│   ├── project_service.py     # Discover + load projects via keel.core.store
│   ├── issue_service.py       # CRUD via keel.core.store
│   ├── node_service.py        # CRUD via keel.core.node_store
│   ├── graph_service.py       # Build graphs via keel.core.concept_graph
│   ├── session_service.py     # Read sessions
│   ├── container_service.py   # (v2) Docker CLI wrapper
│   ├── github_service.py      # (v2) gh CLI wrapper
│   ├── message_service.py     # SQLite CRUD for messages
│   ├── artifact_service.py    # Read artifact manifest + files, approve/reject gates
│   ├── pm_review_service.py   # Run PM PR review checks via keel.core.pm_review
│   ├── orchestration_service.py # Resolve active orchestration pattern with overrides
│   ├── file_watcher.py        # watchdog filesystem monitor → event queue
│   └── action_service.py      # Execute actions (delete branch, merge PR, validate)
│
└── ws/
    ├── hub.py                 # WebSocket connection manager + broadcast
    └── events.py              # Event type definitions
```

### Dependency injection

```python
# dependencies.py
class ProjectContext:
    def __init__(self, project_dir: Path):
        self.project_dir = project_dir
        self.config = load_project(project_dir)

async def get_project(project_id: str) -> ProjectContext:
    project_dir = resolve_project_dir(project_id)
    return ProjectContext(project_dir)

# Usage:
@router.get("/api/projects/{project_id}/issues")
async def list_issues(project: ProjectContext = Depends(get_project)):
    return list_issues(project.project_dir)
```

### Key services

**IssueService** — imports `keel.core.store` directly:
- `list(filters)` → `list_issues(project_dir, filters)`
- `get(key)` → `load_issue(project_dir, key)`
- `update_status(key, status)` → load, mutate, `save_issue()`
- `validate(key?)` → `validate_issue(project_dir, key)`
- `get_references(key)` → `extract_references(issue.body)`

**ContainerService** — Docker CLI via subprocess:
- `list_running()` → `docker ps --filter label=keels --format json`
- `get_stats(id)` → `docker stats <id> --no-stream --format json`
- `get_logs(id, tail)` → `docker logs <id> --tail N`
- `stop(id)` → `docker stop <id>`
- `launch(session_id, project_dir)` → delegates to `tripwire-containers launch`

**GitHubService** — `gh` CLI via subprocess:
- `list_prs(repo, head?)` → `gh pr list --repo R --json ...`
- `get_checks(repo, pr)` → `gh pr checks N --repo R --json ...`
- `get_reviews(repo, pr)` → `gh api repos/R/pulls/N/reviews`
- `merge_pr(repo, pr)` → `gh pr merge N --repo R --merge`
- `close_pr(repo, pr)` → `gh pr close N --repo R`

**MessageService** — SQLite:
- `create(session_id, type, priority, body)` → INSERT + broadcast via WebSocket
- `list(session_id)` → SELECT WHERE session_id
- `get_pending(session_id)` → SELECT WHERE session_id AND status='pending' AND direction='human_to_agent'
- `respond(id, body, decision?)` → UPDATE + broadcast
- `unread_count()` → COUNT WHERE status='unread' AND priority='blocking'
- `finalize(session_id, project_dir)` → export to YAML, write to project repo, commit

---

## 3. Real-time File Watching

### Mechanism

Backend uses `watchdog` to monitor project directories. Changes to `issues/`, `graph/nodes/`, `sessions/`, `agents/`, `project.yaml` emit events via WebSocket.

### Classification

| Path pattern | Entity type | Entity ID |
|-------------|-------------|-----------|
| `issues/*.yaml` | `issue` | filename stem (e.g. `SEI-42`) |
| `graph/nodes/*.yaml` | `node` | filename stem |
| `sessions/*.yaml` | `session` | filename stem |
| `agents/*.yaml` | `agent_def` | filename stem |
| `project.yaml` | `project` | `config` |

### Debouncing

200ms debounce per file — git operations (pull, merge) touch files multiple times rapidly.

### Lifespan

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    event_queue = asyncio.Queue()
    observer = Observer()
    for project_dir in discover_projects():
        handler = ProjectFileHandler(project_dir, event_queue)
        observer.schedule(handler, str(project_dir), recursive=True)
    observer.start()
    broadcaster = asyncio.create_task(broadcast_events(event_queue, app.state.ws_hub))
    yield
    observer.stop(); observer.join(); broadcaster.cancel()
```

### Frontend cache invalidation

```typescript
// On WebSocket file_changed event:
// issue → invalidate ["issues"] + ["issues", entity_id]
// node → invalidate ["nodes"] + ["graph"]
// session → invalidate ["sessions"]
// project → invalidate ["project"]
```

---

## 4. WebSocket Event Model

### Endpoint

```
WS /api/ws?project={project_id}
```

Single connection per client. JSON events with `type` discriminator.

### Event types

```typescript
type FileChangedEvent = {
  type: "file_changed";
  entity_type: "issue" | "node" | "session" | "agent_def" | "project";
  entity_id: string;
  action: "created" | "modified" | "deleted";
  path: string;
  timestamp: string;
};

type ContainerStatusEvent = {
  type: "container_status";
  session_id: string;
  container_id: string;
  status: "running" | "exited" | "stopped";
  exit_code: number | null;
  cpu_percent: string;
  memory_usage: string;
  timestamp: string;
};

type MessageReceivedEvent = {
  type: "message_received";
  session_id: string;
  message_id: string;
  direction: "agent_to_human" | "human_to_agent";
  msg_type: string;
  priority: string;
  author: string;
  preview: string;           // first 200 chars
  timestamp: string;
};

type GitHubEvent = {
  type: "github_event";
  event_type: "checks_completed" | "review_submitted" | "pr_merged" | "pr_closed";
  repo: string;
  pr_number: number;
  details: Record<string, unknown>;
  timestamp: string;
};

type StatusUpdateEvent = {
  type: "status_update";
  session_id: string;
  state: string;             // from agent_state enum
  summary: string;           // 1-2 sentence plain text
  timestamp: string;
};

type ArtifactUpdatedEvent = {
  type: "artifact_updated";
  session_id: string;
  artifact_name: string;     // e.g. "task-checklist"
  file: string;              // e.g. "task-checklist.md"
  timestamp: string;
};

type PmReviewCompletedEvent = {
  type: "pm_review_completed";
  repo: string;
  pr_number: number;
  passed: boolean;
  failed_checks: string[];
  timestamp: string;
};

type ApprovalPendingEvent = {
  type: "approval_pending";
  session_id: string;
  artifact_name: string;
  agent: string;
  timestamp: string;
};
```

`status_update` is broadcast to all clients viewing a session whenever the orchestrator processes a new status message. `artifact_updated` is emitted by the file watcher when an artifact file in `sessions/<id>/artifacts/` changes. `pm_review_completed` fires when a PM PR review finishes. `approval_pending` fires when an artifact with `approval_gate: true` is awaiting human approval.

### Polling intervals for non-filesystem sources

| Source | Interval | Mechanism |
|--------|----------|-----------|
| Filesystem | Instant | watchdog |
| Messages | Instant | broadcast on POST /api/messages |
| Docker containers | 5s | `docker ps` + `docker stats` |
| GitHub PRs/checks | 30s | `gh pr list` + `gh pr checks` |

---

## 5. Routing

### URL structure

```
/                                                   → redirect to /p/:id or /projects
/projects                                           → project list
/p/:projectId                                       → redirect to /p/:id/board
/p/:projectId/board                                 → kanban board
/p/:projectId/graph                                 → concept graph
/p/:projectId/graph?focus=:nodeId                   → graph focused on node
/p/:projectId/issues/:key                           → issue detail
/p/:projectId/nodes/:nodeId                         → node detail
/p/:projectId/agents                                → agent monitor
/p/:projectId/agents/:sessionId                     → session detail
/p/:projectId/messages                              → message inbox
/p/:projectId/messages/:sessionId                   → message thread
/p/:projectId/approvals                             → approval queue
/p/:projectId/pm-reviews                            → PM PR review dashboard
/p/:projectId/sessions/:sid/artifacts/:name         → single-artifact viewer
/p/:projectId/orchestration                         → view active orchestration pattern (read-only)
```

### React Router

```typescript
const router = createBrowserRouter([
  { path: "/", element: <RootRedirect /> },
  { path: "/projects", element: <ProjectList /> },
  {
    path: "/p/:projectId",
    element: <ProjectShell />,
    children: [
      { index: true, element: <Navigate to="board" replace /> },
      { path: "board", element: <KanbanBoard /> },
      { path: "graph", element: <ConceptGraph /> },
      { path: "issues/:key", element: <IssueDetail /> },
      { path: "nodes/:nodeId", element: <NodeDetail /> },
      { path: "agents", element: <AgentMonitor /> },
      { path: "agents/:sessionId", element: <SessionDetail /> },
      { path: "messages", element: <MessageInbox /> },
      { path: "messages/:sessionId", element: <MessageThread /> },
      { path: "approvals", element: <ApprovalQueue /> },
      { path: "pm-reviews", element: <PmReviewList /> },
      { path: "pm-reviews/:prNumber", element: <PmReviewDetail /> },
      { path: "sessions/:sid/artifacts/:name", element: <ArtifactViewer /> },
      { path: "orchestration", element: <OrchestrationView /> },
    ],
  },
]);
```

### ProjectShell layout

```
┌──────────────────────────────────────────────────────┐
│  [Project ▾]         Board | Graph | Agents | ✉ (3)  │  top nav
├────────┬─────────────────────────────────────────────┤
│        │                                             │
│ Sidebar│              Main Content                   │
│        │           (route-dependent)                 │
│ Issues │                                             │
│ Nodes  │                                             │
│ Quick  │                                             │
│ actions│                                             │
│        │                                             │
├────────┴─────────────────────────────────────────────┤
│  [2 running · 1 waiting · ✉ 3 blocking messages]    │  agent status bar
└──────────────────────────────────────────────────────┘
```

Sidebar and agent status bar always visible — never lose awareness of agent activity.

### Navigation patterns

- Issue key click (anywhere) → `/p/:id/issues/:key`
- `[[node-id]]` click (in Markdown) → `/p/:id/nodes/:nodeId`
- Session click → `/p/:id/agents/:sessionId`
- Message notification click → `/p/:id/messages/:sessionId`
- Kanban card click → `/p/:id/issues/:key`
- Graph node click → slide-over panel, "Open full" link

---

## 6. API Endpoints (Complete)

### Projects
```
GET  /api/projects                         → [{id, name, prefix, dir, issue_count}]
GET  /api/projects/:id                     → project.yaml parsed
```

### Issues
```
GET  /api/projects/:id/issues              → list (?status, ?executor, ?label, ?parent)
GET  /api/projects/:id/issues/:key         → full issue (frontmatter + rendered body + refs)
PATCH /api/projects/:id/issues/:key        → update fields (status, priority, labels)
POST /api/projects/:id/issues/:key/validate → ValidationResult
POST /api/projects/:id/validate            → validate all
```

### Concept graph
```
GET  /api/projects/:id/nodes               → list (?type, ?status, ?stale)
GET  /api/projects/:id/nodes/:nodeId       → full node + freshness
POST /api/projects/:id/nodes/check         → check all freshness
GET  /api/projects/:id/graph/deps          → issue dep graph (React Flow format)
GET  /api/projects/:id/graph/concept       → full concept graph (React Flow format)
GET  /api/projects/:id/refs/reverse/:nodeId → issues referencing this node
```

### Sessions & agents
```
GET  /api/projects/:id/sessions            → list (?status)
GET  /api/projects/:id/sessions/:sid       → detail + runtime_state + engagements
POST /api/projects/:id/sessions/:sid/re-engage → {trigger, context}
GET  /api/projects/:id/agents              → list agent definitions
GET  /api/projects/:id/agents/:aid         → agent definition
```

### Containers
```
GET  /api/containers                       → running containers [{id, session_id, status, stats}]
GET  /api/containers/:id/stats             → resource usage
GET  /api/containers/:id/logs?tail=50      → logs
POST /api/containers/launch                → {session_id, project_id}
POST /api/containers/:id/stop
POST /api/containers/:id/terminal          → open a terminal tab via the configured terminal launcher
POST /api/containers/cleanup               → remove stopped
```

The backend uses the terminal launcher configured in `~/.tripwire-containers/config.yaml` (`iterm`, `terminal`, `ghostty`, `alacritty`, `kitty`, `wezterm`, `tmux`, `none`, or a fully custom command). Because this is a localhost dev tool, the launcher runs on the same machine as the user.

### Messages
```
POST /api/messages                         → from agent: {session_id, type, priority, body} → {id}
GET  /api/messages?session_id=X            → list for session
GET  /api/messages/pending?session_id=X    → pending responses (for agent check_messages)
POST /api/messages/:id/respond             → {body, decision?}
GET  /api/messages/unread                  → blocking unread count
```

### GitHub
```
GET  /api/github/prs?repo=X               → list PRs (&head=branch)
GET  /api/github/prs/:n/checks?repo=X     → CI results
GET  /api/github/prs/:n/reviews?repo=X    → reviews
```

### Artifacts
```
GET  /api/projects/:id/sessions/:sid/artifacts                     → list artifacts for a session (from manifest + actual files)
GET  /api/projects/:id/sessions/:sid/artifacts/:name               → get one artifact's rendered content
POST /api/projects/:id/sessions/:sid/artifacts/:name/approve       → approve a gated artifact
POST /api/projects/:id/sessions/:sid/artifacts/:name/reject        → reject with feedback
GET  /api/projects/:id/artifact-manifest                           → return the active artifact manifest from `templates/artifacts/manifest.yaml`
```

### PM Reviews
```
GET  /api/projects/:id/pm-reviews                  → list pending PM PR reviews of project-repo PRs
GET  /api/projects/:id/pm-reviews/:pr-number       → full check results for one PM review
POST /api/projects/:id/pm-reviews/:pr-number/run   → manually trigger PM review
```

### Orchestration & Enums
```
GET  /api/projects/:id/orchestration/pattern       → return active orchestration pattern (resolved with overrides)
GET  /api/projects/:id/enums/:name                 → return an enum (for UI label/color rendering)
```

### Actions
```
POST /api/actions/merge-pr                 → {repo, pr_number}
POST /api/actions/close-pr                 → {repo, pr_number}
POST /api/actions/delete-branch            → {repo, branch}
POST /api/actions/rebuild-index            → {project_id}
POST /api/actions/finalize-session         → {project_id, session_id}
```

### WebSocket
```
WS   /api/ws?project=:projectId            → all real-time events
```

---

## 7. Frontend Data Layer

### Query key conventions

```typescript
const queryKeys = {
  project: (id: string) => ["project", id],
  issues: (pid: string) => ["issues", pid],
  issue: (pid: string, key: string) => ["issues", pid, key],
  nodes: (pid: string) => ["nodes", pid],
  node: (pid: string, nid: string) => ["nodes", pid, nid],
  graph: (pid: string, type: "deps" | "concept") => ["graph", pid, type],
  sessions: (pid: string) => ["sessions", pid],
  session: (pid: string, sid: string) => ["sessions", pid, sid],
  containers: () => ["containers"],
  messages: (sid: string) => ["messages", sid],
  unreadCount: () => ["messages", "unread"],
  prs: (repo: string) => ["github", "prs", repo],
};
```

### Stale times

```typescript
// Default: 30s (file watcher handles real-time)
// Containers: 5s (polled frequently)
// GitHub: 60s (rate limit awareness)
// Messages: 0 (always fresh, WebSocket driven)
```

---

## 8. Feedback & Re-engagement UI

### Agent Monitor — session card

Each session card shows a status state badge driven by `session.current_state` (set by the orchestrator from the latest status message):

```
┌──────────────────────────────────────┐
│ api-endpoints-core · backend-coder        │
│ [implementing] Wired JWT middleware. │
│ Now writing unit tests.              │
│ ─────────────────────────────────    │
│ SEI-40 · SEI-42  ·  re-engaged 2x    │
└──────────────────────────────────────┘
```

- The state badge color comes from the active `agent_state` enum (loaded from the project's `enums/agent_state.yaml`).
- Updates in real-time when a new status message arrives via WebSocket (`status_update` event).
- The summary text (1-2 sentences) is shown below the state badge.

The session card now also shows MULTIPLE PRs (one per repo in the `repos:` array) — single-repo display is gone. Each PR has its own status badge (CI status, review state, etc.).

A small **task checklist progress bar** is rendered on the session card:
- Parses `task-checklist.md` for the table rows.
- Counts `done` rows / total rows.
- Shows as a small progress bar on the session card.
- Live updates via WebSocket when the file changes (file watcher detects change and emits `artifact_updated`).

### Agent Monitor — engagement history

Per-session engagement history:
- **Engagement timeline**: Chronological list of container starts — timestamp, trigger badge, context summary, duration, outcome
- **Re-engagement count badge**: 0=green, 1-2=yellow, 3+=red (struggling)
- **Current trigger**: Shown prominently when re-engaged: "Re-engaged: CI failure — ruff E302"

### Feedback timeline (per issue)

Aggregated timeline across all sources:
```
14:00  Agent launched (backend-coder)
15:30  PR #42 opened
15:35  CI failed: ruff E302
15:36  Agent re-engaged (ci_failure)
15:40  Fix pushed
15:42  CI passed
15:43  Verifier launched
16:00  Verifier rejected: AC#3 not met
16:01  Agent re-engaged (verifier_rejection)
16:15  Fix pushed, CI passed, Verifier approved
16:21  Waiting for human review...
```

Sources: session engagements, PR comments/reviews (GitHub), CI checks (GitHub), issue comments (project repo), container status.

### Manual re-engage

Button on Agent Monitor + Issue Detail (when session in waiting state):
- Trigger type dropdown
- Context text area (pre-populated from latest feedback)
- Launch → `POST /api/projects/:id/sessions/:sid/re-engage`

### Session status indicators

| Status | Color |
|--------|-------|
| `planned` | Gray |
| `active` | Blue |
| `waiting_for_ci` | Yellow |
| `waiting_for_review` | Yellow |
| `waiting_for_deploy` | Yellow |
| `re_engaged` | Orange |
| `completed` | Green |
| `failed` | Red |

### Session detail — Repos section

The session detail view has a "Repos" section listing all repos from the session's `repos:` array, with their branches and PR numbers. Each repo entry shows its own CI status, review state, and links to the PR on GitHub.

---

## Session Artifacts UI

Session detail has a tab/section per artifact in the manifest. The list is **not** a hardcoded set — it is read from the project's `templates/artifacts/manifest.yaml` (fetched via `GET /api/projects/:id/artifact-manifest`). The order of tabs comes from the manifest order.

- Each artifact rendered as Markdown (using `react-markdown` + `remark-gfm`).
- The 5 default artifacts: `plan.md`, `task-checklist.md`, `verification-checklist.md`, `recommended-testing-plan.md`, `post-completion-comments.md`.
- `task-checklist.md` is parsed for the progress bar (count of `done` rows / total rows).
- The `verification-checklist` progress (count of checked items / total) is shown in completion review.
- All artifacts support `[[node-references]]` rendering as clickable links.
- File watcher emits `artifact_updated` events; the UI invalidates the affected artifact query and re-renders.

### Approval queue

A dedicated **Approval Queue** view (`/p/:projectId/approvals`) lists all pending approval-gated artifacts (any artifact with `approval_gate: true` in the manifest).

Each entry shows:
- Session
- Artifact name
- Agent
- Time waiting
- Rendered Markdown content
- Approve / Reject buttons with optional feedback text

Approve → calls `POST /api/projects/:id/sessions/:sid/artifacts/:name/approve` → orchestrator triggers re-engagement with `plan_approved` trigger.

Reject → calls `POST /api/projects/:id/sessions/:sid/artifacts/:name/reject` → orchestrator triggers `plan_rejected` re-engagement with the feedback as context.

A notification badge appears on the nav for pending approvals.

---

## PM Reviews

A new "PM Reviews" view (`/p/:projectId/pm-reviews`) shows pending PM PR reviews — PRs to the project repo that the PM agent is reviewing. It can also be embedded in the Agent Monitor.

For each PR:
- Title, author, link to GitHub
- The 10 check results (pass/fail), expandable for details
- Approve / Merge buttons (if the user has permission), or a "Re-engage agent with fixes" button
- Failed checks include the `fix_hint` from `CheckResult`

A user can manually trigger a review via `POST /api/projects/:id/pm-reviews/:pr-number/run`.

---

## 9. Agent Messaging UI

### Message inbox

- Grouped by session
- Notification badge on nav: red for blocking, gray for informational
- Each message: agent name, type badge, timestamp, preview
- Click → message thread

### Message thread

- Chat interface: agent left, human right
- Markdown rendering (react-markdown + remark-gfm)
- `[[references]]` rendered as clickable links → `/p/:id/nodes/:nodeId`
- Plan approval: Markdown render + Approve (green) / Reject (red) buttons
- Response input at bottom

### Desktop notifications (browser Notification API)

- Blocking messages only: "backend-coder needs your input: ..."
- Click → opens thread in UI

### Message storage

- SQLite at `~/.tripwire/messages.db` (hot store)
- On session complete: finalize to `sessions/<id>/messages.yaml` in project repo (permanent audit trail)

---

## 10. Package Structure

The UI lives within the tripwire monorepo. The Python backend is at
`src/keel/ui/`. The React frontend source is at `src/keel/ui/frontend/`
and builds to `src/keel/ui/static/` (git-ignored).

```
src/keel/ui/
├── __init__.py
├── server.py                          # FastAPI app, lifespan, static serving
├── config.py                          # Load ~/.tripwire/config.yaml
├── dependencies.py                    # FastAPI Depends() — project context
│
├── routes/                            # one file per resource
│   ├── projects.py
│   ├── issues.py
│   ├── nodes.py
│   ├── graph.py
│   ├── sessions.py
│   ├── artifacts.py
│   ├── enums.py
│   ├── orchestration.py
│   ├── actions.py
│   └── ws.py                          # WebSocket
│
├── services/                          # one file per data source
│   ├── project_service.py             # uses keel.core.store
│   ├── issue_service.py               # uses keel.core.store
│   ├── node_service.py                # uses keel.core.node_store
│   ├── graph_service.py               # uses keel.core.concept_graph
│   ├── session_service.py
│   ├── file_watcher.py                # watchdog → event queue
│   └── action_service.py
│
├── ws/
│   ├── hub.py                         # WebSocket connection manager
│   └── events.py                      # event type definitions
│
├── static/                            # git-ignored, built from frontend/
│
└── frontend/                          # React source
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── biome.json
    ├── src/
    │   ├── app/
    │   │   ├── App.tsx
    │   │   ├── routes.tsx
    │   │   └── ProjectShell.tsx
    │   ├── features/
    │   │   ├── projects/              # ProjectList, useProjects
    │   │   ├── kanban/                # KanbanBoard, KanbanColumn, IssueCard
    │   │   ├── graph/                 # ConceptGraph, IssueNode, ConceptNode
    │   │   ├── issues/                # IssueDetail, MarkdownBody
    │   │   ├── nodes/                 # NodeDetail
    │   │   ├── sessions/              # SessionList, SessionDetail
    │   │   ├── artifacts/             # ArtifactViewer, ArtifactList
    │   │   ├── agents/                # (v2) AgentMonitor, containers
    │   │   ├── messages/              # (v2) MessageInbox, MessageThread
    │   │   ├── pm-reviews/            # (v2) PmReviewList
    │   │   └── actions/               # ActionsPanel
    │   ├── components/ui/             # shadcn/ui
    │   ├── hooks/
    │   │   └── useProjectWebSocket.ts
    │   ├── lib/api/
    │   │   ├── client.ts
    │   │   └── queryKeys.ts
    │   └── types/
    │       ├── issue.ts
    │       ├── node.ts
    │       ├── session.ts
    │       └── events.ts
    │
    └── tests/                         # Vitest + RTL

tests/
└── ui/                                # pytest tests for keel.ui backend
```
