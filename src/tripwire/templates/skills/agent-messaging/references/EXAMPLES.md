# Message Examples

Worked examples of every message type. The `body` field accepts
Markdown (except for `status`, which uses a structured object).

## `status` — heartbeat

```json
{
  "type": "status",
  "priority": "informational",
  "body": {
    "state": "investigating",
    "summary": "Reading src/api/auth.py and the [[contract-auth-token]] node to confirm the response shape."
  }
}
```

```json
{
  "type": "status",
  "priority": "informational",
  "body": {
    "state": "testing",
    "summary": "Implementation done. Running `uv run pytest tests/unit/test_auth.py -v`."
  }
}
```

```json
{
  "type": "status",
  "priority": "informational",
  "body": {
    "state": "self_verifying",
    "summary": "Tests pass. Walking the verification-checklist.md to confirm each item before declaring done."
  }
}
```

## `plan_approval` — before implementation

```json
{
  "type": "plan_approval",
  "priority": "blocking",
  "body": "## Plan for SEI-42\n\n## Goal\nImplement POST /auth/token per [[contract-auth-token]].\n\n## Approach\n1. Read [[user-model]] to confirm the lookup methods.\n2. Add the handler to src/api/auth.py.\n3. Use python-jose for signing (see [[dec-003-session-tokens]]).\n4. Set cookie via the existing cookie helpers.\n5. Tests: happy path, 401, 403, rate limit.\n\n## Out of scope\n- Refresh flow (that's SEI-45).\n- Password reset.\n\nRequesting approval before starting code."
}
```

## `question` — blocked by ambiguity

```json
{
  "type": "question",
  "priority": "blocking",
  "body": "## Ambiguity in SEI-42 acceptance criteria\n\nThe ticket says 'expired token returns 403' but [[contract-auth-token]] specifies the error envelope with `code: invalid_credentials`, which is semantically a 401.\n\n**Options:**\n- **A**: Return 403 with `code: token_expired` (matches ticket, adds a new error code)\n- **B**: Return 401 with `code: invalid_credentials` (matches contract, doesn't match ticket)\n- **C**: Return 403 with `code: invalid_credentials` (mixes status and code)\n\n**My preference**: A — the ticket is more recent than the contract, and adding a new error code is a small change. I've checked and no other endpoint uses `token_expired` yet.\n\nCan you confirm A?"
}
```

## `stuck` — tried multiple approaches

```json
{
  "type": "stuck",
  "priority": "blocking",
  "body": "## Stuck on SEI-42 JWT verification\n\n**Goal**: get `jwt.decode()` to succeed on a token we just signed.\n\n**Tried**:\n1. Using `algorithms=['HS256']` — decoding fails with `InvalidSignatureError`.\n2. Switched to `algorithms=['HS512']` to match our signing algorithm — same error.\n3. Checked the JWT_SECRET env var matches between sign and decode — it does (printed both, same 32-char string).\n4. Decoded the token payload by hand at jwt.io — payload is correct, signature is there.\n5. Tried `options={'verify_signature': False}` — that works, so it's specifically a signature issue.\n\n**Current state**: signing and verification are using the same secret and algorithm but the signature still mismatches. Running out of ideas.\n\n**Suspicion**: maybe a byte-encoding issue (bytes vs str for the secret). Haven't confirmed.\n\nCan you take a look? Code is at src/api/auth.py:45-82 on branch claude/SEI-42-auth."
}
```

## `escalation` — scope change needed

```json
{
  "type": "escalation",
  "priority": "blocking",
  "body": "## Escalation: SEI-42 needs to touch web-app-infrastructure\n\nThe ticket assumes [[config-jwt-secret]] is already set in the test environment. I checked the actual env and it's not — the secret hasn't been provisioned.\n\nFixing this requires a Terraform change in SeidoAI/web-app-infrastructure, which is out of scope for SEI-42 (backend only) and outside my agent's permissions.\n\n**Needed**: Either (a) expand SEI-42 scope to include the infra change, or (b) create a blocking issue SEI-X for the infra work and put SEI-42 on hold.\n\nI've stopped work on SEI-42 pending your decision."
}
```

## `handover` — giving up

```json
{
  "type": "handover",
  "priority": "blocking",
  "body": "## Handover: SEI-42 JWT implementation\n\nI've tried three different signing libraries (`python-jose`, `pyjwt`, `authlib`) and each one fails at the same verification step. I suspect the issue is with how the test environment's JWT_SECRET is encoded but I can't confirm from inside the container.\n\n**State**:\n- Branch: `claude/SEI-42-auth` at commit `abc123`\n- Implementation: `src/api/auth.py:45-82` (works for signing, fails for verification)\n- Tests: `tests/unit/test_auth.py` (4 tests, 2 passing, 2 failing on signature)\n- plan.md, task-checklist.md, verification-checklist.md all committed\n\n**Suggested next steps for human takeover**:\n1. Check the actual bytes of JWT_SECRET in the test env (my container can't read Secret Manager directly)\n2. Try a round-trip test outside the container\n3. If the issue is env-level, escalate to infra\n\nI've marked the session as `handed_off`."
}
```

## `progress` — milestone

```json
{
  "type": "progress",
  "priority": "informational",
  "body": "Unit tests all passing for SEI-42 (4/4). Moving to integration tests."
}
```

## `fyi` — interesting finding

```json
{
  "type": "fyi",
  "priority": "informational",
  "body": "Noticed that [[user-model]].find_by_email catches BaseException instead of FirestoreError — swallows KeyboardInterrupt and SystemExit. Not in my scope for SEI-42 but worth a follow-up issue."
}
```
