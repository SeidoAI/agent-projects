# Test-Driven Development (Backend)

Write tests before code. Commit tests separately. Run them and
confirm they fail before writing implementation. This is the
discipline — shortcuts cost hours.

## The loop

1. **Write a failing test** for the behaviour you want.
2. **Run it**: `make test` (or `uv run pytest <path>`). The test must
   fail. If it passes before you've written any code, the test isn't
   actually testing what you think.
3. **Commit the test** with a message like `test: add failing test
   for <feature>`.
4. **Write the minimum code** to make the test pass.
5. **Run it**: the test must now pass. Run the full suite to catch
   regressions.
6. **Commit the implementation** with a message like
   `feat: <feature>`.
7. **Refactor if needed** — tests still pass after refactoring.

## What to test

For every issue, write at minimum:

- **Happy path**: the normal success case described in the acceptance
  criteria.
- **Known failure modes**: 401 for unauthenticated, 403 for
  unauthorised, 404 for missing, 422 for validation errors.
- **Edge cases named in the issue**: expired tokens, empty bodies,
  oversized payloads, concurrent access.
- **Regression tests** for any bug you discover while working.

If the issue has ambiguous acceptance criteria, write the tests to
reflect YOUR reading, then surface the ambiguity via a `question`
message BEFORE committing the tests.

## Questioning failing existing tests

If an existing test fails after your change:

1. **First assumption**: your implementation has a bug.
2. **Investigate the existing test**: what is it asserting? Why?
3. **If you still think the test is wrong**, write a comment
   explaining:
   - What the test was asserting
   - Why you believe that assertion is no longer correct
   - What you're replacing it with
4. **Commit the test rewrite separately** from the implementation, so
   the history shows the intent.

Default to "the existing test is right and my code is wrong" —
experienced engineers find this is true 90% of the time.

## Pytest conventions

- Tests live under `tests/unit/` and `tests/integration/`.
- File names start with `test_<module>.py`.
- Function names start with `test_<behaviour>`.
- Use fixtures for shared setup, not `setUp`/`tearDown` methods.
- Parametrize tests that run the same check against multiple inputs
  rather than copy-pasting test bodies.

Example structure:

```python
# tests/unit/test_auth.py
import pytest
from src.api.auth import generate_token, verify_token


class TestGenerateToken:
    def test_happy_path(self) -> None:
        token = generate_token("user-123")
        assert token.startswith("eyJ")  # JWT header marker

    def test_rejects_empty_user(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            generate_token("")


class TestVerifyToken:
    def test_happy_path(self) -> None:
        token = generate_token("user-123")
        claims = verify_token(token)
        assert claims["sub"] == "user-123"

    def test_rejects_expired_token(self) -> None:
        expired = generate_token("user-123", expires_in=-1)
        with pytest.raises(ValueError, match="expired"):
            verify_token(expired)
```

## Coverage

Aim for >80% line coverage on new code. Don't chase 100% — some
branches (e.g. `if TYPE_CHECKING:`) aren't meaningfully testable.
But anything the issue's acceptance criteria mentions MUST be covered.

## Running tests quickly

- `pytest tests/unit/test_<module>.py` — run one file
- `pytest tests/unit/test_<module>.py::test_<name>` — run one test
- `pytest -k "keyword"` — run tests whose name contains the keyword
- `pytest -x` — stop at the first failure
- `pytest -vv --tb=short` — verbose output with short tracebacks

Use these while iterating. Only run the full suite before committing
each step.

## See also

- `COMMIT_PATTERN.md` — the commit sequence test + code fit into.
- `.claude/skills/project-manager/references/VALIDATION.md` — the
  project-level validation gate (runs AFTER your code tests pass).
