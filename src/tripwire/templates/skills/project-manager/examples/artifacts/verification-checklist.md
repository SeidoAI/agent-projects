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

## Schema parity

This session ships an OpenAPI schema fragment for `POST /v1/auth/token`.

- [x] Located the canonical shape in the issue body or referenced
      spec section. File: `issues/SEI-42/issue.yaml:78` (under the
      `## OpenAPI fragment` heading).
- [x] Located the shipped shape in the implementation. File:
      `web-app-backend/src/api/openapi/auth.yaml:14`.
- [x] Verified BYTE-EQUIVALENT match between the two. Method:
      side-by-side diff via `diff <(yq '.openapi_fragment' issue.yaml) auth.yaml`.
- [x] If the shapes diverge, STOPPED AND ASKED — N/A, no divergence.
- [x] Authored at least one TDD test that asserts the CANONICAL shape.
      Test: `tests/api/test_auth_token_schema.py::test_response_matches_openapi_fragment`.
- [x] Recorded any shape change in `decisions.md` — N/A, shipped
      canonical.

## Concept graph
- [x] [[auth-token-endpoint]] node created and referenced in SEI-42
- [x] [[user-model]] rehashed after touching `src/models/user.py` (no-op; not touched)
- [x] Every `[[reference]]` in committed markdown resolves
- [x] `tripwire node refs check` reports no dangling refs

## Artifacts
- [x] plan.md committed
- [x] task-checklist.md committed and up-to-date
- [x] verification-checklist.md committed (this file)
- [x] recommended-testing-plan.md committed
- [x] post-completion-comments.md committed
- [x] developer.md draft at `issues/SEI-42/developer.md`

## PM review gate
- [x] `tripwire validate` exits 0
- [x] No standards violations from `standards.md`
