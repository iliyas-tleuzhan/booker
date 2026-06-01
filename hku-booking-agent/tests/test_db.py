from datetime import date, datetime

from app import db
from app.models import BookingStatus


def test_booking_request_lifecycle(tmp_path) -> None:
    database_path = tmp_path / "bookings.db"
    db.init_db(database_path)

    request = db.create_booking_request(
        target_date=date(2026, 6, 3),
        start_time=datetime(2026, 6, 3, 16, 0),
        end_time=datetime(2026, 6, 3, 18, 0),
        database_path=database_path,
    )

    assert request.status == BookingStatus.PENDING
    pending = db.get_latest_pending_request(database_path)
    assert pending is not None
    assert pending.id == request.id

    confirmed = db.confirm_booking_request(request.id, "room 5", database_path)
    assert confirmed is not None
    assert confirmed.status == BookingStatus.CONFIRMED
    assert confirmed.room_choice == "room 5"

    next_request = db.get_confirmed_request_for_booking_window(database_path)
    assert next_request is not None
    assert next_request.id == request.id

    booked = db.mark_booked(request.id, "data/screenshots/final.png", database_path)
    assert booked is not None
    assert booked.status == BookingStatus.BOOKED
    assert booked.screenshot_path == "data/screenshots/final.png"


def test_cancel_and_mark_failed(tmp_path) -> None:
    database_path = tmp_path / "bookings.db"
    request = db.create_booking_request(
        target_date=date(2026, 6, 3),
        start_time=datetime(2026, 6, 3, 16, 0),
        end_time=datetime(2026, 6, 3, 18, 0),
        database_path=database_path,
    )

    cancelled = db.cancel_booking_request(request.id, database_path)
    assert cancelled is not None
    assert cancelled.status == BookingStatus.CANCELLED

    failed = db.mark_failed(request.id, "blocked by login", "error.png", database_path)
    assert failed is not None
    assert failed.status == BookingStatus.FAILED
    assert failed.error_message == "blocked by login"
    assert failed.screenshot_path == "error.png"

