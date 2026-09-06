import asyncio
from datetime import datetime
from typing import Optional, Tuple, Union

REMIND_BEFORE_SECONDS = 5 * 60


def remaining_seconds_until(ends_at: Union[str, datetime]) -> int:
    end_time = datetime.fromisoformat(ends_at) if isinstance(ends_at, str) else ends_at
    now = datetime.now().astimezone() if end_time.tzinfo else datetime.now()
    return max(0, int((end_time - now).total_seconds()))


def warning_sleep_plan(
    remaining_seconds: int,
    remind_before: int = REMIND_BEFORE_SECONDS,
) -> Tuple[int, int, bool]:
    """Split a countdown into (sleep_until_warning, sleep_after_warning, should_warn)."""
    remaining = max(0, int(remaining_seconds))
    remind_before = max(0, int(remind_before))
    if remaining > remind_before:
        return remaining - remind_before, remind_before, True
    return remaining, 0, False


async def sleep_with_five_minute_warning(
    remaining_seconds: int,
    title: str,
    message: str,
    ends_at: Optional[Union[str, datetime]] = None,
):
    """Wait until the timer ends, showing a dismissible reminder at 5 minutes left."""
    from blocker_window import blocker

    first, second, should_warn = warning_sleep_plan(remaining_seconds)
    if first:
        await asyncio.sleep(first)
    if should_warn:
        blocker.show_message(title, message)
        if ends_at is not None:
            second = remaining_seconds_until(ends_at)
    if second:
        await asyncio.sleep(second)
