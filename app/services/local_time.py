from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.models import get_config


DEFAULT_TIMEZONE = "America/Asuncion"


def configured_timezone():
    """Return the court timezone, with a safe Paraguay fallback."""
    try:
        timezone_name = get_config().timezone or DEFAULT_TIMEZONE
        return ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError, AttributeError):
        # Paraguay uses UTC-03:00 year-round. This keeps booking checks safe
        # even if a minimal local Python installation has no IANA database.
        return timezone(timedelta(hours=-3), name=DEFAULT_TIMEZONE)


def local_now():
    """Current wall-clock time for the configured court."""
    return datetime.now(configured_timezone())


def local_today():
    return local_now().date()


def utc_bounds_for_local_dates(start: date, end: date):
    """Convert an inclusive local date range to UTC-naive database bounds."""
    zone = configured_timezone()
    start_local = datetime.combine(start, time.min, tzinfo=zone)
    end_local = datetime.combine(end, time.max, tzinfo=zone)
    return (
        start_local.astimezone(timezone.utc).replace(tzinfo=None),
        end_local.astimezone(timezone.utc).replace(tzinfo=None),
    )
