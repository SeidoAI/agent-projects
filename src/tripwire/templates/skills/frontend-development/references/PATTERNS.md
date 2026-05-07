# Patterns & Conventions

Generic patterns for a TypeScript/React frontend. Read the target
repo first — these are sensible defaults, not mandates. If the repo
already follows a different convention, match it.

## Component organization

Organise by feature, not by type:

```
src/components/
├── auth/             # authentication (ProtectedRoute, login forms)
├── <feature-a>/      # feature A — components, sub-components, tests
├── <feature-b>/      # feature B
├── common/           # cross-cutting (DevModeToggle, loading states)
├── layout/           # DashboardLayout, Header, navigation
└── ui/               # design-system primitives (button, card, dialog)
```

### Guidelines

- **One component per file** — file name matches component name in
  PascalCase.
- **Feature components** go in their feature directory.
- **Page components** go in `src/pages/` (SPA) or `app/` (Next.js
  App Router) and are route targets.
- **Design-system components** (e.g. shadcn/ui) go in
  `src/components/ui/` — install via the system's CLI rather than
  hand-rolling primitives.
- **Shared hooks** go in `src/hooks/` — prefix with `use`.
- **Contexts** go in `src/contexts/` — suffix with `Context`.

## Styling approach

Match what the repo has wired up. Common stacks:

### Tailwind CSS v4 + CSS variables

Tailwind v4 uses CSS-first configuration — no `tailwind.config.ts`
needed for most cases. Brand palette is declared via `@theme`
directives in the entry CSS:

```css
@import "tailwindcss";

@theme {
  --color-brand-primary: #...;
  --color-brand-surface: #...;
}
```

Vite plugin: `@tailwindcss/vite` (first-party).

### shadcn/ui

- Configured via `components.json` (style, baseColor, CSS-variable
  mode).
- Uses unified `radix-ui` package and class-variance-authority (CVA)
  for component variants.
- Install new components: `npx shadcn@latest add <component>`.
- Components land in `src/components/ui/`.

### CSS modules / styled-components

If the repo uses CSS modules (`.module.css`) or styled-components,
match the existing pattern. Don't introduce a second styling system
— that's an architectural decision the issue must call out
explicitly.

## API client pattern

### Token management

1. The auth context provides an access/ID token.
2. The API client injects `Authorization: Bearer <token>` on every
   request.
3. On `401`: refresh the token via the auth SDK → retry the request
   once.
4. On persistent `401`: redirect to login (or trigger the auth
   provider's re-auth flow).

### Error handling

Typed error responses from backend:

```typescript
interface ApiError {
  code: string;     // NETWORK_ERROR | AUTH_ERROR | SERVER_ERROR | VALIDATION_ERROR
  message: string;
  details?: object;
}
```

User-facing errors should surface via the design system's toast/
notification primitive (e.g. `sonner`, the shadcn/ui `Toaster`,
React Hot Toast) — not via blocking modals.

## Custom hooks pattern

Hooks encapsulate data fetching + mutation logic using the project's
server-state library (TanStack Query is the most common):

```typescript
export function useResources() {
  const query = useQuery({
    queryKey: ['resources'],
    queryFn: () => apiClient.get('/api/v1/resources'),
  });
  const create = useMutation({
    mutationFn: (input: NewResource) => apiClient.post('/api/v1/resources', input),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['resources'] }),
  });
  return { ...query, create };
}
```

### Naming convention

| Hook | Purpose |
|------|---------|
| `use<Noun>(...)` | Read query for the named resource |
| `use<Noun>List()` | List query when both list and detail exist |
| `use<Verb><Noun>()` | Mutation hook (e.g. `useUploadDocument`) |

## Dev mode pattern

Most projects benefit from a development-only auth bypass for local
testing without real credentials:

1. Set a flag (`localStorage.devMode = 'true'`) in the browser
   console.
2. A `DevAuthContext` (or equivalent) provides a mock user object.
3. The API client still sends requests but with a mock token; the
   backend dev environment accepts it.
4. Mock data lives under `src/utils/devData.ts` (or equivalent).

A toggle component lives in `src/components/common/`.

This is a project-specific pattern — only adopt it if the project
already has the dev-mode plumbing. Don't invent it on a whim.

## Graph / data visualisation

If the project renders graphs/networks, common library choices:

- **XyFlow (React Flow)** — for node/edge graphs with custom
  rendering. Pattern: a custom-node registry, a custom-edge
  registry, and a `useGraphData(id)` hook that fetches raw data
  and transforms it into XyFlow's `nodes`/`edges` shape.
- **D3 / Visx** — for bespoke charts that don't fit a prebuilt
  library.
- **Recharts / Tremor** — for standard chart types (line, bar,
  area, scatter).

Pick one and stick with it; don't mix charting libraries within a
project.

## Error boundaries & Suspense

### Layered error-boundary strategy

1. **Global `ErrorBoundary`** at the app root — catch-all with a
   "something went wrong" UI + retry button.
2. **Per-feature `FeatureErrorBoundary`** — wraps each major route
   or dashboard section so one component failure doesn't crash the
   entire app.
3. **Route-level `<Suspense>`** — skeleton/loading fallbacks for
   code-split routes via `React.lazy()`.

### TanStack Query Suspense mode

Use `useSuspenseQuery` within Suspense boundaries for data fetching:

```typescript
const { data } = useSuspenseQuery({
  queryKey: ['resource', id],
  queryFn: () => apiClient.get(`/api/v1/resource/${id}`),
});
```

The Suspense boundary shows the fallback until data loads, the
error boundary catches fetch failures.

## Accessibility baseline

All components must meet these minimum requirements:

- **Semantic HTML**: prefer `<button>`, `<nav>`, `<main>`,
  `<section>`, `<header>` over generic `<div>`.
- **ARIA attributes**: required on all interactive elements
  (buttons, links, form inputs, modals).
- **Keyboard navigation**: every interactive element reachable via
  Tab, operable via Enter / Space, with a visible focus indicator.
- **Colour contrast**: WCAG AA — 4.5:1 for normal text, 3:1 for
  large text.
- **Linter a11y rules**: enforce via Biome (`a11y` rules) or
  `eslint-plugin-jsx-a11y` — linting catches the common issues at
  development time.

## Testing strategy

### Framework: Vitest or Jest + React Testing Library

- **Vitest** — preferred for Vite projects (shares the build
  config, fast).
- **Jest** — common for Next.js or Create React App projects.
- **React Testing Library** — tests components as users interact
  with them (queries by role, text, label).
- **jsdom** — DOM simulation environment.

### Test file organisation

- **Co-location**: `ComponentName.test.tsx` lives next to the
  component file.
- **Hook tests**: `useHookName.test.tsx` in `src/hooks/`.
- **Utility tests**: `utilName.test.ts` in `src/utils/`.

### Test categories

| Category | Tools | Coverage target |
|----------|-------|----------------|
| Unit | Vitest / Jest | hooks, utilities, pure functions — 80% |
| Component | Vitest/Jest + RTL | render, user interactions, state changes — critical paths |
| Integration | Vitest/Jest + MSW | API mocking, data flow from hook to component |

### Setup

- Test setup file: `src/test/setup.ts` — imports
  `@testing-library/jest-dom` matchers.
- Coverage: `npm test -- --coverage` (Jest) or
  `npx vitest --coverage` (Vitest, v8 provider).

## Runtime configuration

### Pattern: `/config.json` loaded at startup

Build-time `VITE_*` / `NEXT_PUBLIC_*` env vars bake values into the
bundle, requiring a rebuild per environment. The runtime-config
pattern lets the same artefact deploy to test and prod with
different configs.

### How it works

1. `public/config.json` — shipped with the app, replaceable per
   environment.
2. `src/lib/config.ts` — fetches and parses the config at app
   startup.
3. `ConfigContext` — provides typed config to the component tree.
4. The app shows a loading state until config is loaded.

### Schema (illustrative)

```typescript
interface AppConfig {
  apiBaseUrl: string;
  features?: Record<string, boolean>;
  // ...project-specific keys
}
```

### Environment strategy

- **Build-time vars** (`VITE_*`, `NEXT_PUBLIC_*`): only true build-
  time values (e.g. `VITE_APP_VERSION`).
- **Runtime config**: everything else (API URLs, feature flags,
  third-party public keys).
- **Fallback**: in development, fall back to env vars if
  `/config.json` isn't customised.
