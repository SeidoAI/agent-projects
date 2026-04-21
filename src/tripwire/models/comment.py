"""Comment model.

Comments are stored as individual files under
`issues/<KEY>/comments/<sequence>-<topic>-<date>.yaml`, alongside the
issue YAML they belong to. Each comment carries a UUID for canonical
identity and a free-form Markdown body.
"""

import uuid as _uuid
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class Comment(BaseModel):
    """A single comment on an issue."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    uuid: UUID = Field(default_factory=_uuid.uuid4)

    issue_key: str
    author: str
    type: str
    created_at: datetime

    body: str = ""
