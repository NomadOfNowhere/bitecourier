"""Display helpers shared by the web app and the image generator."""
from datetime import datetime


def money(value: float) -> str:
    """9.5 -> "$9.50" """
    return f"${value:,.2f}"


def clock(moment: datetime) -> str:
    """A 12-hour time like "7:05 PM", without platform-specific strftime flags."""
    hour = moment.hour % 12 or 12
    suffix = "AM" if moment.hour < 12 else "PM"
    return f"{hour}:{moment.minute:02d} {suffix}"


def time_range(start: datetime, end: datetime) -> str:
    """"7:05–7:15 PM", or "11:50 AM–12:00 PM" when the range crosses noon/midnight."""
    start_text, end_text = clock(start), clock(end)
    if start_text[-2:] == end_text[-2:]:
        start_text = start_text[:-3]
    return f"{start_text}–{end_text}"
