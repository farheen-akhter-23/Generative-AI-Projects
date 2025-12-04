from __future__ import print_function
import datetime
import json
import os
import webbrowser
import time
from typing import List, Dict

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = "America/Los_Angeles"  # change if needed

# OPTIONAL: use a separate demo calendar instead of primary
CALENDAR_ID = "primary"  # or replace with your demo calendar ID


# ---------- AUTH ----------

def get_calendar_service():
    creds = None
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json", SCOPES
            )
            creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build("calendar", "v3", credentials=creds)


# ---------- LOAD TASKS ----------

def load_tasks(path="daily-fixed-tasks.json") -> List[Dict]:
    with open(path, "r") as f:
        return json.load(f)


# ---------- HELPERS ----------

def weekday_short(date: datetime.date) -> str:
    return date.strftime("%a")  # e.g. Mon, Tue


def parse_time_hhmm(hhmm: str) -> datetime.time:
    hour, minute = map(int, hhmm.split(":"))
    return datetime.time(hour=hour, minute=minute)


def runs_on_date(task: Dict, date: datetime.date) -> bool:
    return weekday_short(date) in task["days"]


# ---------- CLEAR EXISTING SCHEDULED EVENTS ----------

def clear_scheduled_events(service, tasks: List[Dict],
                           start_date: datetime.date,
                           days_span: int = 7):
    print("\n🧹 STEP 1/2: Clearing existing scheduled routine (demo window)...")
    task_names = {t["name"] for t in tasks}

    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(
        start_date + datetime.timedelta(days=days_span),
        datetime.time.max
    )

    time_min = start_dt.isoformat() + "Z"
    time_max = end_dt.isoformat() + "Z"

    page_token = None
    to_delete = []

    while True:
        events_result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token
        ).execute()

        events = events_result.get("items", [])
        for event in events:
            summary = event.get("summary", "")
            if summary in task_names:
                to_delete.append(event)

        page_token = events_result.get("nextPageToken")
        if not page_token:
            break

    if not to_delete:
        print("   ➤ No matching events found to delete in the demo window.")
        return

    print(f"   ➤ Found {len(to_delete)} events created by this scheduler. Deleting...\n")

    for i, event in enumerate(to_delete, start=1):
        eid = event["id"]
        summary = event.get("summary", "")
        start = event["start"].get("dateTime", event["start"].get("date", ""))
        print(f"   [{i}/{len(to_delete)}] ❌ Deleting: {summary} at {start}")
        service.events().delete(calendarId=CALENDAR_ID, eventId=eid).execute()

    print("\n✅ Existing routine cleared in demo window.\n")


# ---------- CREATE EVENTS + VISUAL OPEN ----------

def create_event_visual(service, task: Dict, date: datetime.date, pause: bool = True):
    start_time = parse_time_hhmm(task["start_time"])
    duration = task["duration_minutes"]

    start_dt = datetime.datetime.combine(date, start_time)
    end_dt = start_dt + datetime.timedelta(minutes=duration)

    event = {
        "summary": task["name"],
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": TIMEZONE,
        }
    }

    created = service.events().insert(calendarId=CALENDAR_ID, body=event).execute()
    summary = created.get("summary")
    html_link = created.get("htmlLink")

    print(f"      ➕ Created: {summary} at {task['start_time']}")
    if html_link:
        print("         🌐 Opening this event in Google Calendar...")
        # Open in browser (new tab)
        webbrowser.open_new_tab(html_link)
        # Small pause so the hiring manager can see it pop
        if pause:
            input("         ⏸ Press Enter to schedule the next event...")

    return created


def schedule_demo_window_with_visuals(service,
                                      tasks: List[Dict],
                                      start_date: datetime.date,
                                      days_span: int = 7,
                                      pause_each: bool = True):
    print("📅 STEP 2/2: Rebuilding your routine with visual updates...\n")
    for offset in range(days_span):
        day = start_date + datetime.timedelta(days=offset)
        day_str = day.strftime("%a %Y-%m-%d")
        print(f"─── 🗓  {day_str}  ───")

        created_any = False
        for task in tasks:
            if runs_on_date(task, day):
                created_any = True
                create_event_visual(service, task, day, pause=pause_each)

        if not created_any:
            print("      (no tasks scheduled this day)")

        print()  # blank line between days

    print("🏁 Demo complete! All demo-window events added.\n")


# ---------- MAIN ----------

if __name__ == "__main__":
    service = get_calendar_service()
    tasks = load_tasks("daily-fixed-tasks.json")

    # Demo config
    start_date = datetime.date.today()      # today as demo start
    days_span = 3                           # 3 days is great for demo; change to 7 if you like
    pause_each = True                       # wait for Enter after each event

    print("\n================ AI CALENDAR AGENT – VISUAL DEMO ================\n")
    print(f"Demo window: {start_date} → {start_date + datetime.timedelta(days=days_span)}")
    print("Tip: keep Google Calendar open on other half of your screen.\n")

    clear_scheduled_events(service, tasks, start_date, days_span)
    schedule_demo_window_with_visuals(service, tasks, start_date, days_span, pause_each)
    print("✨ Refresh or look at your Calendar week view to admire the full structure.")
