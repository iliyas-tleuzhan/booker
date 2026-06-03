from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urljoin

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import Page
from playwright.sync_api import sync_playwright

from app.config import settings
from app.models import BookingRequest, BookingResult


logger = logging.getLogger(__name__)


NEW_BOOKING_PATH = "/Secure/NewBooking.aspx"
DEFAULT_LIBRARY = "Chi Wah Learning Commons"
DEFAULT_FACILITY_TYPE = "Study Room"


def _screenshot_path(prefix: str, request_id: int | None = None) -> Path:
    settings.screenshot_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"-request-{request_id}" if request_id is not None else ""
    return settings.screenshot_dir / f"{prefix}{suffix}-{stamp}.png"


def _new_booking_url() -> str:
    return urljoin(settings.hkul_booking_url, NEW_BOOKING_PATH)


def _assert_booking_form_loaded(page: Page) -> None:
    if page.locator("#main_ddlLibrary").count() > 0:
        return
    body_text = page.locator("body").inner_text(timeout=5_000)
    if "HKUL Authentication" in body_text or "Registered library users only" in body_text:
        raise RuntimeError(
            "HKUL login is required or the saved session expired. Run `python -m app.main login-hkul`, "
            "complete the HKUL login in the opened browser, then try again."
        )
    raise RuntimeError("HKUL booking form did not load; #main_ddlLibrary was not found.")


def _wait_for_option_value(page: Page, selector: str, value: str) -> None:
    page.wait_for_function(
        """({ selector, value }) => {
            const element = document.querySelector(selector);
            return element && Array.from(element.options).some(option => option.value === value);
        }""",
        arg={"selector": selector, "value": value},
    )


def _select_option(page: Page, selector: str, value: str) -> None:
    try:
        _wait_for_option_value(page, selector, value)
    except PlaywrightTimeoutError as exc:
        options = page.locator(selector).evaluate("el => Array.from(el.options).map(option => option.value || option.text.trim())")
        raise RuntimeError(f"Option {value!r} is not available for {selector}. Available options: {options}") from exc
    page.select_option(selector, value)
    page.wait_for_timeout(1_000)


def _normalize_option_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


def _option_value_by_text(page: Page, selector: str, expected_text: str) -> str:
    expected = _normalize_option_text(expected_text)
    options = page.locator(selector).evaluate(
        "el => Array.from(el.options).map(option => ({ value: option.value, text: option.text.trim() }))"
    )
    for option in options:
        if option["value"] and _normalize_option_text(option["text"]) == expected:
            return option["value"]
    for option in options:
        if option["value"] and expected in _normalize_option_text(option["text"]):
            return option["value"]
    raise RuntimeError(f"Could not find option {expected_text!r} for {selector}. Available options: {options}")


def _facility_value(page: Page, room_choice: str | None) -> str:
    options = page.locator("#main_ddlFacility").evaluate(
        "el => Array.from(el.options).map(option => ({ value: option.value, text: option.text.trim() }))"
    )
    available = [option for option in options if option["value"]]
    if not available:
        raise RuntimeError("No facilities are available for the selected library and facility type.")

    if not room_choice or room_choice == "any":
        return available[0]["value"]

    match = re.search(r"\d+", room_choice)
    if not match:
        raise RuntimeError(f"Unsupported room choice: {room_choice!r}. Use a room number such as `room 5`.")

    room_number = match.group(0)
    for option in available:
        if re.search(rf"\b{re.escape(room_number)}\b", option["text"]):
            return option["value"]

    available_labels = [option["text"] for option in available]
    raise RuntimeError(f"Could not find room {room_number}. Available facilities: {available_labels}")


def _session_values(request: BookingRequest) -> list[str]:
    start = request.start_time
    end = min(request.end_time, start + timedelta(minutes=settings.default_slot_duration_minutes))
    if end <= start:
        raise RuntimeError("Booking request end time must be after start time.")

    values: list[str] = []
    cursor = start
    while cursor < end:
        next_hour = min(cursor.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1), end)
        if cursor.minute != 0 or next_hour.minute not in {0, 45}:
            raise RuntimeError("HKUL booking sessions must align to listed hourly session checkboxes.")
        values.append(f"{cursor:%H%M}{next_hour:%H%M}")
        cursor = next_hour
    return values


def _check_session(page: Page, value: str) -> None:
    checkbox = page.locator(f"input[type='checkbox'][value='{value}']")
    if checkbox.count() == 0:
        raise RuntimeError(f"Requested session {value[:2]}:{value[2:4]}-{value[4:6]}:{value[6:]} is not available.")
    checkbox.check()


def _page_has_error(page: Page) -> str | None:
    body_text = " ".join(page.locator("body").inner_text(timeout=5_000).split())
    error_markers = ["error", "not available", "already booked", "cannot", "failed", "invalid"]
    lowered = body_text.lower()
    if any(marker in lowered for marker in error_markers):
        return body_text[:1_000]
    return None


def save_auth_state_manual_login() -> None:
    if not settings.hkul_booking_url:
        raise ValueError("HKUL_BOOKING_URL is required")
    settings.playwright_auth_state_path.parent.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(_new_booking_url(), wait_until="domcontentloaded", timeout=60_000)
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
            page.goto(_new_booking_url(), wait_until="domcontentloaded", timeout=60_000)
            screenshot_path = _screenshot_path("opened", request.id)
            page.screenshot(path=str(screenshot_path), full_page=True)
            _assert_booking_form_loaded(page)

            library_value = _option_value_by_text(page, "#main_ddlLibrary", request.library_choice or DEFAULT_LIBRARY)
            _select_option(page, "#main_ddlLibrary", library_value)
            type_value = _option_value_by_text(page, "#main_ddlType", request.facility_type or DEFAULT_FACILITY_TYPE)
            _select_option(page, "#main_ddlType", type_value)
            facility_value = _facility_value(page, request.room_choice)
            _select_option(page, "#main_ddlFacility", facility_value)
            _select_option(page, "#main_ddlDate", request.target_date.isoformat())

            for session_value in _session_values(request):
                _check_session(page, session_value)

            page.locator("#main_txtUserDescription").fill(f"Booking request #{request.id}")

            selected_facility = page.locator("#main_ddlFacility").evaluate("el => el.options[el.selectedIndex].text").strip()
            selected_date = page.locator("#main_ddlDate").input_value()
            if selected_date != request.target_date.isoformat():
                raise RuntimeError(f"Selected date mismatch: expected {request.target_date}, got {selected_date}")
            if request.room_choice != "any" and request.room_choice:
                expected_room = re.search(r"\d+", request.room_choice)
                if expected_room and expected_room.group(0) not in selected_facility:
                    raise RuntimeError(f"Selected room mismatch: expected {request.room_choice}, got {selected_facility}")

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

            page.locator("#main_btnSubmit").click()
            page.locator("#main_btnSubmitYes").wait_for(state="visible")
            confirm_path = _screenshot_path("confirm-submit", request.id)
            page.screenshot(path=str(confirm_path), full_page=True)
            screenshot_path = confirm_path

            page.locator("#main_btnSubmitYes").click()
            page.wait_for_load_state("networkidle", timeout=60_000)
            final_path = _screenshot_path("booked", request.id)
            page.screenshot(path=str(final_path), full_page=True)
            screenshot_path = final_path

            error_text = _page_has_error(page)
            if error_text:
                raise RuntimeError(f"HKUL returned an error after final submit: {error_text}")

            browser.close()
            return BookingResult(
                success=True,
                status="booked",
                screenshot_path=str(screenshot_path),
            )
    except (PlaywrightTimeoutError, PlaywrightError, RuntimeError) as exc:
        logger.exception("Booking attempt failed")
        return BookingResult(
            success=False,
            status="failed",
            screenshot_path=str(screenshot_path) if screenshot_path else None,
            error_message=str(exc),
        )
