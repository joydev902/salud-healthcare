import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel

from app.models import UploadStatus


class ImportIssue(BaseModel):
    row: int
    field: str | None
    reason: str


class ImportSummary(BaseModel):
    id: uuid.UUID
    filename: str
    sha256: str
    status: UploadStatus
    uploaded_by_email: str
    started_at: datetime
    finished_at: datetime | None
    total_rows: int
    inserted_source_rows: int
    duplicate_source_rows: int
    rejected_rows: int
    new_opportunities: int


class ImportDetail(ImportSummary):
    message: str | None = None
    missing_columns: list[str] = []
    error_count: int = 0
    warning_count: int = 0
    errors: list[ImportIssue] = []
    warnings: list[ImportIssue] = []

    @classmethod
    def from_summary(cls, summary: ImportSummary, error_summary: dict[str, Any] | None):
        es = error_summary or {}
        return cls(
            **summary.model_dump(),
            message=es.get("message"),
            missing_columns=es.get("missing_columns", []),
            error_count=es.get("error_count", 0),
            warning_count=es.get("warning_count", 0),
            errors=es.get("errors", []),
            warnings=es.get("warnings", []),
        )


class ImportPage(BaseModel):
    items: list[ImportSummary]
    next_cursor: str | None
    has_more: bool
