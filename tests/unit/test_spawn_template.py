"""Content assertions for the shipped `templates/spawn/defaults.yaml`.

Existing `test_spawn_config.py` covers the resolver + the precedence
mechanics. This file pins specific phrases that the v0.7.9 follow-up
batch added to the kickoff and resume prompts so a careless re-flow
of the YAML can't quietly drop them. Each assertion maps to a bug from
the post-mortem (KUI-90):

- bug #4: pre-push ruff format gate (CI was failing 4 of 5 sessions).
- bug #2: explicit transition-to-in_review at the end of the exit
  protocol so PM review isn't gated on hand-edits.
- bug #3: resume prompt must steer the agent at the canonical main-PT
  plan path and warn off the stale PT-worktree copy.
"""

from tripwire.core.spawn_config import load_resolved_spawn_config


class TestExitProtocol:
    def test_exit_protocol_has_ruff_gate(self, tmp_path_project):
        resolved = load_resolved_spawn_config(tmp_path_project)
        prompt = resolved.prompt_template
        assert "ruff format" in prompt
        # The pre-push gate must precede the `git push` step or the
        # CI-fails-on-format-drift problem returns.
        push_idx = prompt.find("git push origin")
        ruff_idx = prompt.find("ruff format")
        assert ruff_idx >= 0 and push_idx >= 0
        assert ruff_idx < push_idx, (
            "ruff format gate must appear BEFORE git push in the exit protocol"
        )

    def test_exit_protocol_ends_with_transition(self, tmp_path_project):
        """The agent's last action in the exit protocol is the
        executing → in_review flip. Anything after this would mean PM
        review can't run yet."""
        resolved = load_resolved_spawn_config(tmp_path_project)
        prompt = resolved.prompt_template
        assert "tripwire session transition" in prompt
        assert "in_review" in prompt
        # The transition step must come after PR creation — the whole
        # point is "PR is open + self-reviewed → flip to in_review".
        pr_create_idx = prompt.find("gh pr create")
        transition_idx = prompt.find("tripwire session transition")
        assert pr_create_idx >= 0 and transition_idx >= 0
        assert transition_idx > pr_create_idx


class TestResumePrompt:
    def test_resume_prompt_says_main_pt_only(self, tmp_path_project):
        resolved = load_resolved_spawn_config(tmp_path_project)
        resume = resolved.resume_prompt_template
        # Must point at the canonical main-PT path that
        # `runtimes/prep.py` resolves and pass through {plan_path}.
        assert "{plan_path}" in resume
        assert "main-PT" in resume
        # Must explicitly steer the agent away from the stale PT-worktree
        # copy that bit two v0.7.9 sessions.
        assert "Do NOT grep" in resume or "do NOT grep" in resume
