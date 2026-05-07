# Architecture

This is a generic reference for a typical TypeScript/React SPA. The
exact tech list is set per-project — read the target repo's
`package.json` and config files first, and only consult the sections
below that match what's actually in use.

## Tech stack (typical)

| Layer | Technology | Notes |
|-------|-----------|-------|
| Framework | React 18+ + TypeScript 5+ | Functional components with hooks; strict mode usually on |
| Build | Vite or Next.js | Vite preferred for SPAs; Next.js for SSR/RSC apps |
| Routing | React Router (SPA) or Next.js file-based routing | |
| Server state | TanStack Query | Caching, auto-refresh, Suspense mode via `useSuspenseQuery` |
| Client state | React Context (small) / Zustand or Jotai (medium) / Redux Toolkit (large) | Pick the smallest option that fits |
| Styling | Tailwind CSS / shadcn/ui / CSS modules / styled-components | Per the project's locked decision |
| Forms | React Hook Form + Zod | Schema validation, controlled inputs |
| Auth | Project-specific (Firebase Auth, Auth0, Clerk, custom JWT) | Read the existing auth context before designing |
| Testing | Vitest or Jest + React Testing Library | jsdom environment |
| Lint/Format | Biome (single tool) or ESLint + Prettier | Whatever's wired into the repo |

If the target repo uses something not listed here, follow what's
already wired up — do not introduce a new tool unless the issue
explicitly asks for one.

## Routing

For SPAs (Vite + React Router), top-level structure is usually:

```
/                  → public landing
/login             → auth entry
/<protected>/...   → wrapped in a `ProtectedRoute` / auth guard
*                  → 404 / NotFound
```

For Next.js apps, file-based routing under `app/` (App Router) or
`pages/` (Pages Router) is the canonical source of truth — read the
directory structure, don't infer.

All authenticated routes should be wrapped in a single auth-guard
component (or, for Next.js, a `middleware.ts` redirect).

## State management

### React Context providers

Wrap the app in providers in dependency order. A typical chain:

1. Server-state provider (e.g. `QueryClientProvider` for TanStack
   Query)
2. UI primitives (e.g. `TooltipProvider` for shadcn/ui)
3. Router (`BrowserRouter` for SPA, n/a for Next.js)
4. Auth provider (project-specific — Firebase, Auth0, etc.)
5. Feature-specific providers (config, theme, live connections, ...)

### Auth state

Read the existing auth context before adding to it. Typical surface:

- `user` — the current user object (or `null`)
- `idToken` / `accessToken` — bearer token for API calls
- Sign-in methods (e.g. `signInWithGoogle()`, `sendMagicLink(email)`)
- A development-only bypass (often gated by `localStorage.devMode`)

### Server state (TanStack Query)

Custom hooks encapsulate API calls. Naming convention: `use<Noun>`
for read, with mutations exposed as named methods on the returned
object. Example shape:

```typescript
export function useDocuments() {
  const query = useQuery({
    queryKey: ['documents'],
    queryFn: () => apiClient.get('/api/v1/documents'),
  });
  const upload = useMutation({
    mutationFn: (file: File) => apiClient.upload(file),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['documents'] }),
  });
  return { ...query, upload };
}
```

## API integration

### API client pattern

Singleton class (or module) that:

1. Pulls the auth token from the auth context
2. Injects `Authorization: Bearer <token>` on every request
3. On `401`: refreshes the token and retries once
4. Returns typed responses via generics
5. Translates non-2xx responses into a typed `ApiError` (see
   `references/PATTERNS.md` § Error handling)

### Endpoint catalogue

The set of consumed endpoints is project-specific — read the
target repo's `src/api/` (or equivalent) and the backend's OpenAPI
spec before adding a new call.

### Streaming (SSE / WebSockets)

If the backend exposes streaming endpoints (Server-Sent Events for
agent chat, WebSockets for collaborative state), use the standard
EventSource / WebSocket APIs and wrap them in a hook that yields
typed events to consumers. Always handle `error` and `close`
explicitly.

## Build configuration

### Vite

- Dev port and host are set in `vite.config.ts` — read it; don't
  hardcode `8080` etc.
- Path aliases (commonly `@` → `./src`) are declared in both
  `vite.config.ts` and `tsconfig.json` — keep them in sync.
- React plugin: `@vitejs/plugin-react` (Babel) or
  `@vitejs/plugin-react-swc` (SWC, faster).

### TypeScript

- Strict mode (`strict: true`) should already be on. If it isn't and
  you're touching new code, leave it as-is for the issue and flag
  via `fyi`.
- Useful extras when adopted: `noUncheckedIndexedAccess: true`,
  `exactOptionalPropertyTypes: true`.

### Runtime configuration

A common pattern: ship one build artefact and load environment-
specific config at app startup from a `/config.json` (or equivalent)
fetched on first render. This avoids rebuilding per environment.

1. `public/config.json` — replaceable per environment.
2. `src/lib/config.ts` — fetches and parses at startup.
3. A `ConfigContext` provides typed config to the tree.
4. The app shows a loading state until config is loaded.

`VITE_*` / `NEXT_PUBLIC_*` env variables are then reserved for true
build-time values (commit SHA, app version) — anything that changes
per deployment goes in the runtime config.

## Directory structure (typical)

```
<repo>/
├── src/
│   ├── api/                 # API client + endpoint definitions
│   ├── components/
│   │   ├── auth/            # auth-related components (guards, login)
│   │   ├── <feature>/       # one directory per feature
│   │   ├── common/          # cross-cutting components
│   │   ├── layout/          # shells, headers, navigation
│   │   └── ui/              # design-system primitives (shadcn/ui etc.)
│   ├── contexts/            # React Context providers
│   ├── hooks/               # custom hooks (use<Noun>...)
│   ├── lib/                 # third-party setup (firebase.ts, etc.)
│   ├── pages/               # route targets (SPA) — n/a for Next.js
│   ├── types/               # TypeScript type definitions
│   └── utils/               # helper functions
├── public/                  # static assets
├── dist/ or .next/          # build output (gitignored)
├── index.html               # SPA entry point (Vite)
├── vite.config.ts | next.config.ts
├── tsconfig.json
├── biome.json | .eslintrc + .prettierrc
└── package.json
```

This is a starting shape, not a contract. Read what's actually in
the repo before assuming.
