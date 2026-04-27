"""Timezone helpers for IST business-day aligned comparisons."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional, Tuple


IST = ZoneInfo("Asia/Kolkata")


def _to_ist_day(value: date | datetime | str) -> date:
    if isinstance(value, str):
        return datetime.strptime(value, "%Y-%m-%d").date()
    if isinstance(value, datetime):
        dt = value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)
        return dt.astimezone(IST).date()
    return value


def get_ist_day_bounds(value: date | datetime | str) -> Tuple[datetime, datetime]:
    """Return UTC [start, end_exclusive) bounds for an IST business day."""
    ist_day = _to_ist_day(value)
    start_ist = datetime.combine(ist_day, time.min, tzinfo=IST)
    next_day_ist = start_ist + timedelta(days=1)
    return start_ist.astimezone(timezone.utc), next_day_ist.astimezone(timezone.utc)


def normalize_date_range_ist(
    from_date: date | datetime | str,
    to_date: date | datetime | str,
    *,
    closed_window_mode: bool = False,
    now_ist: Optional[datetime] = None,
) -> Tuple[datetime, datetime, dict]:
    """
    Normalize input range to UTC [start, end_exclusive) IST business-day bounds.

    When closed_window_mode is enabled, any `to_date` on/after IST today is clipped to yesterday.
    """
    from_day = _to_ist_day(from_date)
    to_day = _to_ist_day(to_date)

    effective_now_ist = (now_ist or datetime.now(IST)).astimezone(IST)
    today_ist = effective_now_ist.date()
    adjusted = False
    warning = None

    if closed_window_mode and to_day >= today_ist:
        to_day = today_ist - timedelta(days=1)
        adjusted = True
        warning = "to_date adjusted to yesterday because closed_window_mode=true"

    if to_day < from_day:
        raise ValueError("to_date cannot be earlier than from_date after IST normalization")

    start_utc, _ = get_ist_day_bounds(from_day)
    _, end_exclusive_utc = get_ist_day_bounds(to_day)
    metadata = {
        "timezone": "IST",
        "from_date_ist": from_day.isoformat(),
        "to_date_ist": to_day.isoformat(),
        "window_type": "closed" if to_day < today_ist else "open",
        "data_completeness": "final" if to_day < today_ist else "partial",
        "closed_window_mode": bool(closed_window_mode),
        "adjusted_to_closed_window": adjusted,
    }
    if warning:
        metadata["warning"] = warning
    return start_utc, end_exclusive_utc, metadata


def is_closed_window(
    from_date: date | datetime | str,
    to_date: date | datetime | str,
    *,
    now_ist: Optional[datetime] = None,
) -> bool:
    """Return True when the range does not include IST today."""
    _, _, meta = normalize_date_range_ist(from_date, to_date, closed_window_mode=False, now_ist=now_ist)
    return meta["window_type"] == "closed"

