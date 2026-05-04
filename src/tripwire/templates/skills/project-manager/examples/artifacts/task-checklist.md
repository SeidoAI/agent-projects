# Task Checklist — api-endpoints-core

| # | Task | Status | Comments |
|---|------|--------|----------|
| 1 | Read `src/api/auth.py` and understand the existing router | done | — |
| 2 | Confirm [[user-model]] exposes `find_by_email` and `verify_password` | done | Both present; verify_password uses bcrypt. |
| 3 | Read [[contract-auth-token]] for the response envelope | done | — |
| 4 | Read [[dec-007-rate-limiting]] to confirm where to apply the limiter | done | Rate limiter runs BEFORE the user lookup to avoid enumeration attacks. |
| 5 | Implement `POST /auth/token` handler | in_progress | Skeleton in place; wiring in the JWT signing next. |
| 6 | Add unit tests for happy path, 401, 403, rate-limit cases | pending | — |
| 7 | Add integration test for the full HTTP flow | pending | — |
| 8 | Run `make lint` and fix any issues | pending | — |
| 9 | Create [[auth-token-endpoint]] node and reference it in SEI-42 | pending | — |
| 10 | Write `issues/SEI-42/developer.md` | pending | — |
| 11 | Run `tripwire validate` until clean | pending | Must be exit 0 before commit. |
| 12 | Write verification-checklist.md | pending | — |
| 13 | Write recommended-testing-plan.md | pending | — |
| 14 | Write post-completion-comments.md | pending | — |
| 15 | Commit and open PR | pending | — |
