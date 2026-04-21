# Reward Hacking Patterns

Reward hacking is when an implementation passes its checks (tests,
validator, lint) without actually meeting the intent. Catching it is
the verification agent's highest-value job — a missed reward hack
ships a fake "done" that wastes everyone's time when it's discovered
in production.

Every pattern below is something you should look for during
verification.

## Test-level hacks

### 1. Mocking the thing under test

**Bad**:
```python
def test_auth_endpoint(mocker):
    mocker.patch("src.api.auth.verify_password", return_value=True)
    mocker.patch("src.api.auth.generate_jwt", return_value="fake-token")
    response = client.post("/auth/token", json={"email": "x", "password": "y"})
    assert response.status_code == 200
```

This tests nothing. It mocks both the credential verification AND
the token generation. The "test" is just "the HTTP layer returns
200 when we tell it to".

**Red flag**: the thing being tested is replaced by a mock.

### 2. Assertion-less tests

**Bad**:
```python
def test_generate_token():
    token = generate_token("user-123")
    assert token is not None
```

`assert not None` means "something was returned". A bug-ridden
implementation that returned `"bogus"` would still pass.

**Red flag**: assertions that check existence but not correctness.

### 3. Circular expected values

**Bad**:
```python
def test_hash_password():
    hashed = hash_password("mypass")
    assert hashed == hash_password("mypass")
```

This tests that the function is deterministic, not that it produces
the RIGHT hash. A buggy `hash_password` that returned the input
unchanged would pass.

**Red flag**: expected values computed from the function under test.

### 4. Overly broad exception handling in tests

**Bad**:
```python
def test_error_path():
    try:
        do_the_thing_that_should_fail()
    except Exception:
        pass
```

Now any error at all passes the test, including `ImportError`,
`NameError`, or a typo you introduced.

**Red flag**: `except Exception` or bare `except` in tests.

**Good**:
```python
def test_error_path():
    with pytest.raises(ValueError, match="expired"):
        do_the_thing_that_should_fail()
```

### 5. Disabled or skipped tests

```python
@pytest.mark.skip("Breaks CI, will fix later")
def test_important_thing():
    ...
```

A skipped test is a failing test you're not counting. Look for:
- `@pytest.mark.skip` / `@pytest.mark.skipif`
- `@unittest.skip`
- Commented-out test functions
- Tests moved into a file excluded by `pytest.ini` / `pyproject.toml`

**Red flag**: any of these added in the PR diff.

### 6. Tests that never ran

A brand new test file that claims to have tests the PR implements,
but the test file wasn't included in the CI config. Check
`pyproject.toml` / `pytest.ini` / `conftest.py` for path filters.

## Implementation-level hacks

### 7. Stub functions that claim success

**Bad**:
```python
def generate_token(user_id: str) -> str:
    # TODO: implement JWT signing
    return "pending-implementation"
```

Returns a string that isn't a real token. Passes a shallow type
check.

### 8. Hardcoded test values leaking into production

**Bad**:
```python
def get_user_by_email(email: str) -> User | None:
    if email == "test@example.com":
        return User(id="test-user", email=email)
    # real lookup below
    ...
```

The test passes because the test uses `test@example.com`. Production
fails because nothing outside the test case triggers the real path
that was never tested.

### 9. Silent error swallowing

**Bad**:
```python
def verify_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET, algorithms=["HS256"])
    except Exception:
        return {}
```

Returns an empty dict for any error. Downstream code that checks
`claims.get("sub")` gets `None` and treats the request as
unauthenticated… or, worse, treats it as authenticated as a user
with id `None`.

**Red flag**: broad `except:` in the implementation that swallows
the error silently.

### 10. Always-true conditions

**Bad**:
```python
def is_authorized(user, resource) -> bool:
    if user.tenant_id == resource.tenant_id or True:  # FIXME
        return True
    ...
```

Literally any PR with `or True` or `if True` in auth/authz code is a
critical rejection.

## How to review for these

1. **Read the tests line by line**. Don't just run them.
2. **For each test**, ask: "If the implementation returned wrong
   data, would this test catch it?"
3. **Grep the diff** for red flags:
   ```bash
   gh pr diff <number> | grep -E '(pytest.mark.skip|except Exception|or True|if True|TODO|FIXME|return None  #|assert.*is not None)'
   ```
4. **Run the tests with mutations**: if you're suspicious, manually
   change one line of the implementation to return wrong data and
   confirm the tests fail. If they still pass, they're not testing
   what they claim.

## When you find reward hacking

- Request changes on the PR with specific file/line references.
- Quote the exact problematic code.
- Say what the test/implementation SHOULD do.
- Don't rewrite the code yourself — you're read-only.

If the coding agent has done this multiple times on the same issue,
escalate to a human via an `fyi` message in your verified.md or
via a direct message to the PM agent. This might be a pattern you
need human intervention to correct.

## See also

- `SECURITY_CHECKLIST.md` — auth/authz patterns specifically
- `SKILL.md` (verification) — the full verification workflow
