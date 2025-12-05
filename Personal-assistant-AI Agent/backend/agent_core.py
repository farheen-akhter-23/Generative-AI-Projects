# agent_core.py
from __future__ import print_function
import datetime
import json
import os
from typing import List, Dict, Optional, Tuple

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

SCOPES = ["https://www.googleapis.com/auth/calendar"]
TIMEZONE = "America/Los_Angeles"
CALENDAR_ID = "primary"  # you can later swap to a separate demo calendar


# ---------- AUTH / CONFIG ----------

def get_calendar_service():
    """Authenticate and return a Google Calendar service client."""
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


def load_tasks(path: str = "daily-fixed-tasks.json") -> List[Dict]:
    """Load your structured routine from JSON."""
    with open(path, "r") as f:
        return json.load(f)


def weekday_short(date: datetime.date) -> str:
    return date.strftime("%a")  # e.g. Mon, Tue


def parse_time_hhmm(hhmm: str) -> datetime.time:
    hour, minute = map(int, hhmm.split(":"))
    return datetime.time(hour=hour, minute=minute)


def runs_on_date(task: Dict, date: datetime.date) -> bool:
    return weekday_short(date) in task["days"]


# ---------- CALENDAR HELPERS & CONFLICT CHECKING ----------

def get_events_for_day(service, date: datetime.date) -> List[Dict]:
    """Fetch all events for a specific day."""
    start_dt = datetime.datetime.combine(date, datetime.time.min)
    end_dt = datetime.datetime.combine(date, datetime.time.max)

    time_min = start_dt.isoformat() + "Z"
    time_max = end_dt.isoformat() + "Z"

    events = []
    page_token = None
    while True:
        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token
        ).execute()
        events.extend(result.get("items", []))
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return events


def slot_conflicts(
    events: List[Dict],
    start_dt: datetime.datetime,
    end_dt: datetime.datetime,
    agent_task_names: Optional[set] = None,
) -> bool:
    """
    Returns True if there is an overlapping event (excluding our own agent events).
    """
    agent_task_names = agent_task_names or set()

    for ev in events:
        summary = ev.get("summary", "")
        # Ignore our own agent-generated events when checking conflicts
        if summary in agent_task_names:
            continue

        start_str = ev["start"].get("dateTime") or (ev["start"].get("date") + "T00:00:00")
        end_str = ev["end"].get("dateTime") or (ev["end"].get("date") + "T23:59:59")

        ev_start = datetime.datetime.fromisoformat(start_str.replace("Z", "+00:00")).replace(tzinfo=None)
        ev_end = datetime.datetime.fromisoformat(end_str.replace("Z", "+00:00")).replace(tzinfo=None)

        # overlap if NOT completely before or after
        if not (end_dt <= ev_start or start_dt >= ev_end):
            return True

    return False


def find_next_free_slot(
    events: List[Dict],
    date: datetime.date,
    original_start: datetime.time,
    duration_minutes: int,
    day_end_time: datetime.time = datetime.time(22, 0),
    step_minutes: int = 15,
    agent_task_names: Optional[set] = None,
) -> Optional[Tuple[datetime.datetime, datetime.datetime]]:
    """
    Try moving the task later in the same day in step_minutes increments.
    Return (start_dt, end_dt) if a free slot is found, else None.
    """
    agent_task_names = agent_task_names or set()
    cur_start = datetime.datetime.combine(date, original_start)
    last_end_dt = datetime.datetime.combine(date, day_end_time)

    while cur_start + datetime.timedelta(minutes=duration_minutes) <= last_end_dt:
        cur_end = cur_start + datetime.timedelta(minutes=duration_minutes)
        if not slot_conflicts(events, cur_start, cur_end, agent_task_names):
            return cur_start, cur_end
        cur_start += datetime.timedelta(minutes=step_minutes)

    return None


def create_event(
    service,
    summary: str,
    start_dt: datetime.datetime,
    end_dt: datetime.datetime
) -> Dict:
    """Create a single Google Calendar event."""
    event = {
        "summary": summary,
        "start": {
            "dateTime": start_dt.isoformat(),
            "timeZone": TIMEZONE,
        },
        "end": {
            "dateTime": end_dt.isoformat(),
            "timeZone": TIMEZONE,
        }
    }
    return service.events().insert(calendarId=CALENDAR_ID, body=event).execute()


# ---------- CORE SCHEDULING ----------

def schedule_day(
    service,
    tasks: List[Dict],
    date: datetime.date,
    allow_reschedule: bool = True
) -> List[Dict]:
    """
    Schedule tasks for a single day.
    Returns a list of decisions:
      {
        "task_name": str,
        "status": "scheduled" | "scheduled_rescheduled" | "skipped",
        "scheduled_start": iso or None,
        "scheduled_end": iso or None,
        "reason": str
      }
    """
    decisions = []
    events = get_events_for_day(service, date)
    agent_task_names = {t["name"] for t in tasks}

    for task in tasks:
        if not runs_on_date(task, date):
            continue

        name = task["name"]
        start_time = parse_time_hhmm(task["start_time"])
        duration = task["duration_minutes"]

        original_start_dt = datetime.datetime.combine(date, start_time)
        original_end_dt = original_start_dt + datetime.timedelta(minutes=duration)

        # 1) Try original slot
        if not slot_conflicts(events, original_start_dt, original_end_dt, agent_task_names):
            ev = create_event(service, name, original_start_dt, original_end_dt)
            events.append(ev)
            decisions.append({
                "task_name": name,
                "status": "scheduled",
                "scheduled_start": original_start_dt.isoformat(),
                "scheduled_end": original_end_dt.isoformat(),
                "reason": "original_slot"
            })
            continue

        # 2) Try rescheduling later the same day
        if allow_reschedule:
            alt = find_next_free_slot(
                events,
                date,
                original_start=start_time,
                duration_minutes=duration,
                agent_task_names=agent_task_names,
            )
            if alt:
                alt_start, alt_end = alt
                ev = create_event(service, name, alt_start, alt_end)
                events.append(ev)
                decisions.append({
                    "task_name": name,
                    "status": "scheduled_rescheduled",
                    "scheduled_start": alt_start.isoformat(),
                    "scheduled_end": alt_end.isoformat(),
                    "reason": "rescheduled_due_to_conflict"
                })
            else:
                decisions.append({
                    "task_name": name,
                    "status": "skipped",
                    "scheduled_start": None,
                    "scheduled_end": None,
                    "reason": "no_free_slot_found"
                })
        else:
            decisions.append({
                "task_name": name,
                "status": "skipped",
                "scheduled_start": None,
                "scheduled_end": None,
                "reason": "conflict_and_reschedule_disabled"
            })

    return decisions


def schedule_range(
    service,
    tasks: List[Dict],
    start_date: datetime.date,
    days: int = 7,
    allow_reschedule: bool = True
) -> Dict:
    """Schedule tasks across multiple days. Returns a dict keyed by date."""
    result = {}
    for offset in range(days):
        date = start_date + datetime.timedelta(days=offset)
        decisions = schedule_day(service, tasks, date, allow_reschedule=allow_reschedule)
        result[date.isoformat()] = decisions
    return result


# ---------- CLEAR AGENT EVENTS ----------

def clear_agent_events(
    service,
    tasks: List[Dict],
    start_date: datetime.date,
    days: int = 7,
) -> int:
    """
    Delete events whose summary matches any agent task name in the date range.
    Returns number of deleted events.
    """
    task_names = {t["name"] for t in tasks}
    start_dt = datetime.datetime.combine(start_date, datetime.time.min)
    end_dt = datetime.datetime.combine(start_date + datetime.timedelta(days=days), datetime.time.max)

    time_min = start_dt.isoformat() + "Z"
    time_max = end_dt.isoformat() + "Z"

    page_token = None
    deleted = 0

    while True:
        result = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=time_min,
            timeMax=time_max,
            singleEvents=True,
            orderBy="startTime",
            pageToken=page_token
        ).execute()

        events = result.get("items", [])
        for ev in events:
            if ev.get("summary", "") in task_names:
                service.events().delete(calendarId=CALENDAR_ID, eventId=ev["id"]).execute()
                deleted += 1

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return deleted
