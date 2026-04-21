# Dependencies

Adding or upgrading a Python dependency is a scoped decision with
long-term consequences. Follow this discipline.

## When you may add a dependency

- The issue explicitly says to.
- The problem genuinely requires a library (crypto, parsing, an
  external API) that the standard library can't solve cleanly.
- The library is well-maintained, widely used, and has a license
  compatible with the project.

## When you may NOT add a dependency

- To save 10 lines of code.
- For a one-off transformation you could write inline.
- To avoid thinking about the problem.
- Because "this library usually has this function" without checking.
- If the library has fewer than ~100 GitHub stars, or hasn't been
  updated in the last year.

## The procedure

1. **Justify in plan.md** — before editing `pyproject.toml`, write
   in your plan what you're adding, why, and what you considered as
   alternatives.
2. **If the issue didn't authorize it**, send a `question` message:
   ```
   type: question
   priority: blocking
   body: |
     SEI-42 needs JWT signing. The standard library has no JWT
     support. I see three options:
     - python-jose (has JWE, widely used, 1.8k stars)
     - pyjwt (simpler, very widely used, 4.5k stars)
     - authlib (does more than JWT, might be overkill)

     My preference: python-jose, because SEI-58's planned future
     work needs JWE and we'd have to migrate if we picked pyjwt.

     Approve python-jose, or specify a different choice?
   ```
3. **Add via the project's tool**:
   - `uv add <package>` (if using uv)
   - `pip install <package>` + update `pyproject.toml`/`requirements.txt`
4. **Commit `pyproject.toml` and lockfile together**:
   ```
   chore(SEI-42): add python-jose for JWT signing
   ```
5. **Run the full test suite** to confirm nothing else broke.

## Upgrading a dependency

Same discipline. Don't upgrade "because there's a new version" —
upgrade because you need a specific fix or feature, OR because the
current version has a security issue.

1. Read the changelog between your current version and the target.
2. Run tests against the new version locally.
3. Commit the version bump separately from any code changes the
   upgrade forces.

## Removing a dependency

If you notice an unused dependency, surface it via `post-completion-comments.md`
as a follow-up suggestion. Don't remove it in the same PR as
unrelated work.

## See also

- `TDD.md` — tests protect you from regressions when you add or
  upgrade dependencies.
