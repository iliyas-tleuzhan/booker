from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from app.config import settings
from app.models import BookingRequest, BookingResult


logger = logging.getLogger(__name__)


def _screenshot_path(prefix: str, request_id: int | None = None) -> Path:
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"-request-{request_id}" if request_id is not None else ""
    return settings.screenshot_dir / f"{prefix}{suffix}-{stamp}.png"


def save_auth_state_manual_login() -> None:
    if not settings.hkul_booking_url:
        raise ValueError("HKUL_BOOKING_URL is required")
    settings.playwright_auth_state_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(settings.hkul_booking_url, wait_until="domcontentloaded", timeout=60_000)
        input("Log in to HKUL in the opened browser, then press Enter here to save auth state...")
        context.storage_state(path=str(settings.playwright_auth_state_path))
        browser.close()


def book_room(request: BookingRequest, dry_run: bool = True) -> BookingResult:
    if not settings.hkul_booking_url:
        return BookingResult(success=False, status="failed", error_message="HKUL_BOOKING_URL is required")
    if not settings.playwright_auth_state_path.exists():
        return BookingResult(
            success=False,
            status="failed",
            error_message=f"Missing Playwright auth state: {settings.playwright_auth_state_path}",
        )

    screenshot_path: Path | None = None
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(storage_state=str(settings.playwright_auth_state_path))
            page = context.new_page()
            page.set_default_timeout(15_000)
            page.goto(settings.hkul_booking_url, wait_until="domcontentloaded", timeout=60_000)
            screenshot_path = _screenshot_path("opened", request.id)
            page.screenshot(path=str(screenshot_path), full_page=True)

            # TODO: Inspect the HKUL booking page and replace these placeholders.
            # Example selectors below are intentionally not assumed to be correct.
            # page.locator("TODO_DATE_INPUT_SELECTOR").fill(request.target_date.isoformat())
            # page.locator("TODO_START_TIME_SELECTOR").select_option(request.start_time.strftime("%H:%M"))
            # page.locator("TODO_END_TIME_SELECTOR").select_option(request.end_time.strftime("%H:%M"))
            # if request.room_choice and request.room_choice != "any":
            #     page.locator("TODO_ROOM_SELECTOR").fill(request.room_choice)
            #
            # Before any live submission, assert visible page text clearly matches:
            # - request.target_date
            # - request.start_time / request.end_time
            # - selected room/facility, unless room_choice == "any"

            ready_path = _screenshot_path("ready-to-submit", request.id)
            page.screenshot(path=str(ready_path), full_page=True)
            screenshot_path = ready_path

            if dry_run:
                browser.close()
                return BookingResult(
                    success=True,
                    status="dry_run_ready",
                    screenshot_path=str(screenshot_path),
                )

            raise RuntimeError(
                "Live booking selectors are TODO placeholders. Inspect the HKUL DOM, replace selectors, "
                "and add visible-detail verification before enabling final submit."
            )
    except (PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
        logger.exception("Booking attempt failed")
        return BookingResult(
            success=False,
            status="failed",
            screenshot_path=str(screenshot_path) if screenshot_path else None,
            error_message=str(exc),
        )

