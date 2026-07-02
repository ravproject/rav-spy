"""
Calendar Client — Google Calendar integration.
Stores OAuth token in ~/.config/rav-spy/calendar_token.json

Dependencies: google-api-python-client, google-auth-httplib2, google-auth-oauthlib
"""
from pathlib import Path
from datetime import datetime, timedelta
from loguru import logger

CALENDAR_TOKEN_DIR = Path.home() / ".config" / "rav-spy"
CALENDAR_TOKEN_FILE = CALENDAR_TOKEN_DIR / "calendar_token.json"
CALENDAR_CRED_FILE = CALENDAR_TOKEN_DIR / "credentials.json"

def _get_calendar_service():
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
    except ImportError:
        return None, "Google API libraries not installed. Run: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib"

    SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]
    creds = None

    if CALENDAR_TOKEN_FILE.exists():
        try:
            creds = Credentials.from_authorized_user_file(str(CALENDAR_TOKEN_FILE), SCOPES)
        except Exception:
            pass

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception:
                pass
        else:
            return None, "Belum terautentikasi dengan Google. Jalankan setup calendar dulu."

        with open(CALENDAR_TOKEN_FILE, "w") as f:
            f.write(creds.to_json())

    try:
        service = build("calendar", "v3", credentials=creds)
        return service, None
    except Exception as e:
        return None, f"Gagal inisialisasi Calendar API: {e}"

def get_next_event() -> str:
    service, error = _get_calendar_service()
    if error:
        return error

    now = datetime.utcnow().isoformat() + "Z"
    try:
        events_result = service.events().list(
            calendarId="primary", timeMin=now,
            maxResults=5, singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        if not events:
            return "Tidak ada acara mendatang di Google Calendar."

        lines = ["Acara Google Calendar Mendatang:"]
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "Tanpa judul")
            link = event.get("hangoutLink", "")
            lines.append(f"  {start[:16]} - {summary}")
            if link:
                lines.append(f"    Meet: {link}")
        return "\n".join(lines)
    except Exception as e:
        return f"Gagal mengambil calendar: {e}"

def get_today_events() -> str:
    service, error = _get_calendar_service()
    if error:
        return error

    now = datetime.utcnow()
    end_of_day = now.replace(hour=23, minute=59, second=59)
    try:
        events_result = service.events().list(
            calendarId="primary",
            timeMin=now.isoformat() + "Z",
            timeMax=end_of_day.isoformat() + "Z",
            maxResults=10, singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        if not events:
            return "Tidak ada acara hari ini."

        lines = [f"Acara Hari Ini ({now.strftime('%d/%m/%Y')}):"]
        for event in events:
            start = event["start"].get("dateTime", event["start"].get("date"))
            summary = event.get("summary", "Tanpa judul")
            lines.append(f"  {start[11:16]} - {summary}")
        return "\n".join(lines)
    except Exception as e:
        return f"Gagal mengambil calendar: {e}"

def join_event(query: str = None) -> str:
    service, error = _get_calendar_service()
    if error:
        return error

    now = datetime.utcnow().isoformat() + "Z"
    try:
        events_result = service.events().list(
            calendarId="primary", timeMin=now,
            maxResults=10, singleEvents=True,
            orderBy="startTime"
        ).execute()
        events = events_result.get("items", [])
        target = None
        for event in events:
            summary = event.get("summary", "").lower()
            if query and query.lower() in summary:
                target = event
                break
        if not target and events:
            target = events[0]

        if not target:
            return "Tidak ada acara untuk dijoin."

        link = target.get("hangoutLink") or ""
        summary = target.get("summary", "Meeting")
        if link:
            import webbrowser
            webbrowser.open(link)
            return f"Membuka Meet link untuk: {summary}"
        return f"Tidak ada link Meet/Zoom untuk: {summary}"
    except Exception as e:
        return f"Gagal: {e}"

def create_event(summary: str, time_str: str = None) -> str:
    return "Buat acara di Google Calendar: gunakan Google Calendar UI atau perintah !calendar create <nama> <YYYY-MM-DD HH:MM>"
