from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum


class BookingStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    BOOKED = "booked"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class BusyBlock:
    start: datetime
    end: datetime


@dataclass(frozen=True)
class FreeSlot:
    start: datetime
    end: datetime

    @property
    def duration_minutes(self) -> int:
        return int((self.end - self.start).total_seconds() // 60)


@dataclass(frozen=True)
class BookingRequest:
    id: int
    target_date: date
    start_time: datetime
    end_time: datetime
    room_choice: str | None
    status: BookingStatus
    telegram_message_id: int | None
    screenshot_path: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class BookingResult:
    success: bool
    status: str
    screenshot_path: str | None = None
    error_message: str | None = None
