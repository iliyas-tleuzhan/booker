from datetime import date

from app.telegram_bot import _is_affirmative, _is_cancel, _parse_library, _parse_room, _parse_time_range


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
