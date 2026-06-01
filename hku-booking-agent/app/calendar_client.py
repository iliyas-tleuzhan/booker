from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from app.config import settings
from app.models import BusyBlock


SCOPES = ["https://www.googleapis.com/auth/calendar"]
CREDENTIALS_PATH = Path("credentials.json")
TOKEN_PATH = Path("token.json")


def _get_credentials() -> Credentials:
    """Load Google OAuth credentials.

    Put the OAuth desktop client file from Google Cloud Console at
    ./credentials.json. The generated access/refresh token is stored at
    ./token.json. Both files are intentionally gitignored.
    """
    creds: Credentials | None = None
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(
                "Missing credentials.json. Create an OAuth desktop client in Google Cloud Console "
                "and save it as credentials.json in the project root."
            )
        flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
        creds = flow.run_local_server(port=0)

    TOKEN_PATH.write_text(creds.to_json(), encoding="utf-8")
    return creds


def _service():
    return build("calendar", "v3", credentials=_get_credentials())


def _parse_google_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def get_busy_blocks(target_date: date) -> list[BusyBlock]:
    tz = ZoneInfo(settings.timezone)
    start = datetime.combine(target_date, time.min, tzinfo=tz)
    end = start + timedelta(days=1)

    events = (
        _service()
        .events()
        .list(
            calendarId=settings.google_calendar_id,
            timeMin=start.isoformat(),
            timeMax=end.isoformat(),
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
        .get("items", [])
    )

    busy: list[BusyBlock] = []
    for event in events:
        if event.get("transparency") == "transparent":
            continue
        start_value = event["start"].get("dateTime") or event["start"].get("date")
        end_value = event["end"].get("dateTime") or event["end"].get("date")
        if "T" not in start_value:
            busy.append(BusyBlock(start=start.replace(tzinfo=None), end=end.replace(tzinfo=None)))
            continue
        busy.append(
            BusyBlock(
                start=_parse_google_datetime(start_value).astimezone(tz).replace(tzinfo=None),
                end=_parse_google_datetime(end_value).astimezone(tz).replace(tzinfo=None),
            )
        )
    return busy


def create_calendar_event(title: str, start: datetime, end: datetime, description: str | None = None) -> dict:
    event = {
        "summary": title,
        "description": description or "",
        "start": {"dateTime": start.isoformat(), "timeZone": settings.timezone},
        "end": {"dateTime": end.isoformat(), "timeZone": settings.timezone},
    }
    return _service().events().insert(calendarId=settings.google_calendar_id, body=event).execute()
