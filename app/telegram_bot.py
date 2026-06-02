from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import requests

from app import db
from app.config import settings


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ParsedReply:
    action: str
    room_choice: str | None = None


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


def poll_replies(offset: int | None = None, timeout: int = 10) -> int | None:
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
        parsed = parse_user_reply(text)
        if parsed.action == "confirm" and parsed.room_choice:
            db.confirm_booking_request(pending.id, parsed.room_choice)
            send_message(f"Confirmed. I will try booking {parsed.room_choice} for request #{pending.id}.")
        elif parsed.action == "cancel":
            db.cancel_booking_request(pending.id)
            send_message(f"Cancelled booking request #{pending.id}.")
        else:
            send_message("I did not understand that reply. Please send `room 5`, `any`, `no`, or `cancel`.")

    return next_offset
