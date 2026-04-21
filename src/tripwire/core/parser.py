"""YAML frontmatter + Markdown body parser.

The file format used by issues, concept nodes, sessions, and comments is:

    ---
    <YAML frontmatter>
    ---
    <Markdown body>

Both halves are optional in principle, but the validator requires frontmatter
for every entity type. This module is intentionally schema-agnostic — it
returns a dict and a string, and lets the model layer construct the typed
objects.
"""

from __future__ import annotations

import yaml

FRONTMATTER_DELIMITER = "---"


class ParseError(ValueError):
    """Raised when a file cannot be parsed as frontmatter + body."""


def parse_frontmatter_body(text: str) -> tuple[dict, str]:
    """Split a frontmatter+body string into (frontmatter dict, body string).

    Accepted shapes:
    - `---\\n<yaml>\\n---\\n<body>` — full frontmatter + body
    - `---\\n<yaml>\\n---\\n` — frontmatter only, empty body
    - `<yaml>` (no delimiters, no body) — bare YAML, returns ({}, text) is wrong;
      we require frontmatter to be wrapped in `---` so the parser is unambiguous.

    Raises:
        ParseError: if the text is not a valid frontmatter+body file.
    """
    if not text.startswith(FRONTMATTER_DELIMITER):
        raise ParseError(
            f"File must begin with a frontmatter delimiter (---). Got: {text[:40]!r}"
        )

    # Strip the leading `---` line.
    after_first = text[len(FRONTMATTER_DELIMITER) :]
    if after_first.startswith("\n"):
        after_first = after_first[1:]
    elif after_first.startswith("\r\n"):
        after_first = after_first[2:]
    else:
        raise ParseError("Frontmatter delimiter (---) must be followed by a newline.")

    # Find the closing delimiter.
    closing_idx = after_first.find(f"\n{FRONTMATTER_DELIMITER}")
    if closing_idx == -1:
        # Maybe the file is just `---\n<yaml>` with no closing delimiter.
        raise ParseError("Frontmatter must be closed with a `---` line on its own.")

    frontmatter_text = after_first[:closing_idx]
    after_closing = after_first[closing_idx + len(f"\n{FRONTMATTER_DELIMITER}") :]

    # Strip the leading newline after the closing `---`.
    if after_closing.startswith("\n"):
        body = after_closing[1:]
    elif after_closing.startswith("\r\n"):
        body = after_closing[2:]
    else:
        body = after_closing

    try:
        frontmatter = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        raise ParseError(f"Invalid YAML in frontmatter: {exc}") from exc

    if not isinstance(frontmatter, dict):
        raise ParseError(
            f"Frontmatter must be a YAML mapping, got {type(frontmatter).__name__}."
        )

    return frontmatter, body


def serialize_frontmatter_body(frontmatter: dict, body: str) -> str:
    """Serialise (frontmatter dict, body string) back to a frontmatter+body file.

    The frontmatter is dumped with `sort_keys=False` to preserve insertion
    order, which the model layer should set deliberately.
    """
    yaml_text = yaml.safe_dump(
        frontmatter,
        sort_keys=False,
        default_flow_style=False,
        allow_unicode=True,
    )
    if not yaml_text.endswith("\n"):
        yaml_text += "\n"

    if body and not body.endswith("\n"):
        body += "\n"

    return f"{FRONTMATTER_DELIMITER}\n{yaml_text}{FRONTMATTER_DELIMITER}\n{body}"
