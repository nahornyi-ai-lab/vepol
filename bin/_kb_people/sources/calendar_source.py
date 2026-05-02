"""Google Calendar contact source."""

import json
import os
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from . import ContactSource

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
TOKEN_PATH = Path.home() / ".vepol" / "tokens" / "google-calendar.json"
CREDENTIALS_PATH = Path.home() / ".vepol" / "tokens" / "google-calendar-credentials.json"


def _get_creds(reauth: bool = False) -> Credentials:
    creds = None
    if not reauth and TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_PATH.exists():
                raise FileNotFoundError(
                    f"Google credentials not found at {CREDENTIALS_PATH}.\n"
                    "Download OAuth2 credentials from Google Cloud Console and save there."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_PATH),
                SCOPES,
                redirect_uri="urn:ietf:wg:oauth:2.0:oob",
            )
            # access_type=offline ensures refresh_token is returned (B1 fix)
            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent",
            )
        TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())
    return creds


def _get_authenticated_email(service) -> str:
    """Get the authenticated user's email to filter self-attendees (B2 fix)."""
    try:
        settings = service.settings().get(setting="format").execute()
        calendar = service.calendarList().get(calendarId="primary").execute()
        return calendar.get("id", "").lower()
    except Exception:
        return ""


class CalendarSource(ContactSource):
    def __init__(self, days_back: int = 30, reauth: bool = False):
        self.days_back = days_back
        self.reauth = reauth

    def get_contacts(self) -> list[dict]:
        from datetime import datetime, timedelta, timezone

        creds = _get_creds(self.reauth)
        service = build("calendar", "v3", credentials=creds)
        self_email = _get_authenticated_email(service)

        time_min = (datetime.now(timezone.utc) - timedelta(days=self.days_back)).isoformat()
        time_max = datetime.now(timezone.utc).isoformat()

        contacts = []
        page_token = None

        while True:
            events_result = service.events().list(
                calendarId="primary",
                timeMin=time_min,
                timeMax=time_max,
                singleEvents=True,
                orderBy="startTime",
                pageToken=page_token,
                maxResults=250,
            ).execute()

            for event in events_result.get("items", []):
                event_date = (event.get("start", {}).get("dateTime") or event.get("start", {}).get("date", ""))[:10]
                event_title = event.get("summary", "Calendar event")

                for attendee in event.get("attendees", []):
                    email = attendee.get("email", "").lower().strip()
                    name = attendee.get("displayName", "")

                    # B3: skip attendees without email (room resources etc.)
                    if not email:
                        continue

                    # B2: skip self
                    if email == self_email:
                        continue

                    # skip resource calendars
                    if "resource.calendar.google.com" in email:
                        continue

                    contacts.append({
                        "name": name or email.split("@")[0].replace(".", " ").title(),
                        "email": email,
                        "context": event_title,
                        "date": event_date,
                        "source_type": "calendar",
                    })

            page_token = events_result.get("nextPageToken")
            if not page_token:
                break

        return contacts
