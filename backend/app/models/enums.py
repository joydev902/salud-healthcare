from enum import StrEnum


class UserRole(StrEnum):
    ADMIN = "ADMIN"
    CODER = "CODER"


class Disposition(StrEnum):
    OPEN = "OPEN"
    CONFIRMED = "CONFIRMED"
    DENIED = "DENIED"
    PENDING_CHART = "PENDING_CHART"
    REFERRED_TO_PROVIDER = "REFERRED_TO_PROVIDER"


USER_SELECTABLE_DISPOSITIONS = frozenset(
    {
        Disposition.CONFIRMED,
        Disposition.DENIED,
        Disposition.PENDING_CHART,
        Disposition.REFERRED_TO_PROVIDER,
    }
)
ACTIVE_DISPOSITIONS = frozenset(
    {Disposition.OPEN, Disposition.PENDING_CHART, Disposition.REFERRED_TO_PROVIDER}
)


class UploadStatus(StrEnum):
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
