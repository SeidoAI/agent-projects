"""Inbox has exactly two buckets: ``blocked`` and ``fyi``.

Philosophy §5 ("The two-bucket attention model") is one of the
sharpest claims in the doc:

    *"The inbox solves this with exactly two buckets: `bucket:
    blocked` — interruptive ... `bucket: fyi` — digest ...
    Why not three buckets, or five? Triage cost grows non-linearly
    with bucket count. If a finer distinction matters,
    `escalation_reason` is a queryable string field — encode the
    distinction there, not in another panel."*

The *exact* count of two is load-bearing. A third bucket isn't
just "one more option" — it changes the cognitive treatment the
human applies to the whole inbox. The §5 motivation ("alert chrome
for BLOCKED, muted chrome for FYI; the visual encoding tells the
human which cognitive mode to engage") only works when the
encoding is binary.

This test pins the count at the type level. ``InboxBucket =
Literal["blocked", "fyi"]`` is the single source of truth; this
test reads it and asserts the value set hasn't grown.
"""

from __future__ import annotations

from tripwire.models.inbox import InboxBucket


def test_inbox_bucket_literal_has_exactly_blocked_and_fyi():
    """``InboxBucket`` is a ``Literal[...]`` whose value set is
    ``{"blocked", "fyi"}`` — no more, no less.

    A failure here means someone tried to add a third bucket. Before
    accepting the change, §5 says: ask whether the finer distinction
    fits in ``escalation_reason`` instead. The threshold for a new
    bucket is high — it triggers a UI cognitive-mode change.
    """
    # `typing.Literal[...]` exposes its arguments via __args__.
    args = getattr(InboxBucket, "__args__", None)
    assert args is not None, (
        "InboxBucket is no longer a typing.Literal; the test's "
        "introspection shape is stale. Update this test to match "
        "the new type definition."
    )

    actual = set(args)
    expected = {"blocked", "fyi"}

    assert actual == expected, (
        "Philosophy §5 violation — InboxBucket no longer has exactly the\n"
        "two declared buckets.\n"
        "\n"
        f"  expected: {sorted(expected)}\n"
        f"  actual:   {sorted(actual)}\n"
        "\n"
        "Adding a bucket changes the cognitive treatment the human applies\n"
        "to the whole inbox — it's not a small change. §5 says: if a finer\n"
        "distinction matters, encode it in `escalation_reason` (a queryable\n"
        "string field). Don't add another bucket.\n"
        "\n"
        "Removing a bucket means the corresponding cognitive mode\n"
        "disappeared from the product — update `docs/philosophy.md` §5\n"
        "and `dec-two-bucket-attention-model` to reflect the new shape."
    )
