"""Comment model.

Comments are stored as individual files under
`issues/<KEY>/comments/<sequence>-<topic>-<date>.yaml`, alongside the
issue YAML they belong to. Each comment carries a UUID for canonical
identity and a free-form Markdown body.
"""

import uuid as _uuid
from datetime import datetime

from pydantic import UUID4, BaseModel, ConfigDict, Field


class Comment(BaseModel):
    """A single comment on an issue."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    uuid: UUID4 = Field(default_factory=_uuid.uuid4)

    # Integer schema/contract version. KUI-126 / A1.
    version: int = 1

    # KUI-127 / A2: PM-set marker for the latest contract-change version.
    contract_changed_at: int | None = None

    issue_key: str
    author: str
    type: str
    created_at: datetime

    body: str = ""
