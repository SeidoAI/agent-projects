"""Python hook scripts for custom orchestration logic.

Add modules here and reference them from `orchestration/default.yaml`
(or any other pattern) via dotted names. Each hook receives an `Event`
and `Context` object and returns a dict that the orchestrator merges
into its decision state.

Example — `custom_verifier.py`:

    from tripwire.orchestration import Event, Context

    def maybe_skip_verifier(event: Event, ctx: Context) -> dict:
        \"\"\"Skip verifier for trivial PRs (e.g. only docs changed).\"\"\"
        if all(f.endswith(".md") for f in ctx.pr_files):
            return {"skip": True}
        return {"skip": False}

Then in orchestration/default.yaml:

    hooks:
      pre_re_engage: hooks.custom_verifier.maybe_skip_verifier
"""
