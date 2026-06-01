from __future__ import annotations

import argparse
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app import calendar_client, db, telegram_bot
from app.booking_browser import book_room, save_auth_state_manual_login
from app.config import settings
from app.scheduler import daily_planner_job, midnight_booking_job, run_scheduler


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def _test_calendar() -> None:
    target_date = datetime.now(ZoneInfo(settings.timezone)).date() + timedelta(days=settings.target_booking_offset_days)
    busy = calendar_client.get_busy_blocks(target_date)
    print(f"Found {len(busy)} busy blocks for {target_date}:")
    for block in busy:
        print(f"- {block.start:%Y-%m-%d %H:%M} to {block.end:%H:%M}")


def _book_now(dry_run: bool) -> None:
    request = db.get_confirmed_request_for_booking_window()
    if request is None:
        raise SystemExit("No confirmed booking request found. Confirm a pending request first.")
    result = book_room(request, dry_run=dry_run)
    print(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="HKU study room booking assistant")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init-db")
    sub.add_parser("login-hkul")
    sub.add_parser("plan-now")
    book_now = sub.add_parser("book-now")
    mode = book_now.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--live", action="store_true")
    sub.add_parser("run")
    sub.add_parser("test-telegram")
    sub.add_parser("test-calendar")

    args = parser.parse_args()
    _configure_logging()

    if args.command == "init-db":
        db.init_db()
        print(f"Initialized database at {settings.database_path}")
    elif args.command == "login-hkul":
        save_auth_state_manual_login()
        print(f"Saved auth state to {settings.playwright_auth_state_path}")
    elif args.command == "plan-now":
        daily_planner_job()
    elif args.command == "book-now":
        _book_now(dry_run=args.dry_run)
    elif args.command == "run":
        run_scheduler()
    elif args.command == "test-telegram":
        message_id = telegram_bot.send_message("HKU booking agent Telegram test message.")
        print(f"Sent Telegram message id: {message_id}")
    elif args.command == "test-calendar":
        _test_calendar()


if __name__ == "__main__":
    main()

