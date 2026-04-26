/**
 * Default MSW handlers for every backend route the frontend uses.
 *
 * These return minimal-but-valid fixtures so tests that don't seed
 * the QueryClient (or that exercise a fresh-mount path) get a
 * deterministic 200 instead of an unhandled-request error. Tests
 * needing a different shape — empty list, 404, 409, etc. — call
 * `server.use(http.get(...))` to override per-test.
 *
 * Pattern: keep handlers narrow on path, broad on response. If a
 * route accepts query filters (`?status=active`), the default
 * handler ignores them — tests asserting filter forwarding should
 * inspect `request.url` inside an override.
 */
import { HttpResponse, http } from "msw";

import {
  makeArtifactManifest,
  makeArtifactStatuses,
  makeEmptyGraph,
  makeIssueDetail,
  makeIssueStatusEnum,
  makeNodeDetail,
  makeProject,
  makeReverseRefs,
  makeSessionDetail,
} from "./fixtures";

export const defaultHandlers = [
  // Projects
  http.get("/api/projects", () => HttpResponse.json([makeProject()])),
  http.get("/api/projects/:pid", ({ params }) =>
    HttpResponse.json(makeProject({ id: String(params.pid) })),
  ),

  // Issues
  http.get("/api/projects/:pid/issues", () => HttpResponse.json([])),
  http.get("/api/projects/:pid/issues/:key", ({ params }) =>
    HttpResponse.json(makeIssueDetail({ id: String(params.key) })),
  ),
  http.patch("/api/projects/:pid/issues/:key", async ({ request, params }) => {
    const body = (await request.json()) as Partial<ReturnType<typeof makeIssueDetail>>;
    return HttpResponse.json(makeIssueDetail({ id: String(params.key), ...body }));
  }),
  http.post("/api/projects/:pid/issues/:key/validate", () =>
    HttpResponse.json({
      version: 1,
      exit_code: 0,
      summary: { errors: 0, warnings: 0, fixed: 0 },
      categories: {},
      errors: [],
      warnings: [],
      fixed: [],
    }),
  ),

  // Sessions
  http.get("/api/projects/:pid/sessions", () => HttpResponse.json([])),
  http.get("/api/projects/:pid/sessions/:sid", ({ params }) =>
    HttpResponse.json(makeSessionDetail({ id: String(params.sid) })),
  ),

  // Nodes
  http.get("/api/projects/:pid/nodes", () => HttpResponse.json([])),
  http.get("/api/projects/:pid/nodes/:nid", ({ params }) =>
    HttpResponse.json(makeNodeDetail({ id: String(params.nid) })),
  ),
  http.get("/api/projects/:pid/refs/reverse/:nid", ({ params }) =>
    HttpResponse.json(makeReverseRefs({ node_id: String(params.nid) })),
  ),

  // Graph
  http.get("/api/projects/:pid/graph/concept", () => HttpResponse.json(makeEmptyGraph())),

  // Enums
  http.get("/api/projects/:pid/enums/:name", ({ params }) => {
    if (params.name === "issue_status") return HttpResponse.json(makeIssueStatusEnum());
    return HttpResponse.json({ name: String(params.name), values: [] });
  }),

  // Strand Y (v0.8) — workflow + events. The endpoints are still in
  // flight; default handlers return empty payloads so consumers like
  // the Dashboard's "Recent Activity" feed render their empty state.
  // Tests asserting populated states `setQueryData` directly.
  http.get("/api/projects/:pid/workflow", () => HttpResponse.json({ events: [], next_cursor: null })),
  http.get("/api/projects/:pid/events", () => HttpResponse.json({ events: [], next_cursor: null })),

  // Artifacts
  http.get("/api/projects/:pid/artifact-manifest", () =>
    HttpResponse.json(makeArtifactManifest()),
  ),
  http.get("/api/projects/:pid/sessions/:sid/artifacts", () =>
    HttpResponse.json(makeArtifactStatuses()),
  ),
  http.get("/api/projects/:pid/sessions/:sid/artifacts/:name", ({ params }) =>
    HttpResponse.json({
      name: String(params.name),
      file_path: `${String(params.name)}.md`,
      body: "",
      mtime: "2026-04-24T00:00:00Z",
    }),
  ),
  http.post("/api/projects/:pid/sessions/:sid/artifacts/:name/approve", () =>
    HttpResponse.json({}, { status: 200 }),
  ),
  http.post("/api/projects/:pid/sessions/:sid/artifacts/:name/reject", () =>
    HttpResponse.json({}, { status: 200 }),
  ),
];
