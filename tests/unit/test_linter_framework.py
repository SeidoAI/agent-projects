"""Lint framework: stage dispatch, rule registration, severity exit codes."""

from tripwire.core.linter import (
    Linter,
    LintFinding,
    exit_code_for,
    register_rule,
)


def _make_finding(code: str, severity: str) -> LintFinding:
    return LintFinding(code=code, severity=severity, message="x", file="x.yaml")


class TestRegistration:
    def test_register_and_run_single_rule(self, tmp_path):
        marker_code = "test/registered_sample"

        @register_rule(stage="scoping", code=marker_code, severity="warning")
        def _sample(ctx):
            yield LintFinding(
                code=marker_code,
                severity="warning",
                message="sample finding",
                file="project.yaml",
            )

        linter = Linter(project_dir=tmp_path)
        findings = list(linter.run_stage("scoping"))
        assert any(f.code == marker_code for f in findings)

    def test_stage_filter_excludes_other_stages(self, tmp_path):
        marker_code = "test/other_stage"

        @register_rule(stage="handoff", code=marker_code, severity="error")
        def _other(ctx):
            yield LintFinding(
                code=marker_code,
                severity="error",
                message="x",
                file="x.yaml",
            )

        linter = Linter(project_dir=tmp_path)
        scoping_findings = list(linter.run_stage("scoping"))
        assert not any(f.code == marker_code for f in scoping_findings)


class TestExitCode:
    def test_no_findings_exits_zero(self):
        assert exit_code_for([]) == 0

    def test_info_only_exits_zero(self):
        assert exit_code_for([_make_finding("x", "info")]) == 0

    def test_warning_present_exits_one(self):
        assert (
            exit_code_for([_make_finding("x", "info"), _make_finding("y", "warning")])
            == 1
        )

    def test_error_present_exits_two(self):
        assert (
            exit_code_for(
                [
                    _make_finding("x", "warning"),
                    _make_finding("y", "error"),
                ]
            )
            == 2
        )
