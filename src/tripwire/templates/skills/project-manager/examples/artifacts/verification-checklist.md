# Verification Checklist — api-endpoints-core

## Acceptance criteria
- [x] Happy path returns 200 + valid JWT (SEI-42 AC#1)
- [x] Invalid credentials return 401 with standard envelope (SEI-42 AC#2)
- [x] Expired token replay returns 403 (SEI-42 AC#3)
- [x] Rate limit enforces per [[dec-007-rate-limiting]] (SEI-42 AC#4)
- [x] Unit tests cover all four cases (SEI-42 AC#5)
- [x] CI passing (SEI-42 AC#6)

## Code quality
- [x] Unit tests pass locally: `uv run pytest tests/unit/test_auth.py -v`
- [x] Integration tests pass: `uv run pytest tests/integration/test_auth_flow.py -v`
- [x] Lint passes: `make lint`
- [x] Type check passes: `uv run ty check src/api/auth.py`
- [x] No hardcoded secrets (JWT_SECRET read from env at startup)
- [x] No unused imports or debug prints

## Concept graph
- [x] [[auth-token-endpoint]] node created and referenced in SEI-42
- [x] [[user-model]] rehashed after touching `src/models/user.py` (no-op; not touched)
- [x] Every `[[reference]]` in committed markdown resolves
- [x] `tripwire refs check` reports no dangling refs

## Artifacts
- [x] plan.md committed
- [x] task-checklist.md committed and up-to-date
- [x] verification-checklist.md committed (this file)
- [x] recommended-testing-plan.md committed
- [x] post-completion-comments.md committed
- [x] developer.md draft at `issues/SEI-42/developer.md`

## PM review gate
- [x] `tripwire validate --strict` exits 0
- [x] No standards violations from `standards.md`
