"""Branch naming convention: <type>/<session-slug>."""

import pytest

from keel.core.branch_naming import (
    ALLOWED_TYPES,
    BranchNameError,
    derive_branch_name,
    is_valid_branch_name,
    parse_branch_name,
)


class TestIsValidBranchName:
    def test_accepts_valid_feat(self):
        assert is_valid_branch_name("feat/infra-gcs") is True

    def test_accepts_valid_fix(self):
        assert is_valid_branch_name("fix/correct-sort-order") is True

    def test_rejects_missing_type(self):
        assert is_valid_branch_name("infra-gcs") is False

    def test_rejects_unknown_type(self):
        assert is_valid_branch_name("wip/infra-gcs") is False

    def test_rejects_uppercase(self):
        assert is_valid_branch_name("feat/Infra-Gcs") is False

    def test_rejects_underscores(self):
        assert is_valid_branch_name("feat/infra_gcs") is False

    def test_rejects_personal_prefix(self):
        assert is_valid_branch_name("maia/feat/infra-gcs") is False

    def test_rejects_too_long(self):
        long_slug = "x" * 100
        assert is_valid_branch_name(f"feat/{long_slug}") is False

    def test_rejects_empty_slug(self):
        assert is_valid_branch_name("feat/") is False

    def test_accepts_exact_max_length(self):
        from keel.core.branch_naming import MAX_BRANCH_LENGTH

        # feat/ = 5 chars; fill rest with 'a' up to the limit.
        slug = "a" * (MAX_BRANCH_LENGTH - len("feat/"))
        assert is_valid_branch_name(f"feat/{slug}") is True

    def test_rejects_one_over_max_length(self):
        from keel.core.branch_naming import MAX_BRANCH_LENGTH

        slug = "a" * (MAX_BRANCH_LENGTH - len("feat/") + 1)
        assert is_valid_branch_name(f"feat/{slug}") is False


class TestParseBranchName:
    def test_parses_valid(self):
        branch_type, slug = parse_branch_name("feat/infra-gcs")
        assert branch_type == "feat"
        assert slug == "infra-gcs"

    def test_raises_on_invalid(self):
        with pytest.raises(BranchNameError):
            parse_branch_name("not-a-branch")


class TestDeriveBranchName:
    def test_from_session_with_prefix_and_feat_issue(self):
        assert derive_branch_name("session-infra-gcs", "feat") == "feat/infra-gcs"

    def test_from_session_without_prefix(self):
        assert derive_branch_name("infra-gcs", "feat") == "feat/infra-gcs"

    def test_rejects_unknown_kind(self):
        with pytest.raises(BranchNameError):
            derive_branch_name("session-x", "epic")

    def test_lowercases_uppercase_session_key(self):
        """`keel next-key --type session` emits keys like 'TST-S1' (uppercase).
        Derive must lowercase the slug so the result matches convention."""
        assert derive_branch_name("TST-S1", "feat") == "feat/tst-s1"


class TestAllowedTypes:
    def test_contains_expected_set(self):
        assert set(ALLOWED_TYPES) == {
            "feat",
            "fix",
            "refactor",
            "docs",
            "chore",
            "test",
        }
