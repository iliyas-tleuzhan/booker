from datetime import date, datetime

from app.models import BusyBlock, FreeSlot
from app.slot_picker import find_free_slots, pick_best_slot, rank_slots


def dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def test_find_free_slots_merges_overlapping_busy_blocks() -> None:
    target = date(2026, 6, 3)
    busy = [
        BusyBlock(start=dt("2026-06-03T09:00:00"), end=dt("2026-06-03T10:30:00")),
        BusyBlock(start=dt("2026-06-03T10:00:00"), end=dt("2026-06-03T11:00:00")),
        BusyBlock(start=dt("2026-06-03T15:00:00"), end=dt("2026-06-03T16:00:00")),
    ]

    slots = find_free_slots(busy, target, duration_minutes=120)

    assert [(slot.start.time().isoformat(timespec="minutes"), slot.end.time().isoformat(timespec="minutes")) for slot in slots] == [
        ("11:00", "15:00"),
        ("16:00", "23:00"),
    ]


def test_find_free_slots_respects_day_window_and_duration() -> None:
    target = date(2026, 6, 3)
    busy = [
        BusyBlock(start=dt("2026-06-03T07:00:00"), end=dt("2026-06-03T09:00:00")),
        BusyBlock(start=dt("2026-06-03T21:30:00"), end=dt("2026-06-03T23:30:00")),
    ]

    slots = find_free_slots(busy, target, day_start="08:00", day_end="23:00", duration_minutes=120)

    assert len(slots) == 1
    assert slots[0].start == dt("2026-06-03T09:00:00")
    assert slots[0].end == dt("2026-06-03T21:30:00")


def test_rank_slots_prefers_after_1500_and_not_too_late() -> None:
    slots = [
        FreeSlot(start=dt("2026-06-03T08:00:00"), end=dt("2026-06-03T10:00:00")),
        FreeSlot(start=dt("2026-06-03T20:00:00"), end=dt("2026-06-03T22:00:00")),
        FreeSlot(start=dt("2026-06-03T15:30:00"), end=dt("2026-06-03T17:30:00")),
    ]
    ranked = rank_slots(slots)

    assert ranked[0].start == dt("2026-06-03T15:30:00")
    assert pick_best_slot(slots) == ranked[0]
