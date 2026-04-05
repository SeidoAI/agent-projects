# Agent Projects UI — Detailed Plan

## Context

Command-and-control centre for the agent development platform. Local development tool (localhost only). See `overarching-plan.md` for how it connects to agent-project (data) and agent-containers (execution).

**Tech stack**: React 19, TypeScript 5.8, Vite 7, Tailwind CSS v4, shadcn/ui, React Flow (XyFlow), TanStack Query v5, Biome, Vitest.

---

## 1. Startup Experience

### For new users — zero config

```bash
pip install agent-projects-ui       # installs backend + bundled frontend
agent-projects-ui                   # starts everything, opens browser
```

What happens:
1. FastAPI backend starts on `localhost:8000`
2. Pre-built frontend static files served by backend at `localhost:8000`
3. Browser opens automatically
4. Auto-discovers projects — scans for `project.yaml` in:
   - Current directory
   - `~/.agent-projects/config.yaml` configured roots (if file exists)
   - Common locations: `~/Code/**/project.yaml` (shallow, max 2 levels)
5. One project found → go straight to it
6. Multiple → project switcher
7. None → "No projects found" with instructions to run `agent-project init`

### Configuration (optional)

```yaml
# ~/.agent-projects/config.yaml
project_roots:
  - ~/Code/seido/projects
  - ~/Code/other-org/projects
default_project: ~/Code/seido/projects/seido-mvp
port: 8000
open_browser: true
```

### CLI

```
agent-projects-ui
  --project-dir TEXT    Open directly to this project [default: auto-discover]
  --port INT            Port [default: 8000]
  --no-browser          Don't auto-open browser
  --dev                 Dev mode: Vite on :3000 proxying to backend on :8000
```

### For UI developers

```bash
cd agent-projects-ui
npm install && npm run dev        # Vite :3000, proxies /api → :8000
# Separate terminal:
cd backend && uv run uvicorn agent_projects_api.main:app --reload --port 8000
```

### Packaging

The pip package bundles pre-built frontend statics. Backend serves them directly — no Node.js process needed in production mode.

```python
# main.py
if not dev_mode:
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True))
```

---

## 2. Backend Architecture

### Stack

- **FastAPI** (async, WebSocket built-in)
- **agent_project** imported as Python library (not subprocess)
- **Docker CLI** via subprocess for container management
- **`gh` CLI** via subprocess for GitHub API
- **SQLite** for message storage (`~/.agent-projects/messages.db`)
- **watchdog** for filesystem monitoring
- **uvicorn** as ASGI server

### Service layer

```
backend/src/agent_projects_api/
├── main.py                    # FastAPI app, lifespan, static file serving
├── config.py                  # Load ~/.agent-projects/config.yaml
├── dependencies.py            # FastAPI Depends() — project context, services
│
├── routes/
│   ├── projects.py            # GET /api/projects[/:id]
│   ├── issues.py              # GET/PATCH /api/projects/:id/issues[/:key], validate
│   ├── nodes.py               # GET /api/projects/:id/nodes[/:nodeId], check freshness
│   ├── graph.py               # GET /api/projects/:id/graph/{deps,concept}
│   ├── sessions.py            # GET /api/projects/:id/sessions[/:sid], re-engage
│   ├── agents.py              # GET /api/projects/:id/agents[/:aid]
│   ├── containers.py          # GET/POST /api/containers — launch, stop, stats, logs
│   ├── messages.py            # POST/GET /api/messages — agent messaging
│   ├── github.py              # GET /api/github/prs, checks, reviews
│   ├── actions.py             # POST /api/actions/{action}
│   └── ws.py                  # WebSocket /api/ws
│
├── services/
│   ├── project_service.py     # Discover + load projects via agent_project lib
│   ├── issue_service.py       # CRUD via agent_project.core.store
│   ├── node_service.py        # CRUD via agent_project.core.node_store
│   ├── graph_service.py       # Build graphs via agent_project.core.concept_graph
│   ├── session_service.py     # Read sessions, trigger re-engagement
│   ├── container_service.py   # Docker CLI wrapper: ps, stats, logs, start, stop
│   ├── github_service.py      # gh CLI wrapper: PRs, checks, reviews, merge, close
│   ├── message_service.py     # SQLite CRUD for messages
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

**IssueService** — imports `agent_project.core.store` directly:
- `list(filters)` → `list_issues(project_dir, filters)`
- `get(key)` → `load_issue(project_dir, key)`
- `update_status(key, status)` → load, mutate, `save_issue()`
- `validate(key?)` → `validate_issue(project_dir, key)`
- `get_references(key)` → `extract_references(issue.body)`

**ContainerService** — Docker CLI via subprocess:
- `list_running()` → `docker ps --filter label=agent-projects --format json`
- `get_stats(id)` → `docker stats <id> --no-stream --format json`
- `get_logs(id, tail)` → `docker logs <id> --tail N`
- `stop(id)` → `docker stop <id>`
- `launch(session_id, project_dir)` → delegates to `agent-containers launch`

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
```

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
/                                      → redirect to /p/:id or /projects
/projects                              → project list
/p/:projectId                          → redirect to /p/:id/board
/p/:projectId/board                    → kanban board
/p/:projectId/graph                    → concept graph
/p/:projectId/graph?focus=:nodeId      → graph focused on node
/p/:projectId/issues/:key              → issue detail
/p/:projectId/nodes/:nodeId            → node detail
/p/:projectId/agents                   → agent monitor
/p/:projectId/agents/:sessionId        → session detail
/p/:projectId/messages                 → message inbox
/p/:projectId/messages/:sessionId      → message thread
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
GET  /api/projects/:id/sessions            → list (?status, ?wave)
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
POST /api/containers/launch                → {session_id, project_id, iterm?}
POST /api/containers/:id/stop
POST /api/containers/:id/iterm             → open iTerm2 tab
POST /api/containers/cleanup               → remove stopped
```

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

### Agent Monitor — engagement history

Per-session engagement history:
- **Engagement timeline**: Chronological list of container starts — timestamp, trigger badge, context summary, duration, outcome
- **Re-engagement count badge**: 0=green, 1-2=yellow, 3+=red (struggling)
- **Current trigger**: Shown prominently when re-engaged: "Re-engaged: CI failure — ruff E302"

### Feedback timeline (per issue)

Aggregated timeline across all sources:
```
14:00  Agent launched (backend-coder, wave 1)
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

- SQLite at `~/.agent-projects/messages.db` (hot store)
- On session complete: finalize to `sessions/<id>/messages.yaml` in project repo (permanent audit trail)

---

## 10. Package Structure

```
agent-projects-ui/
├── package.json
├── vite.config.ts
├── tsconfig.json
├── biome.json
├── src/
│   ├── app/
│   │   ├── App.tsx
│   │   ├── routes.tsx
│   │   └── ProjectShell.tsx           # layout: sidebar + main + status bar
│   ├── features/
│   │   ├── projects/
│   │   │   ├── ProjectList.tsx
│   │   │   └── hooks/useProjects.ts
│   │   ├── kanban/
│   │   │   ├── KanbanBoard.tsx
│   │   │   ├── KanbanColumn.tsx
│   │   │   ├── IssueCard.tsx
│   │   │   └── hooks/useKanban.ts
│   │   ├── graph/
│   │   │   ├── ConceptGraph.tsx
│   │   │   ├── IssueNode.tsx          # React Flow custom node
│   │   │   ├── ConceptNode.tsx        # React Flow custom node
│   │   │   └── hooks/useGraphData.ts
│   │   ├── issues/
│   │   │   ├── IssueDetail.tsx
│   │   │   ├── IssueTimeline.tsx
│   │   │   ├── MarkdownBody.tsx       # renders [[refs]] as links
│   │   │   └── hooks/useIssue.ts
│   │   ├── nodes/
│   │   │   ├── NodeDetail.tsx
│   │   │   └── hooks/useNode.ts
│   │   ├── agents/
│   │   │   ├── AgentMonitor.tsx
│   │   │   ├── SessionDetail.tsx
│   │   │   ├── EngagementTimeline.tsx
│   │   │   ├── ReEngageDialog.tsx
│   │   │   ├── SessionStatusBadge.tsx
│   │   │   └── hooks/
│   │   │       ├── useSessions.ts
│   │   │       └── useContainerStatus.ts
│   │   ├── messages/
│   │   │   ├── MessageInbox.tsx
│   │   │   ├── MessageThread.tsx
│   │   │   ├── PlanApprovalCard.tsx
│   │   │   ├── MessageBadge.tsx
│   │   │   └── hooks/
│   │   │       ├── useMessages.ts
│   │   │       └── useDesktopNotification.ts
│   │   └── actions/
│   │       ├── ActionsPanel.tsx
│   │       └── hooks/useActions.ts
│   ├── components/
│   │   └── ui/                        # shadcn/ui
│   ├── hooks/
│   │   └── useProjectWebSocket.ts     # WebSocket + cache invalidation
│   ├── lib/
│   │   └── api/
│   │       ├── client.ts              # fetch wrapper
│   │       └── queryKeys.ts
│   └── types/
│       ├── issue.ts
│       ├── node.ts
│       ├── session.ts
│       ├── container.ts
│       ├── message.ts
│       └── events.ts
│
├── backend/
│   ├── pyproject.toml                 # depends on agent-project, fastapi, watchdog, uvicorn
│   └── src/agent_projects_api/
│       ├── main.py
│       ├── config.py
│       ├── dependencies.py
│       ├── routes/                    # one file per resource
│       ├── services/                  # one file per data source
│       └── ws/                        # hub + events
│
└── tests/
    ├── frontend/                      # Vitest + RTL
    └── backend/                       # pytest
```
