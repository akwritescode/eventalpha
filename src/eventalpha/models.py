"""The one normalized shape every source is converted into."""

from __future__ import annotations

import hashlib
from datetime import datetime

from pydantic import BaseModel, Field, computed_field, field_validator

MAX_BODY_CHARS = 20_000  # ~5k tokens; keeps classifier requests small and cheap


class Article(BaseModel):
    source: str  # "sec_edgar" or "rss:<feed name>"
    source_id: str  # accession number, or feed GUID
    form_type: str | None = None  # SEC form (8-K, 6-K, SCHEDULE 13D, ...) for EDGAR articles
    url: str
    title: str
    published_at: datetime
    summary: str | None = None
    body: str | None = None
    company: str | None = None
    cik: str | None = None
    tickers: list[str] = Field(default_factory=list)
    sec_items: list[str] = Field(default_factory=list)  # 8-K item codes, e.g. ["2.02", "9.01"]

    @field_validator("published_at")
    @classmethod
    def _tz_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("published_at must be timezone-aware")
        return v

    @field_validator("body")
    @classmethod
    def _truncate(cls, v: str | None) -> str | None:
        return v[:MAX_BODY_CHARS] if v else v

    @computed_field  # type: ignore[prop-decorator]
    @property
    def content_hash(self) -> str:
        """Changes only when the text changes, so re-ingesting identical content is a no-op."""
        h = hashlib.sha256()
        for part in (self.title, self.summary or "", self.body or ""):
            h.update(part.encode())
            h.update(b"\x00")
        return h.hexdigest()
