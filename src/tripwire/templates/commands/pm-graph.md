---
name: pm-graph
description: Analyse the dependency or concept graph for critical path and cycles.
argument-hint: "[deps|concept]"
---

You are the project manager for this repository. Load the project-manager
skill if not active.

Graph type (defaults to deps if omitted):
$ARGUMENTS

1. Run `tripwire graph --type deps` (or `--type concept`
   if the user asked for the concept graph).
2. Parse the JSON output.
3. Analyse the structure:
   - **Connected components** — how many independent subgraphs exist?
     Can any of them run in parallel by different agents?
   - **The critical path** — which chain of issues has the longest
     dependency chain? What's at the front of it?
   - **Parallelizable work** — which issues have no pending dependencies
     and could start right now?
   - **Cycles** — any unexpected cycles in the dependency graph? If so,
     they're a bug — report them clearly.
   - **Orphan nodes** — concept nodes with no incoming references (may
     be dead) or issues with no connections (may be missing context).
4. Summarize for the user. Lead with the thing they most likely care
   about: what can be worked on right now and what's blocked.

Reference specific issue keys and node IDs. Use short bullets, not prose.
