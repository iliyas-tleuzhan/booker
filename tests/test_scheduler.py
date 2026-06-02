from datetime import datetime
from zoneinfo import ZoneInfo

from app.models import FreeSlot
from app import scheduler
from app.scheduler import _booking_target_date


def test_midnight_booking_targets_original_planned_date() -> None:
    now = datetime(2026, 6, 3, 0, 0, tzinfo=ZoneInfo("Asia/Hong_Kong"))

    assert _booking_target_date(now).isoformat() == "2026-06-04"


def test_daily_planner_uses_manual_target_offset(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 6, 2, 10, 0, tzinfo=tz)

    def fake_get_busy_blocks(target_date):
        captured["target_date"] = target_date
        return []

    def fake_find_free_slots(busy_blocks, target_date, duration_minutes):
        return [
            FreeSlot(
                start=datetime.combine(target_date, datetime.strptime("12:00", "%H:%M").time()),
                end=datetime.combine(target_date, datetime.strptime("14:00", "%H:%M").time()),
            )
        ]

    monkeypatch.setattr(scheduler, "datetime", FixedDatetime)
    monkeypatch.setattr(scheduler.calendar_client, "get_busy_blocks", fake_get_busy_blocks)
    monkeypatch.setattr(scheduler, "find_free_slots", fake_find_free_slots)
    monkeypatch.setattr(scheduler.telegram_bot, "send_message", lambda text: 123)
    monkeypatch.setattr(scheduler.db, "create_booking_request", lambda *args, **kwargs: type("Request", (), {"id": 1})())

    scheduler.daily_planner_job(target_offset_days=1)

    assert captured["target_date"].isoformat() == "2026-06-03"


def test_daily_planner_target_offset_handles_month_rollover(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FixedDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 5, 30, 10, 0, tzinfo=tz)

    def fake_find_free_slots(busy_blocks, target_date, duration_minutes):
        return [
            FreeSlot(
                start=datetime.combine(target_date, datetime.strptime("12:00", "%H:%M").time()),
                end=datetime.combine(target_date, datetime.strptime("14:00", "%H:%M").time()),
            )
        ]

    monkeypatch.setattr(scheduler, "datetime", FixedDatetime)
    monkeypatch.setattr(scheduler.calendar_client, "get_busy_blocks", lambda target_date: captured.setdefault("target_date", target_date) and [])
    monkeypatch.setattr(scheduler, "find_free_slots", fake_find_free_slots)
    monkeypatch.setattr(scheduler.telegram_bot, "send_message", lambda text: 123)
    monkeypatch.setattr(scheduler.db, "create_booking_request", lambda *args, **kwargs: type("Request", (), {"id": 1})())

    scheduler.daily_planner_job(target_offset_days=2)

    assert captured["target_date"].isoformat() == "2026-06-01"
