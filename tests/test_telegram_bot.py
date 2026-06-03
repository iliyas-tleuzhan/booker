from datetime import date, datetime

from app.models import BookingRequest, BookingStatus
from app.telegram_bot import (
    _is_affirmative,
    _is_cancel,
    _parse_library,
    _parse_room,
    _parse_time_range,
    format_booking_details,
    format_planner_prompt,
)


def test_parse_time_revision_from_negative_reply() -> None:
    parsed = _parse_time_range("no, choose 14:00-16:00", date(2026, 6, 4))

    assert parsed is not None
    assert parsed[0].isoformat() == "2026-06-04T14:00:00"
    assert parsed[1].isoformat() == "2026-06-04T16:00:00"


def test_parse_library_aliases_case_insensitively() -> None:
    assert _parse_library("CHIWAH") == "Chi Wah Learning Commons"
    assert _parse_library("CWL") == "Chi Wah Learning Commons"
    assert _parse_library("Main Lib") == "Main Library"
    assert _parse_library("music lib") == "Music Library"


def test_parse_room_number_variants() -> None:
    assert _parse_room("room 6") == "room 6"
    assert _parse_room("6") == "room 6"
    assert _parse_room("rm 6") == "room 6"
    assert _parse_room("any room") == "any"


def test_parse_more_conversation_vocabulary() -> None:
    assert _is_affirmative("book it")
    assert _is_affirmative("sounds good")
    assert _is_cancel("don't book")
    assert _is_cancel("never mind")


def test_poll_replies_uses_stored_offset(monkeypatch, tmp_path) -> None:
    from app import db
    from app import telegram_bot

    db.set_app_state(telegram_bot.TELEGRAM_UPDATE_OFFSET_KEY, "99", tmp_path / "bookings.db")
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"result": []}

    monkeypatch.setattr(telegram_bot.db, "get_app_state", lambda key: "99")
    monkeypatch.setattr(telegram_bot.db, "set_app_state", lambda key, value: captured.update({key: value}))
    monkeypatch.setattr(telegram_bot.requests, "get", lambda url, params, timeout: captured.update({"params": params}) or Response())

    assert telegram_bot.poll_replies(timeout=0) == 99
    assert captured["params"]["offset"] == 99


def test_format_planner_prompt_is_readable() -> None:
    text = format_planner_prompt(
        date(2026, 6, 2),
        datetime(2026, 6, 2, 8, 0),
        datetime(2026, 6, 2, 10, 0),
    )

    assert "I found this booking slot for *2026-06-02:*" in text
    assert "from 08:00 - to 10:00" in text
    assert "\n\nReply `yes`" in text


def test_format_booking_details_is_readable() -> None:
    request = BookingRequest(
        id=1,
        target_date=date(2026, 6, 2),
        start_time=datetime(2026, 6, 2, 8, 0),
        end_time=datetime(2026, 6, 2, 10, 0),
        room_choice="room 5",
        library_choice="Chi Wah Learning Commons",
        facility_type="Study Room",
        conversation_state=None,
        status=BookingStatus.CONFIRMED,
        telegram_message_id=1,
        screenshot_path=None,
        error_message=None,
        created_at=datetime(2026, 6, 1, 23, 30),
        updated_at=datetime(2026, 6, 1, 23, 35),
    )

    assert format_booking_details(request) == (
        "Date:     *2026-06-02*\n"
        "Time:     08:00 - 10:00\n"
        "Facility: Chi Wah Learning Commons\n"
        "Room:     Room 5"
    )
