# Plan — wave1-agent-a

## Goal
Implement the JWT authentication endpoint (SEI-42) in `web-app-backend`.
The endpoint must satisfy [[contract-auth-token]] and use the
[[user-model]] for credential lookups. Session tokens follow
[[dec-003-session-tokens]] (httpOnly cookies, no localStorage).

## Issues in scope
- SEI-42: Implement JWT authentication endpoint

## Repos
- SeidoAI/web-app-backend (primary; new branch `claude/SEI-42-auth`)

## Approach

### Phase 1: Investigation
Read the existing auth router at `src/api/auth.py` to understand the
current structure. Confirm that [[user-model]] exposes the lookup
methods I need (`find_by_email`, `verify_password`). Read
[[contract-auth-token]] to confirm the exact response envelope.

### Phase 2: Implementation
1. Add `POST /auth/token` handler to `src/api/auth.py` (new function,
   does not touch existing handlers).
2. Use [[user-model]] to look up the user and verify the password.
3. Sign the JWT using `JWT_SECRET` ([[config-jwt-secret]]).
4. Set the token via the cookie helpers per [[dec-003-session-tokens]].
5. Return `{access_token, expires_in, token_type}` per [[contract-auth-token]].

### Phase 3: Verification
Run the unit tests, lint, and `agent-project validate --strict`. Write
`developer.md` and the verification checklist.

## Key decisions
- Decision: use `python-jose[cryptography]` for signing. Rationale: built-in
  JWE support for SEI-58's planned future work. Alternative: `pyjwt` —
  simpler but no JWE, would require a migration later.
- Decision: use a constant-time comparison for password verification via
  the `secrets` stdlib module, not `==`. Rationale: timing-attack safety.

## Risks and unknowns
- Risk: `[[user-model]].verify_password` is untested under load. Mitigation:
  the integration test simulates 100 concurrent auth requests.
- Unknown: whether rate-limiting ([[dec-007-rate-limiting]]) should be
  applied before or after the user lookup. Will read the decision doc
  before implementing.

## Out of scope
- Refresh token flow — that's SEI-45.
- Password reset — not in this epic.
- OAuth social login — future work.
