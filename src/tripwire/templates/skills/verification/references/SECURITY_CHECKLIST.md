# Security Checklist for Verification

Run through this list for any PR that touches authentication,
authorization, user input handling, or data access. Miss an item and
you might approve a security regression.

## Authentication

- [ ] **Input validation on every user-supplied field**. Email format,
      string length limits, type checks. The endpoint should reject
      malformed input with 422 before doing any work.
- [ ] **No credential leaks in error messages**. "Invalid email or
      password" is fine. "Email not found in database" is a leak
      (user enumeration). "Incorrect password for user@example.com"
      is worse.
- [ ] **Constant-time comparisons for secrets**. Password hashes,
      JWTs, API keys — all compared with a constant-time function
      (`secrets.compare_digest`, `hmac.compare_digest`), never `==`.
- [ ] **Rate limiting where the issue requires it**. Both login and
      token refresh endpoints. Check both the limiter config AND
      that it's actually called in the handler.
- [ ] **JWT validation includes expiry, signature, algorithm**.
      Don't accept `alg: none`. Don't skip signature verification.
- [ ] **Session cookies set `httpOnly`, `Secure`, `SameSite`**. Per
      the decision record for the project (usually there's a
      `dec-xxx-session-tokens` node).
- [ ] **Password hashing uses bcrypt/argon2 at appropriate cost**,
      not SHA-256, not MD5.

## Authorization

- [ ] **Every query scoped to the current user/tenant**. Look for
      `.where("tenant_id", "==", current_tenant_id)` (or equivalent)
      in every database read. Missing scope → cross-tenant leak.
- [ ] **No superuser backdoors**. `if user.is_admin: return all_data`
      is a red flag unless the issue explicitly says admin scope is
      the goal.
- [ ] **Resource ownership checked before mutation**. Updating a
      record requires proof that the current user owns it, not just
      that they're authenticated.
- [ ] **List endpoints don't leak across tenants**. A `GET /items`
      must filter by the current user's tenant, always.
- [ ] **Relationship walks check permission**. If accessing
      `user.organization.secrets`, each hop must be permitted.

## Input handling

- [ ] **No SQL injection paths**. All queries parameterised. No
      string formatting of user input into SQL.
- [ ] **No path traversal**. User-supplied filenames validated
      against a whitelist or sanitised with `os.path.basename`.
- [ ] **No command injection**. If the code shells out, user input
      is passed via argument list (`subprocess.run(["cmd", user_input])`),
      never via string concatenation (`f"cmd {user_input}"`).
- [ ] **Size limits on inputs**. File uploads, request bodies, query
      parameters. Unbounded input → DOS vector.
- [ ] **Type validation before trust**. Pydantic models (or
      equivalent) validate every field before the handler uses it.

## Output handling

- [ ] **No sensitive data in response bodies**. Password hashes,
      internal IDs, stack traces, Raw PII the user shouldn't see.
- [ ] **No sensitive data in logs**. Passwords, tokens, PII.
      Log the user id, not the user object.
- [ ] **Error envelopes are consistent**. Matching the contract
      (usually defined in a `contract-*` concept node). Stack traces
      only in dev mode.

## Secrets

- [ ] **No hardcoded secrets in code**. Grep the diff for anything
      that looks like a key:
      ```bash
      gh pr diff <number> | grep -iE '(api_key|secret|token|password).*=.*["'\''][a-zA-Z0-9/+]{16,}'
      ```
- [ ] **Secrets come from Secret Manager / env vars**. Reads at
      startup, not hardcoded defaults.
- [ ] **No `.env` files committed**. Check `.gitignore` if in doubt.
- [ ] **No credentials in test fixtures**. Test credentials should
      be obviously-fake placeholders.

## Data safety

- [ ] **Hard deletes require explicit authorization**. The issue
      must explicitly say to delete — agents don't autonomously
      drop data.
- [ ] **Cascades are documented**. If deleting A removes B, the
      issue must say so and the code must match.
- [ ] **Destructive migrations are reversible**. Down-migration
      present; tested.

## What to do when you find a security issue

1. **Immediately request changes** — do not approve, do not wait
   for the coding agent to fix another issue first.
2. **Quote the vulnerable code** with a file:line reference.
3. **Explain the exploit scenario** — what bad input or action
   triggers the problem.
4. **Say what the fix should do** (not "fix the bug" — specific
   direction like "use `secrets.compare_digest` for the token
   comparison").
5. **Escalate to a human via `fyi` message** if it's a class of
   issue (not just one instance) that the agent may repeat.

Security issues are the one class where it's worth slowing down
everyone's flow to make sure the fix lands correctly.

## See also

- `REWARD_HACKING.md` — the "always-true conditions" pattern maps to
  missing authz checks
- `SKILL.md` (verification) — the full verification workflow
