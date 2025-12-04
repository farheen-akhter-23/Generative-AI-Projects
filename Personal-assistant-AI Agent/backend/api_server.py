# api_server.py
import datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from agent_core import (
    get_calendar_service,
    load_tasks,
    schedule_day,
    schedule_range,
    clear_agent_events,
)
import os
import json

from openai import OpenAI


# ---------- INIT ----------
OPENAI_API_KEY = os.environ.get("OPEN_AI_KEY")
llm_client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

app = FastAPI(title="AI Calendar Agent Backend")

# CORS so React (later) can call this
origins = [
    "http://localhost:3000",
    "http://localhost:5174",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

service = get_calendar_service()
tasks = load_tasks("daily-fixed-tasks.json")


# ---------- MODELS ----------

class ScheduleRequest(BaseModel):
    start_date: Optional[str] = None  # ISO date, null = today
    days: int = 7
    allow_reschedule: bool = True


class ClearRequest(BaseModel):
    start_date: Optional[str] = None
    days: int = 7

class CommandRequest(BaseModel):
    command: str

# ---------- HELPERS ----------

def parse_date_or_today(date_str: Optional[str]) -> datetime.date:
    if date_str:
        return datetime.date.fromisoformat(date_str)
    return datetime.date.today()

# ---------- LLM ROUTER ----------

LLM_ROUTER_SYSTEM_PROMPT = """
You are a command router for a calendar-scheduling agent.

You receive natural language commands like:
- "schedule my routine for the next 7 days"
- "clear this week's schedule"
- "just schedule today"
- "schedule next 3 days without rescheduling"

You MUST respond with a single JSON object with this structure:

{
  "intent": "<one of: schedule_range | clear_range | schedule_today>",
  "params": {
    ... fields depending on intent ...
  }
}

INTENT SCHEMAS:

1) schedule_range:
{
  "intent": "schedule_range",
  "params": {
    "start_date": "YYYY-MM-DD",   // if user says "today" or "tomorrow", resolve it
    "days": 7,                    // integer number of days
    "allow_reschedule": true      // true/false whether to move tasks if conflict
  }
}

2) clear_range:
{
  "intent": "clear_range",
  "params": {
    "start_date": "YYYY-MM-DD",
    "days": 7
  }
}

3) schedule_today:
{
  "intent": "schedule_today",
  "params": {
    "allow_reschedule": true
  }
}

Rules:
- ALWAYS output valid JSON.
- NEVER include explanations or commentary outside the JSON.
- If the user doesn't specify dates, assume start_date is today and days=7 for ranges.
- Map phrases like "this week" to 7 days starting today.
- Map phrases like "next 3 days" to days=3.
- If you are unsure, choose a reasonable default instead of asking questions.
"""


def call_llm_router(nl_command: str) -> dict:
    """Send the natural-language command to the LLM and get back JSON spec."""
    if not llm_client:
        return {
            "error": "LLM not configured. Set OPENAI_API_KEY.",
            "raw_command": nl_command,
        }

    resp = llm_client.chat.completions.create(
        model="gpt-4.1-mini",  # or any other compatible model
        messages=[
            {"role": "system", "content": LLM_ROUTER_SYSTEM_PROMPT},
            {"role": "user", "content": nl_command},
        ],
        response_format={"type": "json_object"},
    )
    content = resp.choices[0].message.content
    return json.loads(content)


def execute_llm_action(spec: dict) -> dict:
    """Take the parsed intent/params and call our existing scheduling functions."""
    if "error" in spec:
        return spec

    intent = spec.get("intent")
    params = spec.get("params", {}) or {}

    today = datetime.date.today()

    if intent == "schedule_range":
        start_date_str = params.get("start_date")
        days = int(params.get("days", 7))
        allow_reschedule = bool(params.get("allow_reschedule", True))
        start_date = parse_date_or_today(start_date_str)
        result = schedule_range(
            service,
            tasks,
            start_date=start_date,
            days=days,
            allow_reschedule=allow_reschedule,
        )
        return {
            "intent": intent,
            "start_date": start_date.isoformat(),
            "days": days,
            "allow_reschedule": allow_reschedule,
            "result": result,
        }

    if intent == "clear_range":
        start_date_str = params.get("start_date")
        days = int(params.get("days", 7))
        start_date = parse_date_or_today(start_date_str)
        deleted = clear_agent_events(service, tasks, start_date, days)
        return {
            "intent": intent,
            "start_date": start_date.isoformat(),
            "days": days,
            "deleted": deleted,
        }

    if intent == "schedule_today":
        allow_reschedule = bool(params.get("allow_reschedule", True))
        decisions = schedule_day(service, tasks, today, allow_reschedule)
        return {
            "intent": intent,
            "date": today.isoformat(),
            "allow_reschedule": allow_reschedule,
            "decisions": decisions,
        }

    return {
        "error": f"Unknown intent: {intent}",
        "raw_spec": spec,
    }

# ---------- ENDPOINTS ----------

@app.get("/tasks")
def get_tasks():
    """Return the configured routine (from JSON)."""
    return tasks


@app.get("/today_plan")
def today_plan():
    """
    Schedule tasks for today and return decisions.
    (You can later split this into 'plan only' vs 'plan + write' if you want.)
    """
    today = datetime.date.today()
    decisions = schedule_day(service, tasks, today, allow_reschedule=True)
    return {
        "date": today.isoformat(),
        "decisions": decisions,
    }


@app.post("/schedule")
def schedule(req: ScheduleRequest):
    """
    Schedule a range of days starting from start_date (or today).
    """
    start_date = parse_date_or_today(req.start_date)
    result = schedule_range(
        service,
        tasks,
        start_date=start_date,
        days=req.days,
        allow_reschedule=req.allow_reschedule,
    )
    return {
        "start_date": start_date.isoformat(),
        "days": req.days,
        "allow_reschedule": req.allow_reschedule,
        "result": result,
    }


@app.post("/clear")
def clear(req: ClearRequest):
    """
    Clear all agent-created events (matching task names) in the range.
    """
    start_date = parse_date_or_today(req.start_date)
    deleted = clear_agent_events(service, tasks, start_date, days=req.days)
    return {
        "start_date": start_date.isoformat(),
        "days": req.days,
        "deleted": deleted,
    }

@app.post("/command_llm")
def command_llm(req: CommandRequest):
    """
    Natural-language entry point for your agent.

    Examples:
      - "schedule my routine for the next 5 days"
      - "clear the next 7 days"
      - "just schedule today"
      - "schedule the next 3 days without rescheduling"
    """
    spec = call_llm_router(req.command)
    result = execute_llm_action(spec)
    return {
        "command": req.command,
        "parsed": spec,
        "result": result,
    }
