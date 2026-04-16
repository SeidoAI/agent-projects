// Endpoint-specific typed wrappers live here as per-resource modules.
//
// Pattern:
//   endpoints/issues.ts   — issuesApi.list(), issuesApi.get(), ...
//   endpoints/nodes.ts    — nodesApi.list(), nodesApi.get(), ...
//   endpoints/sessions.ts — sessionsApi.list(), ...
//
// Each module imports apiGet/apiPost/apiPatch/apiDelete from "../client"
// and the relevant TypeScript types. Feature issues add their endpoint
// modules alongside their views.
