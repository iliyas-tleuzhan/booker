from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
import os


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _as_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    google_calendar_id: str
    telegram_bot_token: str
    telegram_chat_id: str
    hkul_booking_url: str
    timezone: str
    default_slot_duration_minutes: int
    planner_hour: int
    planner_minute: int
    booking_hour: int
    booking_minute: int
    telegram_poll_interval_seconds: int
    target_booking_offset_days: int
    playwright_auth_state_path: Path
    screenshot_dir: Path
    database_path: Path
    dry_run: bool


def load_settings() -> Settings:
    load_dotenv()
    return Settings(
        google_calendar_id=os.getenv("GOOGLE_CALENDAR_ID", "primary"),
        telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
        telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
        hkul_booking_url=os.getenv("HKUL_BOOKING_URL", ""),
        timezone=os.getenv("TIMEZONE", "Asia/Hong_Kong"),
        default_slot_duration_minutes=_as_int("DEFAULT_SLOT_DURATION_MINUTES", 120),
        planner_hour=_as_int("PLANNER_HOUR", 23),
        planner_minute=_as_int("PLANNER_MINUTE", 30),
        booking_hour=_as_int("BOOKING_HOUR", 0),
        booking_minute=_as_int("BOOKING_MINUTE", 0),
        telegram_poll_interval_seconds=_as_int("TELEGRAM_POLL_INTERVAL_SECONDS", 60),
        target_booking_offset_days=_as_int("TARGET_BOOKING_OFFSET_DAYS", 2),
        playwright_auth_state_path=Path(os.getenv("PLAYWRIGHT_AUTH_STATE_PATH", "playwright/.auth/hku.json")),
        screenshot_dir=Path(os.getenv("SCREENSHOT_DIR", "data/screenshots")),
        database_path=Path(os.getenv("DATABASE_PATH", "data/bookings.db")),
        dry_run=_as_bool(os.getenv("DRY_RUN"), True),
    )


settings = load_settings()
