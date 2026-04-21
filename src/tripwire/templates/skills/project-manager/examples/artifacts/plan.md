# Plan — api-endpoints-core

## Context
Implement the JWT authentication endpoint (SEI-42) in `web-app-backend`.
The endpoint must satisfy [[contract-auth-token]] and use the
[[user-model]] for credential lookups. Session tokens follow
[[dec-003-session-tokens]] (httpOnly cookies, no localStorage).

## Issues in scope
- SEI-42: Implement JWT authentication endpoint

## Repos
- SeidoAI/web-app-backend (primary; new branch `claude/SEI-42-auth`)

## Steps

### Step 1: Read existing auth structure
- **Files:** `src/api/auth.py` (full file)
- **Change:** None — read-only investigation.
- **Action:** Confirm that [[user-model]] exposes `find_by_email` and
  `verify_password`. Read [[contract-auth-token]] to confirm the exact
  response envelope `{access_token, expires_in, token_type}`.
- **Verify:** You can name the function signatures from memory.
- **Est:** 2-3 min

### Step 2: Add the POST /auth/token handler
- **Files:** `src/api/auth.py` (append new handler)
- **Change:** Add `post_auth_token(request: AuthRequest) -> AuthResponse`
  handler. Use [[user-model]].find_by_email + verify_password. Sign JWT
  with `JWT_SECRET` ([[config-jwt-secret]]). Set cookie per
  [[dec-003-session-tokens]].
- **Code:**
  ```python
  @router.post("/auth/token")
  async def post_auth_token(body: AuthRequest) -> AuthResponse:
      user = await User.find_by_email(body.email)
      if not user or not user.verify_password(body.password):
          raise HTTPException(401, "Invalid credentials")
      token = create_access_token(user.id)
      response = AuthResponse(
          access_token=token,
          expires_in=3600,
          token_type="bearer",
      )
      return response
  ```
- **Verify:** `uv run pytest tests/api/test_auth.py -x -q` → all pass
- **Est:** 5 min

### Step 3: Write unit tests for the new handler
- **Files:** `tests/api/test_auth.py` (append)
- **Change:** Add 4 test cases: valid credentials, wrong password, unknown
  email, missing fields. Each test hits the endpoint and asserts the
  response shape and status code.
- **Verify:** `uv run pytest tests/api/test_auth.py -x -q` → 4 new tests pass
- **Est:** 5 min

### Step 4: Run the full verification checklist
- **Files:** (none modified)
- **Change:** None — verification only.
- **Verify:**
  - `uv run pytest tests/ -x -q` → all pass
  - `uv run ruff check .` → clean
  - `tripwire validate --strict` → exit 0
- **Est:** 2 min

## Key decisions
- Use `python-jose[cryptography]` for JWT signing. Rationale: built-in
  JWE support for future SEI-58 work. Alternative: `pyjwt` — simpler
  but no JWE.
- Constant-time password comparison via `secrets.compare_digest`, not
  `==`. Rationale: timing-attack safety.

## Risks
- [[user-model]].verify_password is untested under load. Mitigation:
  the integration test simulates 100 concurrent auth requests.

## Out of scope
- Refresh token flow (SEI-45), password reset, OAuth social login.

## Verification
- [ ] `uv run pytest tests/ -x -q` passes
- [ ] `uv run ruff check .` clean
- [ ] `tripwire validate --strict` exits 0
- [ ] Response matches [[contract-auth-token]] envelope exactly
