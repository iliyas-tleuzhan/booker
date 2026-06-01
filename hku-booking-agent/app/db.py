from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from app.config import settings
from app.models import BookingRequest, BookingStatus


SCHEMA = """
CREATE TABLE IF NOT EXISTS booking_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    target_date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    room_choice TEXT,
    status TEXT NOT NULL,
    telegram_message_id INTEGER,
    screenshot_path TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_booking_requests_status_created
ON booking_requests(status, created_at);
"""


@contextmanager
def connect(database_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(database_path or settings.database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(database_path: str | Path | None = None) -> None:
    with connect(database_path) as conn:
        conn.executescript(SCHEMA)


def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _row_to_request(row: sqlite3.Row | None) -> BookingRequest | None:
    if row is None:
        return None
    return BookingRequest(
        id=row["id"],
        target_date=date.fromisoformat(row["target_date"]),
        start_time=datetime.fromisoformat(row["start_time"]),
        end_time=datetime.fromisoformat(row["end_time"]),
        room_choice=row["room_choice"],
        status=BookingStatus(row["status"]),
        telegram_message_id=row["telegram_message_id"],
        screenshot_path=row["screenshot_path"],
        error_message=row["error_message"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


def create_booking_request(
    target_date: date,
    start_time: datetime,
    end_time: datetime,
    room_choice: str | None = None,
    telegram_message_id: int | None = None,
    database_path: str | Path | None = None,
) -> BookingRequest:
    init_db(database_path)
    now = _now_iso()
    with connect(database_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO booking_requests (
                target_date, start_time, end_time, room_choice, status,
                telegram_message_id, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                target_date.isoformat(),
                start_time.isoformat(timespec="seconds"),
                end_time.isoformat(timespec="seconds"),
                room_choice,
                BookingStatus.PENDING.value,
                telegram_message_id,
                now,
                now,
            ),
        )
        row = conn.execute("SELECT * FROM booking_requests WHERE id = ?", (cursor.lastrowid,)).fetchone()
        request = _row_to_request(row)
        assert request is not None
        return request


def get_latest_pending_request(database_path: str | Path | None = None) -> BookingRequest | None:
    init_db(database_path)
    with connect(database_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM booking_requests
            WHERE status = ?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (BookingStatus.PENDING.value,),
        ).fetchone()
        return _row_to_request(row)


def confirm_booking_request(id: int, room_choice: str, database_path: str | Path | None = None) -> BookingRequest | None:
    init_db(database_path)
    with connect(database_path) as conn:
        conn.execute(
            """
            UPDATE booking_requests
            SET status = ?, room_choice = ?, updated_at = ?
            WHERE id = ? AND status = ?
            """,
            (BookingStatus.CONFIRMED.value, room_choice, _now_iso(), id, BookingStatus.PENDING.value),
        )
        row = conn.execute("SELECT * FROM booking_requests WHERE id = ?", (id,)).fetchone()
        return _row_to_request(row)


def cancel_booking_request(id: int, database_path: str | Path | None = None) -> BookingRequest | None:
    init_db(database_path)
    with connect(database_path) as conn:
        conn.execute(
            "UPDATE booking_requests SET status = ?, updated_at = ? WHERE id = ?",
            (BookingStatus.CANCELLED.value, _now_iso(), id),
        )
        row = conn.execute("SELECT * FROM booking_requests WHERE id = ?", (id,)).fetchone()
        return _row_to_request(row)


def get_confirmed_request_for_booking_window(database_path: str | Path | None = None) -> BookingRequest | None:
    init_db(database_path)
    with connect(database_path) as conn:
        row = conn.execute(
            """
            SELECT * FROM booking_requests
            WHERE status = ?
            ORDER BY created_at ASC, id ASC
            LIMIT 1
            """,
            (BookingStatus.CONFIRMED.value,),
        ).fetchone()
        return _row_to_request(row)


def mark_booked(id: int, screenshot_path: str, database_path: str | Path | None = None) -> BookingRequest | None:
    init_db(database_path)
    with connect(database_path) as conn:
        conn.execute(
            """
            UPDATE booking_requests
            SET status = ?, screenshot_path = ?, error_message = NULL, updated_at = ?
            WHERE id = ?
            """,
            (BookingStatus.BOOKED.value, screenshot_path, _now_iso(), id),
        )
        row = conn.execute("SELECT * FROM booking_requests WHERE id = ?", (id,)).fetchone()
        return _row_to_request(row)


def mark_failed(
    id: int,
    error_message: str,
    screenshot_path: str | None = None,
    database_path: str | Path | None = None,
) -> BookingRequest | None:
    init_db(database_path)
    with connect(database_path) as conn:
        conn.execute(
            """
            UPDATE booking_requests
            SET status = ?, error_message = ?, screenshot_path = COALESCE(?, screenshot_path), updated_at = ?
            WHERE id = ?
            """,
            (BookingStatus.FAILED.value, error_message, screenshot_path, _now_iso(), id),
        )
        row = conn.execute("SELECT * FROM booking_requests WHERE id = ?", (id,)).fetchone()
        return _row_to_request(row)

