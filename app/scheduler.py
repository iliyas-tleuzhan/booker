from __future__ import annotations

import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.blocking import BlockingScheduler

from app import calendar_client, db, telegram_bot
from app.booking_browser import book_room
from app.config import settings
from app.slot_picker import find_free_slots, pick_best_slot


logger = logging.getLogger(__name__)


def daily_planner_job() -> None:
    tz = ZoneInfo(settings.timezone)
    target_date = (datetime.now(tz).date() + timedelta(days=settings.target_booking_offset_days))
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

    text = (
        f"I found this free slot: {target_date} "
        f"{best.start:%H:%M}-{best.end:%H:%M}. "
        "Which room should I try booking? Reply with room number/name, `any`, or `no`."
    )
    message_id = telegram_bot.send_message(text)
    request = db.create_booking_request(target_date, best.start, best.end, telegram_message_id=message_id)
    logger.info("Created booking request %s after Telegram message %s", request.id, message_id)


def midnight_booking_job(dry_run: bool | None = None) -> None:
    request = db.get_confirmed_request_for_booking_window()
    if request is None:
        logger.info("No confirmed booking request found")
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
    logger.info("Scheduler started")
    scheduler.start()
