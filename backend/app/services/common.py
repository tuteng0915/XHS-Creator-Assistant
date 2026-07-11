from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def as_iso(value: datetime) -> str:
    return value.isoformat(timespec="microseconds")

