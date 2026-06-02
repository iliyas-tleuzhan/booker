from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app import calendar_client, db, telegram_bot
from app.booking_browser import book_room
from app.config import settings
from app.slot_picker import find_free_slots, pick_best_slot


logger = logging.getLogger(__name__)


def daily_planner_job(target_offset_days: int | None = None) -> None:
    tz = ZoneInfo(settings.timezone)
    offset_days = settings.target_booking_offset_days if target_offset_days is None else target_offset_days
    target_date = datetime.now(tz).date() + timedelta(days=offset_days)
    busy_blocks = calendar_client.get_busy_blocks(target_date)
    slots = find_free_slots(
        busy_blocks,
        target_date,
        duration_minutes=settings.default_slot_duration_minutes,
    )
    best = pick_best_slot(slots)
    if best is None:
        telegram_bot.send_message(f"No free {settings.default_slot_duration_minutes}-minute slot found for {target_date}.")
        return

    booking_start = best.start
    booking_end = min(best.end, booking_start + timedelta(minutes=settings.default_slot_duration_minutes))
    text = (
        f"I found this booking slot for {target_date}: "
        f"{booking_start:%H:%M}-{booking_end:%H:%M}. "
        "Reply `yes` if the time is good, `no` to cancel, or send a different time like `14:00-16:00`. "
        "After that I will ask which library/facility and room you want. "
        f"I will wait until {settings.booking_hour:02d}:{settings.booking_minute:02d} tomorrow before trying to book it."
    )
    message_id = telegram_bot.send_message(text)
    request = db.create_booking_request(target_date, booking_start, booking_end, telegram_message_id=message_id)
    logger.info("Created booking request %s after Telegram message %s", request.id, message_id)


def _booking_target_date(now: datetime | None = None) -> date:
    tz = ZoneInfo(settings.timezone)
    current = now or datetime.now(tz)
    booking_offset_days = max(settings.target_booking_offset_days - 1, 0)
    return current.date() + timedelta(days=booking_offset_days)


def poll_telegram_replies_job() -> None:
    telegram_bot.poll_replies(timeout=0)


def midnight_booking_job(dry_run: bool | None = None) -> None:
    poll_telegram_replies_job()
    tz = ZoneInfo(settings.timezone)
    current_date = datetime.now(tz).date()
    request = db.get_confirmed_request_for_booking_window(min_target_date=current_date)
    if request is None:
        logger.info("No confirmed booking request found for %s or later", current_date)
        return

    result = book_room(request, dry_run=settings.dry_run if dry_run is None else dry_run)
    if result.success and result.status == "dry_run_ready":
        caption = "Dry-run booking flow reached the ready-to-submit page. No live booking was submitted."
    elif result.success:
        db.mark_booked(request.id, result.screenshot_path or "")
        caption = f"Booking flow finished with status: {result.status}"
    else:
        db.mark_failed(request.id, result.error_message or "Unknown booking error", result.screenshot_path)
        caption = f"Booking failed: {result.error_message}"

    if result.screenshot_path:
        telegram_bot.send_photo(result.screenshot_path, caption=caption)
    else:
        telegram_bot.send_message(caption)


def run_scheduler() -> None:
    logging.basicConfig(level=logging.INFO)
    scheduler = BlockingScheduler(timezone=settings.timezone)
    scheduler.add_job(daily_planner_job, "cron", hour=settings.planner_hour, minute=settings.planner_minute)
    scheduler.add_job(midnight_booking_job, "cron", hour=settings.booking_hour, minute=settings.booking_minute)
    scheduler.add_job(poll_telegram_replies_job, "interval", seconds=60, id="poll_telegram_replies")
    logger.info("Scheduler started")
    scheduler.start()
