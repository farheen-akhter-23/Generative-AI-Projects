# jobflow_agent/agent.py
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, List

from google.adk import tools
from google.adk.agents.llm_agent import Agent  # ✅ use Agent from ADK
import datetime
import gspread
from google.oauth2.service_account import Credentials


# ---------- Simple "database" ----------

# Use project-root/profile_summary.json
PROFILE_PATH = Path(__file__).resolve().parent.parent / "profile_summary.json"


def load_profile() -> Dict[str, Any]:
    if PROFILE_PATH.exists():
        return json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
    # fallback placeholder profile
    return {
        "name": "Your Name",
        "current_role": "ML Engineer",
        "skills": [
            "Python",
            "FastAPI",
            "React",
            "LLMs",
            "RAG",
            "MLOps",
        ],
        "projects": [
            "AI Calendar Agent (personal productivity automation)",
        ],
    }


# ---------- Tool 1: Parse Job Description (lightweight) ----------

@dataclass
class ParsedJob:
    title: str
    company: str
    location: str
    must_have_skills: List[str]
    nice_to_have_skills: List[str]
    raw_summary: str



def parse_job_description(text: str) -> Dict[str, Any]:
    """
    Lightweight parser for a job description.

    For v1 we keep it simple and let the main LLM reason about the full text.
    This returns structured placeholders + the raw JD text.
    """
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    title = lines[0] if lines else "Unknown Title"

    # You can make this smarter later (regex, patterns, etc.)
    company = "Unknown Company"
    location = "Unknown / Remote"

    return {
        "title": title,
        "company": company,
        "location": location,
        "must_have_skills": [],
        "nice_to_have_skills": [],
        "raw_summary": text,
    }


# ---------- Tool 2: Load Profile Summary ----------

def load_profile_summary() -> Dict[str, Any]:
    """
    Returns a structured summary of the user's profile, skills and projects.
    """
    return load_profile()


# ---------- Root Agent ----------

SYSTEM_PROMPT = """
You are JobFlow AI, an AI career copilot that:

1. Analyzes job descriptions.
2. Compares them to the user's profile.
3. Produces:
   - A fit summary (strong match / partial / stretch).
   - Missing or weak skill gaps.
   - 3–5 resume bullet suggestions tailored for this role.
   - 2–3 talking points for recruiter / hiring manager outreach.

Use tools to:
- parse_job_description(text) when the user provides a job description or link text.
- load_profile_summary() to understand the user's skills and background.
- log_application_to_sheet(job_title, company, location, link, status, notes):
    Use this when the user wants to track or log a job opportunity in a Google Sheet.
    Populate reasonable defaults for location, status, and notes if missing.

Always respond in a concise, structured way:
1) Role & Company
2) Fit Summary
3) Gaps
4) Recommended resume bullets
5) Suggested outreach message
""".strip()

# ---------- Google Sheets Config ----------

# Path to your service account JSON
SHEETS_SERVICE_ACCOUNT_FILE = Path(__file__).resolve().parent.parent / "ai-scheduler.json"

# Replace with your actual Sheet ID from the URL
SHEETS_SPREADSHEET_ID = "https://docs.google.com/spreadsheets/d/1N56Y-Mp0ggQ1uhMbsH4Nljkzf9PiTkZACxe5sCkedcU/edit?gid=0#gid=0"

SHEETS_SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def get_jobflow_sheet():
    """Return the first worksheet in your JobFlow AI Tracker Google Sheet."""
    creds = Credentials.from_service_account_file(
        str(SHEETS_SERVICE_ACCOUNT_FILE),
        scopes=SHEETS_SCOPES,
    )
    client = gspread.authorize(creds)
    sh = client.open_by_key(SHEETS_SPREADSHEET_ID)
    # use the first sheet (or .worksheet("JobFlow AI Tracker") if you named it)
    return sh.sheet1

def log_application_to_sheet(
    job_title: str,
    company: str,
    location: str = "",
    link: str = "",
    status: str = "Interested",
    notes: str = "",
) -> Dict[str, Any]:
    """
    Tool: log_application_to_sheet(job_title, company, location, link, status, notes)

    Appends a new row to the JobFlow AI Tracker Google Sheet.

    Returns a small JSON payload confirming the write.
    """

    sheet = get_jobflow_sheet()
    timestamp = datetime.datetime.now().isoformat(timespec="seconds")

    row = [
        timestamp,
        job_title,
        company,
        location,
        link,
        status,
        notes,
    ]

    sheet.append_row(row)

    return {
        "status": "ok",
        "written_row": {
            "timestamp": timestamp,
            "job_title": job_title,
            "company": company,
            "location": location,
            "link": link,
            "status": status,
            "notes": notes,
        },
    }

# 🔹 ADK looks for this symbol by default
root_agent = Agent(
    model="gemini-2.5-flash", 
    name="jobflow_agent",
    description="JobFlow AI – an AI career copilot that analyzes JDs against Farheen's profile.",
    instruction=SYSTEM_PROMPT,
    tools=[
        parse_job_description,
        load_profile_summary,
        log_application_to_sheet
    ],
)

