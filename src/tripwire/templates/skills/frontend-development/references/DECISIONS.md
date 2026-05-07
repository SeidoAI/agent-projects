# Locked Decisions

In tripwire, locked architectural decisions are tracked as
`[[decision]]` nodes under `<project>/nodes/`. If an issue body
references a `[[decision]]` node, that node is authoritative — read
it before designing. Decision nodes outrank any conflicting
in-issue assumption.

## Reading decisions

```bash
ls <project>/nodes/decision-*.yaml
```

A decision node typically carries:

- `id` — the slug used in `[[references]]`.
- `kind: decision`.
- `title` — a short label.
- `body` — the rationale and the locked outcome.
- `source` — pointer to the canonical source (if any) and a
  content hash so changes are detectable.

If you find conflict between a decision node and your plan, **stop
and send a `question` message**. Do not work around a locked
decision.

## Starter checklist of frontend decisions to lock

When scoping a new frontend project, the PM should create
`[[decision]]` nodes pinning at minimum:

- Build tool (Vite vs Next.js vs Remix).
- Framework version (React 18 vs 19, Next.js App Router vs Pages
  Router).
- TypeScript config posture (strict mode flags).
- Routing library.
- Server-state library (TanStack Query, SWR, custom).
- Client-state library (Context, Zustand, Redux Toolkit).
- Styling system (Tailwind v4, CSS modules, styled-components).
- Component library (shadcn/ui, MUI, Mantine, in-house).
- Forms library (React Hook Form, Formik, native).
- Auth provider (Firebase, Auth0, Clerk, custom).
- Test framework (Vitest, Jest).
- Lint/format toolchain (Biome, ESLint + Prettier).
- Node.js minimum version.

Anything not pinned is an open architectural decision. Issues that
hit an open decision must surface it via a `question` message
rather than picking a default.

## Common technology locks (illustrative)

The following are typical choices for a modern React SPA. These are
**not** mandates — only the locks recorded in `<project>/nodes/`
are authoritative for any given project.

- React 18+ with functional components and hooks (no class
  components).
- TypeScript 5+ with strict mode enabled (`strict: true`).
- Vite for SPAs, Next.js for SSR/RSC apps.
- Tailwind CSS v4 with CSS-first `@theme` config.
- shadcn/ui for primitives (built on Radix UI + CVA).
- TanStack Query v5 for server state.
- React Router v7 for SPA routing (or Next.js routing for Next).
- Vitest + React Testing Library for testing.
- Biome for lint+format (single tool, replacing ESLint + Prettier).
- Node.js 20 LTS minimum.
