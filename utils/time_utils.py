from datetime import datetime, timezone, timedelta, date

# Indian Standard Time (IST) timezone definition (UTC+05:30)
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now() -> datetime:
    """Returns current naive-aware datetime in Indian Standard Time (IST)."""
    return datetime.now(IST)

def get_ist_today_str() -> str:
    """Returns current date in IST as 'YYYY-MM-DD'."""
    return get_ist_now().strftime("%Y-%m-%d")

def get_ist_time_str(fmt: str = "%H:%M:%S") -> str:
    """Returns current formatted time in IST."""
    return get_ist_now().strftime(fmt)

def get_ist_iso() -> str:
    """Returns ISO 8601 formatted string with +05:30 timezone offset."""
    return get_ist_now().isoformat()
