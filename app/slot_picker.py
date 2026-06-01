from __future__ import annotations

from datetime import date, datetime, time, timedelta

from app.models import BusyBlock, FreeSlot


def _parse_time(value: str) -> time:
    hour, minute = value.split(":", maxsplit=1)
    return time(hour=int(hour), minute=int(minute))


def _merge_busy_blocks(busy_blocks: list[BusyBlock], window_start: datetime, window_end: datetime) -> list[BusyBlock]:
    clipped: list[BusyBlock] = []
    for block in sorted(busy_blocks, key=lambda item: item.start):
        start = max(block.start, window_start)
        end = min(block.end, window_end)
        if start < end:
            clipped.append(BusyBlock(start=start, end=end))

    merged: list[BusyBlock] = []
    for block in clipped:
        if not merged or block.start > merged[-1].end:
            merged.append(block)
            continue
        previous = merged[-1]
        merged[-1] = BusyBlock(start=previous.start, end=max(previous.end, block.end))
    return merged


def find_free_slots(
    busy_blocks: list[BusyBlock],
    date: date,
    day_start: str = "08:00",
    day_end: str = "23:00",
    duration_minutes: int = 120,
) -> list[FreeSlot]:
    window_start = datetime.combine(date, _parse_time(day_start))
    window_end = datetime.combine(date, _parse_time(day_end))
    if window_start >= window_end:
        raise ValueError("day_start must be before day_end")

    minimum_duration = timedelta(minutes=duration_minutes)
    merged_busy = _merge_busy_blocks(busy_blocks, window_start, window_end)

    free_slots: list[FreeSlot] = []
    cursor = window_start
    for block in merged_busy:
        if block.start - cursor >= minimum_duration:
            free_slots.append(FreeSlot(start=cursor, end=block.start))
        cursor = max(cursor, block.end)

    if window_end - cursor >= minimum_duration:
        free_slots.append(FreeSlot(start=cursor, end=window_end))

    return free_slots


def rank_slots(slots: list[FreeSlot]) -> list[FreeSlot]:
    def score(slot: FreeSlot) -> tuple[int, int, int, datetime]:
        starts_after_classes = 0 if slot.start.time() >= time(15, 0) else 1
        duration_delta = abs(slot.duration_minutes - 120)
        late_penalty = max(0, slot.start.hour - 19) * 60 + slot.start.minute
        return (starts_after_classes, duration_delta, late_penalty, slot.start)

    return sorted(slots, key=score)


def pick_best_slot(slots: list[FreeSlot]) -> FreeSlot | None:
    ranked = rank_slots(slots)
    return ranked[0] if ranked else None

