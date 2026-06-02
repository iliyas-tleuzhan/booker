from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, time
from pathlib import Path

import requests

from app import db
from app.config import settings


logger = logging.getLogger(__name__)
TELEGRAM_UPDATE_OFFSET_KEY = "telegram_update_offset"


@dataclass(frozen=True)
class ParsedReply:
    action: str
    room_choice: str | None = None


AFFIRMATIVE_REPLIES = {
    "yes",
    "y",
    "ok",
    "okay",
    "correct",
    "that is correct",
    "thats correct",
    "confirm",
    "confirmed",
    "sure",
    "good",
    "looks good",
}
LIBRARY_ALIASES = {
    "chi wah": "Chi Wah Learning Commons",
    "chiwah": "Chi Wah Learning Commons",
    "chi wah learning commons": "Chi Wah Learning Commons",
    "learning commons": "Chi Wah Learning Commons",
    "main": "Main Library",
    "main lib": "Main Library",
    "main library": "Main Library",
    "dental": "Dental Libary",
    "dental library": "Dental Libary",
    "medicine": "Faculty of Medicine",
    "faculty of medicine": "Faculty of Medicine",
    "law": "Law Library",
    "law lib": "Law Library",
    "law library": "Law Library",
    "medical": "Medical Library",
    "medical library": "Medical Library",
    "music": "Music Library",
    "music library": "Music Library",
    "engineering": "Research Student Centre (Faculty of Engineering)",
    "research student centre": "Research Student Centre (Faculty of Engineering)",
    "history gallery": "The University of Hong Kong History Gallery",
}


def _api_url(method: str) -> str:
    if not settings.telegram_bot_token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    return f"https://api.telegram.org/bot{settings.telegram_bot_token}/{method}"


def send_message(text: str) -> int | None:
    response = requests.post(
        _api_url("sendMessage"),
        json={"chat_id": settings.telegram_chat_id, "text": text},
        timeout=20,
    )
    response.raise_for_status()
    result = response.json()["result"]
    return result.get("message_id")


def send_photo(path: str | Path, caption: str | None = None) -> int | None:
    with Path(path).open("rb") as handle:
        response = requests.post(
            _api_url("sendPhoto"),
            data={"chat_id": settings.telegram_chat_id, "caption": caption or ""},
            files={"photo": handle},
            timeout=60,
        )
    response.raise_for_status()
    result = response.json()["result"]
    return result.get("message_id")


def parse_user_reply(text: str) -> ParsedReply:
    normalized = " ".join(text.strip().lower().split())
    if normalized in {"no", "cancel", "stop"}:
        return ParsedReply(action="cancel")
    if normalized == "any":
        return ParsedReply(action="confirm", room_choice="any")
    if normalized.startswith("yes "):
        normalized = normalized.removeprefix("yes ").strip()
    if normalized.startswith("room "):
        return ParsedReply(action="confirm", room_choice=normalized)
    return ParsedReply(action="unknown")


def _normalize(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9: -]+", " ", text.lower()).split())


def _is_affirmative(text: str) -> bool:
    return _normalize(text) in AFFIRMATIVE_REPLIES


def _parse_time_range(text: str, target_date) -> tuple[datetime, datetime] | None:
    match = re.search(r"(\d{1,2})(?::(\d{2}))?\s*(?:-|–|to)\s*(\d{1,2})(?::(\d{2}))?", text.lower())
    if not match:
        return None
    start_hour = int(match.group(1))
    start_minute = int(match.group(2) or 0)
    end_hour = int(match.group(3))
    end_minute = int(match.group(4) or 0)
    if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23 and 0 <= start_minute <= 59 and 0 <= end_minute <= 59):
        return None

    start = datetime.combine(target_date, time(start_hour, start_minute))
    end = datetime.combine(target_date, time(end_hour, end_minute))
    if end <= start:
        return None
    return start, end


def _parse_library(text: str) -> str | None:
    normalized = _normalize(text)
    if normalized in LIBRARY_ALIASES:
        return LIBRARY_ALIASES[normalized]
    for alias, library in LIBRARY_ALIASES.items():
        if alias in normalized:
            return library
    return None


def _parse_room(text: str) -> str | None:
    normalized = _normalize(text)
    if normalized == "any":
        return "any"
    match = re.search(r"\d+", normalized)
    if not match:
        return None
    return f"room {match.group(0)}"


def _summary(request) -> str:
    library = request.library_choice or "unspecified library"
    room = request.room_choice or "unspecified room"
    return f"{request.target_date} {request.start_time:%H:%M}-{request.end_time:%H:%M}, {library}, {room}"


def _ask_library(request) -> None:
    db.update_booking_request_details(request.id, conversation_state="awaiting_library")
    send_message("Ok, which library/facility do you want? Examples: Chi Wah, Main Library, Law Library, Music Library.")


def _handle_pending_reply(request, text: str) -> None:
    normalized = _normalize(text)

    state = request.conversation_state or "awaiting_initial"

    if state == "awaiting_initial":
        time_range = _parse_time_range(text, request.target_date)
        if time_range:
            db.update_booking_request_details(
                request.id,
                start_time=time_range[0],
                end_time=time_range[1],
                conversation_state="awaiting_library",
            )
            send_message(f"Ok, I changed the time to {time_range[0]:%H:%M}-{time_range[1]:%H:%M}. Which library/facility do you want?")
            return
        if normalized in {"no", "cancel", "stop"}:
            db.cancel_booking_request(request.id)
            send_message(f"Cancelled booking request #{request.id}.")
            return
        library = _parse_library(text)
        if library:
            updated = db.update_booking_request_details(request.id, library_choice=library, facility_type="Study Room", conversation_state="awaiting_room")
            send_message(f"Ok, {updated.library_choice}. Which room should I choose?")
            return
        room = _parse_room(text)
        if room:
            db.update_booking_request_details(request.id, room_choice=room, conversation_state="awaiting_library")
            send_message(f"Ok, {room}. Which library/facility do you want?")
            return
        if _is_affirmative(text) or normalized in {"any"}:
            _ask_library(request)
            return
        send_message("Please reply `yes`, `no`, a time like `14:00-16:00`, or a library name.")
        return

    if normalized in {"no", "cancel", "stop"}:
        db.cancel_booking_request(request.id)
        send_message(f"Cancelled booking request #{request.id}.")
        return

    if state == "awaiting_library":
        library = _parse_library(text)
        if not library:
            send_message("I did not recognize that library. Try `Chi Wah`, `Main Library`, `Law Library`, `Music Library`, or another listed library name.")
            return
        updated = db.update_booking_request_details(request.id, library_choice=library, facility_type="Study Room", conversation_state="awaiting_room")
        send_message(f"Ok, {updated.library_choice}. Which room should I choose? You can send `room 6`, `6`, or `any`.")
        return

    if state == "awaiting_room":
        room = _parse_room(text)
        if not room:
            send_message("Please send a room number like `room 6`, `6`, or `any`.")
            return
        updated = db.update_booking_request_details(request.id, room_choice=room, conversation_state="awaiting_confirmation")
        send_message(f"{_summary(updated)}. Is that correct?")
        return

    if state == "awaiting_confirmation":
        if _is_affirmative(text):
            room_choice = request.room_choice or "any"
            db.confirm_booking_request(request.id, room_choice)
            send_message(f"Confirmed. I will try booking {_summary(request)} when it becomes available.")
            return
        if normalized.startswith("no"):
            db.update_booking_request_details(request.id, conversation_state="awaiting_initial")
            send_message("Ok, send the corrected time like `14:00-16:00`, or send `cancel`.")
            return
        send_message("Please reply `yes` to confirm, `no` to revise, or `cancel`.")
        return

    send_message("I lost track of the booking conversation. Please send `cancel` and run `plan-now` again.")


def poll_replies(offset: int | None = None, timeout: int = 10) -> int | None:
    stored_offset = db.get_app_state(TELEGRAM_UPDATE_OFFSET_KEY)
    if offset is None and stored_offset is not None:
        offset = int(stored_offset)

    params: dict[str, int] = {"timeout": timeout}
    if offset is not None:
        params["offset"] = offset
    response = requests.get(
        _api_url("getUpdates"),
        params=params,
        timeout=20,
    )
    response.raise_for_status()
    updates = response.json().get("result", [])
    next_offset = offset

    for update in updates:
        next_offset = update["update_id"] + 1
        message = update.get("message", {})
        if str(message.get("chat", {}).get("id")) != str(settings.telegram_chat_id):
            continue
        pending = db.get_latest_pending_request()
        if not pending:
            logger.info("Ignoring Telegram reply because there is no pending request")
            continue
        if pending.telegram_message_id and message.get("message_id", 0) <= pending.telegram_message_id:
            logger.info("Ignoring Telegram reply older than pending request prompt")
            continue
        text = message.get("text", "")
        _handle_pending_reply(pending, text)

    if next_offset is not None:
        db.set_app_state(TELEGRAM_UPDATE_OFFSET_KEY, str(next_offset))

    return next_offset
