from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
from datetime import datetime, timezone


def convert_to_tz(dt: datetime | None, tz_name: str) -> datetime | None:
    """Convertit un datetime UTC en fuseau horaire local."""
    if dt is None:
        return None
    dt_utc = dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    try:
        return dt_utc.astimezone(ZoneInfo(tz_name))
    except ZoneInfoNotFoundError:
        return dt_utc


def naive_to_utc(dt: datetime | None, tz_name: str) -> datetime | None:
    """Interprète un datetime naïf comme appartenant au fuseau tz_name et le convertit en UTC.
    Si le datetime est déjà timezone-aware, le convertit simplement en UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    try:
        local = dt.replace(tzinfo=ZoneInfo(tz_name))
        return local.astimezone(timezone.utc)
    except ZoneInfoNotFoundError:
        return dt.replace(tzinfo=timezone.utc)
