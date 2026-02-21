import os
import uuid
import hmac
import hashlib
import time
import threading
import json
import re
import base64
import secrets
import smtplib
import random
from pathlib import Path
import html
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
try:
    from zoneinfo import ZoneInfo
except Exception:
    ZoneInfo = None

from fastapi import FastAPI, Form, Request, HTTPException, Header, UploadFile, File
from fastapi.responses import Response, FileResponse, JSONResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Gather
from twilio.twiml.messaging_response import MessagingResponse
from twilio.request_validator import RequestValidator
from dotenv import load_dotenv
import requests

try:
    from openai import OpenAI
except Exception:
    OpenAI = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    import docx
except Exception:
    docx = None

try:
    import psycopg2
except Exception:
    psycopg2 = None

load_dotenv(override=True)

# LiveKit integration is optional and isolated in /livekit_agent.
try:
    from livekit_agent.health import check_livekit_health
    from livekit_agent.orchestrator import LiveKitVoiceOrchestrator
except Exception:
    check_livekit_health = None
    LiveKitVoiceOrchestrator = None

app = FastAPI(title="Twilio + ElevenLabs Voice Agent")


@app.on_event("startup")
def on_startup():
    ok = init_db()
    log_event(f"DB_INIT {'OK' if ok else 'SKIPPED_OR_FAILED'}")
    _cleanup_tts_cache()

AUDIO_DIR = Path(__file__).resolve().parent.parent / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
LOG_DIR = Path(__file__).resolve().parent.parent / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
RESUME_DIR = Path(__file__).resolve().parent.parent / "uploads" / "resumes"
RESUME_DIR.mkdir(parents=True, exist_ok=True)
SCRIPT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "call_script.json"
SARA_SCRIPT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "sara_prompt.json"
ADAM_SCRIPT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "adam_prompt.json"
SARA_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "config" / "sara_system_prompt.txt"
ADAM_SYSTEM_PROMPT_PATH = Path(__file__).resolve().parent.parent / "config" / "adam_system_prompt.txt"

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "")

ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # ElevenLabs "Adam" (male)
TWILIO_FALLBACK_VOICE = os.getenv("TWILIO_FALLBACK_VOICE", "Polly.Matthew")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
ASSISTANT_NAME = os.getenv("ASSISTANT_NAME", "Adam")
COMPANY_NAME = os.getenv("COMPANY_NAME", "Joblynk")
MANAGER_PHONE_NUMBER = os.getenv("MANAGER_PHONE_NUMBER", "+17736563444")
AGENT_VOICE_PROFILES = {
    "adam": {
        "assistant_name": "Adam",
        "elevenlabs_voice_id": "pNInz6obpgDQGcFmaJgB",  # male
        "twilio_fallback_voice": "Polly.Matthew",
    },
    "sara": {
        "assistant_name": "Sara",
        "elevenlabs_voice_id": "21m00Tcm4TlvDq8ikWAM",  # female
        "twilio_fallback_voice": "Polly.Joanna",
    },
}

CALL_API_KEY = os.getenv("CALL_API_KEY", "")
CALL_CONVERSATIONAL_AI_BRIDGE = os.getenv("CALL_CONVERSATIONAL_AI_BRIDGE", "false").lower() in {"1", "true", "yes"}
VOICE_PROVIDER = (os.getenv("VOICE_PROVIDER", "legacy") or "legacy").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:AIzaSyC69gwKzgTO9@127.0.0.1:5432/agent_memory_hub")
TTS_CACHE_MAX_FILES = int(os.getenv("TTS_CACHE_MAX_FILES", "500"))
TTS_CACHE_MAX_DAYS = int(os.getenv("TTS_CACHE_MAX_DAYS", "30"))
CONVERSATION_STATE: dict[str, dict] = {}
INTERVIEW_SESSIONS: dict[str, dict] = {}
JOB_POSTINGS: dict[str, dict] = {}
VALIDATE_TWILIO_SIGNATURE = os.getenv("VALIDATE_TWILIO_SIGNATURE", "false").lower() in {"1", "true", "yes"}

# Simple app login (can be overridden with env vars).
APP_LOGIN_EMAIL = os.getenv("APP_LOGIN_EMAIL", "adam@joblynk.ai").strip().lower()
APP_LOGIN_PASSWORD = os.getenv("APP_LOGIN_PASSWORD", "lr26fzky8UR^gr1s")
APP_SESSION_SECRET = os.getenv("APP_SESSION_SECRET", OPENAI_API_KEY or "joblynk-screening-session-secret")
APP_SESSION_COOKIE = "joblynk_session"
AUTH_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "auth.json"
AGENT_PROFILE_PATH = Path(__file__).resolve().parent.parent / "config" / "agent_profile.json"
# In-memory reset + throttling stores (simple single-instance protection).
PASSWORD_RESET_CODES: dict[str, dict] = {}
AUTH_RATE_LIMIT: dict[str, list[float]] = {}
QUESTION_HISTORY: dict[str, list[str]] = {}
CALL_PROVIDER_TRACK: dict[str, dict] = {}

SMTP_HOST = os.getenv("SMTP_HOST", "")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587") or "587")
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM = os.getenv("SMTP_FROM", SMTP_USER or "no-reply@joblynk.ai")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() in {"1", "true", "yes"}

PROTECTED_PREFIXES = (
    "/ui",
    "/dashboard",
    "/jobs",
    "/interview",
    "/candidate",
    "/candidates",
    "/resume",
    "/profile",
    "/db/health",
    "/referrals",
)

PUBLIC_PREFIXES = (
    "/",
    "/login",
    "/signup",
    "/contact-us",
    "/logout",
    "/forgot-password",
    "/reset-password",
    "/twilio",
    "/twiml",
    "/audio",
    "/call/start",
    "/r",
)


def _now():
    try:
        if ZoneInfo:
            return datetime.now(ZoneInfo("America/New_York")).isoformat()
    except Exception:
        pass
    return datetime.now(timezone(timedelta(hours=-5))).isoformat()


def _load_call_script_config(agent_profile: str | None = None) -> dict:
    defaults = {
        "intro_template": "Hi {first_name}, this is {agent_name}, an AI assistant designed to help recruiters screen candidates. Do you have a few minutes to speak right now?",
        "consent_yes_template": "Great, thank you. The position is {job_title}. It focuses on {job_summary}. This is just a quick overview so you have context for the questions I’ll ask. First question: {first_question}",
        "consent_retry": "Just to confirm, do you have a few minutes now for a short screening conversation?",
        "consent_no": "No problem at all. Thank you for your time. We can reconnect at a better time.",
        "next_question_template": "Next question: {next_question}",
        "wrap_up": "That’s all the questions I have for you. Thank you for sharing your responses. Our recruitment team will reach out to you. If you have any further questions, you can email the recruiter you are working with from Softwise Solutions.",
    }

    def _merge_from(path: Path):
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    defaults.update({k: v for k, v in data.items() if isinstance(v, str)})
        except Exception:
            pass

    # Global script defaults for all agents.
    _merge_from(SCRIPT_CONFIG_PATH)

    # Optional per-agent override.
    key = (agent_profile or "").strip().lower()
    if key == "sara":
        _merge_from(SARA_SCRIPT_CONFIG_PATH)
    elif key == "adam":
        _merge_from(ADAM_SCRIPT_CONFIG_PATH)

    # Normalize legacy phrasing requested by user.
    nqt = defaults.get("next_question_template", "")
    if isinstance(nqt, str) and "Thanks, that’s helpful." in nqt:
        defaults["next_question_template"] = nqt.replace("Thanks, that’s helpful. ", "").strip()

    return defaults


def log_event(message: str):
    p = LOG_DIR / f"voice-agent-{datetime.now(timezone.utc).strftime('%Y%m%d')}.log"
    with p.open("a", encoding="utf-8") as f:
        f.write(f"[{_now()}] {message}\n")


def _build_interviewer_system_prompt(path: Path, default_name: str, session: dict | None = None) -> str:
    session = session or {}
    template = ""
    try:
        if path.exists():
            template = path.read_text(encoding="utf-8")
    except Exception:
        template = ""
    if not template.strip():
        return f"You are {default_name}, a senior technical interviewer at Joblynk. Ask one concise technical question at a time in a warm, professional tone."

    must_ask = session.get("plan") or []
    if isinstance(must_ask, list):
        must_ask_text = "\n".join([f"- {str(x)}" for x in must_ask[:12]])
    else:
        must_ask_text = str(must_ask or "")

    vals = {
        "name": str(session.get("assistant_name") or default_name),
        "work_methodology": str(session.get("work_methodology") or "Already covered in prior screening"),
        "jd_context": str(session.get("job_description") or session.get("job_title") or "Not provided"),
        "candidate_info": str(session.get("resume") or session.get("candidate_name") or "Not provided"),
        "must_ask": must_ask_text or "Not provided",
        "salary_period": str(session.get("salary_period") or "Confidential - handled by HR"),
        "benefits": str(session.get("benefits") or "Health insurance, 401k, and other benefits included."),
    }
    try:
        return template.format(**vals)
    except Exception:
        return template


def _build_sara_system_prompt(session: dict | None = None) -> str:
    return _build_interviewer_system_prompt(SARA_SYSTEM_PROMPT_PATH, "Sara", session)


def _build_adam_system_prompt(session: dict | None = None) -> str:
    return _build_interviewer_system_prompt(ADAM_SYSTEM_PROMPT_PATH, "Adam", session)


def _active_interviewer_prompt(session: dict) -> str:
    key = (session.get("agent_profile") or "").strip().lower()
    if key == "sara":
        return _build_sara_system_prompt(session)
    if key == "adam":
        return _build_adam_system_prompt(session)
    return ""


def _prompt_preview_config() -> dict:
    return {
        "sara": {
            "intro": "Hi, this is Sara from Joblynk. Is this a good time to talk?",
            "after_consent": "Thank you. I am calling regarding the selected position. Let's start the technical interview. Can you please introduce yourself and share your work experience, education, and a recent project you have completed?",
            "closing_1": "It was great speaking with you today. Our HR team will be in touch soon to guide you through the next steps if you're shortlisted.",
            "closing_2": "Thank you for your time. Interview is over, HR will contact you for further details.",
        },
        "adam": {
            "intro": "Hi, this is Adam from Joblynk. Is this a good time to talk?",
            "after_consent": "Thank you. I am calling regarding the selected position. Let's start the technical interview. Can you please introduce yourself and share your work experience, education, and a recent project you have completed?",
            "closing_1": "It was great speaking with you today. Our HR team will be in touch soon to guide you through the next steps if you're shortlisted.",
            "closing_2": "Thank you for your time. Interview is over, HR will contact you for further details.",
        },
    }


def _prompt_line(session: dict, key: str, fallback: str = "") -> str:
    cfg = _prompt_preview_config()
    profile = (session.get("agent_profile") or "sara").strip().lower()
    return (((cfg.get(profile) or {}).get(key)) or fallback).strip()


def _next_prompt_question(session: dict) -> str:
    plan = session.get("plan") or []
    if not isinstance(plan, list) or not plan:
        return "Could you walk me through one recent project you delivered end to end?"
    idx = int(session.get("prompt_q_idx", 0) or 0)
    if idx >= len(plan):
        session["awaiting_final_questions"] = True
        return "Do you have any questions before we conclude the interview?"
    q = str(plan[idx]).strip() or "Could you walk me through one recent project you delivered end to end?"
    session["prompt_q_idx"] = idx + 1
    return q


def _prompt_driven_interview_turn(session: dict, user_text: str, call_sid: str = "", session_id: str = "") -> str:
    low_user = (user_text or "").strip().lower()

    if session.get("awaiting_final_questions"):
        if any(x in low_user for x in ["no", "nope", "none", "that's all", "no more", "2", "end the call", "bye", "goodbye"]):
            if session.get("handoff_requested") and session_id:
                room = f"joblynk-{session_id[:10]}-{uuid.uuid4().hex[:4]}"
                ok = _trigger_manager_handoff(session_id, room)
                if ok:
                    session["handoff_room"] = room
                    session["handoff_now"] = True
                    session["completed"] = True
                    session["call_in_progress"] = False
                    return "I do not have the complete answer to all your questions. Please hold for a moment while I connect you to our hiring manager now."
            session["completed"] = True
            session["call_in_progress"] = False
            return "It was great speaking with you today. Our HR team will be in touch soon to guide you through the next steps if you're shortlisted. Thank you for your time. Interview is over, HR will contact you for further details."
        ans, handoff = _answer_candidate_question_or_handoff(session, user_text, call_sid)
        if handoff:
            session["handoff_requested"] = True
            return "I do not have the full answer right now. Our hiring manager can help, and at the end of this call I will connect you to the hiring manager. Do you have any other questions before we conclude the interview?"
        return f"{ans} Do you have any other questions before we conclude the interview?"

    if any(x in low_user for x in ["end the call", "end call", "stop", "hang up", "goodbye", "bye", "can we end"]):
        if session.get("handoff_requested") and session_id:
            room = f"joblynk-{session_id[:10]}-{uuid.uuid4().hex[:4]}"
            ok = _trigger_manager_handoff(session_id, room)
            if ok:
                session["handoff_room"] = room
                session["handoff_now"] = True
                session["completed"] = True
                session["call_in_progress"] = False
                return "I do not have the complete answer to all your questions. Please hold for a moment while I connect you to our hiring manager now."
        session["completed"] = True
        session["call_in_progress"] = False
        return "It was great speaking with you today. Our HR team will be in touch soon to guide you through the next steps if you're shortlisted. Thank you for your time. Interview is over, HR will contact you for further details."

    # Two-way Q&A: if candidate asks a question, answer politely and continue.
    asks_question = ("?" in (user_text or "")) or low_user.startswith(("can ", "could ", "what ", "why ", "how ", "when ", "where ", "who ", "do ", "does ", "is ", "are ", "will ", "would "))
    if asks_question:
        ans, handoff = _answer_candidate_question_or_handoff(session, user_text, call_sid)
        if handoff:
            session["handoff_requested"] = True
            return "I do not have the full answer right now. Our hiring manager can help, and at the end of this call I will connect you to the hiring manager."
        return f"{ans} {_next_prompt_question(session)}"

    prompt = _active_interviewer_prompt(session)
    if not prompt or not (OpenAI and OPENAI_API_KEY):
        return f"Thanks for sharing. {_next_prompt_question(session)}"

    history = session.setdefault("dialogue", [])
    if user_text:
        history.append({"role": "candidate", "text": user_text[:700]})
    history = history[-8:]
    session["dialogue"] = history

    asked = session.get("plan") or []
    asked_text = "\n".join([f"- {q}" for q in asked[:12]]) if isinstance(asked, list) else str(asked)

    payload = {
        "candidate_message": (user_text or "")[:700],
        "conversation_history": history,
        "must_ask_topics": asked_text,
        "job_title": session.get("job_title") or "",
        "job_description": (session.get("job_description") or "")[:4000],
        "candidate_info": (session.get("resume") or "")[:4000],
        "rules": [
            "Run this as a two-way voice interview conversation",
            "If candidate asks a question, answer per policy and continue interview flow",
            "Ask one question at a time",
            "Use must-ask topics naturally during interview",
            "When interview is complete, include: Interview is over, HR will contact you for further details.",
        ],
    }

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        r = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.35,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload)},
            ],
            max_tokens=140,
        )
        txt = (r.choices[0].message.content or "").strip()
        if not txt:
            txt = f"Thank you. {_next_prompt_question(session)}"
        low_txt = txt.lower()
        if "continue with more detail" in low_txt or "could you continue with more detail" in low_txt:
            prev = ""
            if len(history) >= 2 and isinstance(history[-2], dict):
                prev = str(history[-2].get("text") or "").lower()
            if "continue with more detail" in prev:
                txt = f"Thanks for clarifying. {_next_prompt_question(session)}"

        # Guard against repeated same-question loops.
        last_reply = str(session.get("last_prompt_reply") or "")
        if last_reply and txt.strip().lower() == last_reply.strip().lower():
            session["repeat_reply_count"] = int(session.get("repeat_reply_count", 0)) + 1
        else:
            session["repeat_reply_count"] = 0
        session["last_prompt_reply"] = txt

        if int(session.get("repeat_reply_count", 0)) >= 2:
            txt = f"Thanks for clarifying. {_next_prompt_question(session)}"
            session["repeat_reply_count"] = 0
            session["last_prompt_reply"] = txt

        history.append({"role": "interviewer", "text": txt[:1400]})
        session["dialogue"] = history[-16:]
        if "interview is over" in txt.lower():
            if session.get("handoff_requested") and session_id:
                room = f"joblynk-{session_id[:10]}-{uuid.uuid4().hex[:4]}"
                ok = _trigger_manager_handoff(session_id, room)
                if ok:
                    session["handoff_room"] = room
                    session["handoff_now"] = True
                    txt = "I do not have the complete answer to all your questions. Please hold for a moment while I connect you to our hiring manager now."
            session["completed"] = True
            session["call_in_progress"] = False
        _mark_call_provider(call_sid, "openai", "prompt_driven_interview")
        return txt
    except Exception as e:
        log_event(f"PROMPT_DRIVEN_TURN_FAIL | {e}")
        return f"Thanks. {_next_prompt_question(session)}"


def _load_auth_config() -> dict:
    data = {"email": APP_LOGIN_EMAIL, "password": APP_LOGIN_PASSWORD}
    try:
        if AUTH_CONFIG_PATH.exists():
            raw = json.loads(AUTH_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                data["email"] = (raw.get("email") or data["email"]).strip().lower()
                data["password"] = raw.get("password") or data["password"]
    except Exception as e:
        log_event(f"AUTH_CONFIG_LOAD_FAIL | {e}")
    return data


def _save_auth_config(email: str, password: str):
    try:
        AUTH_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        AUTH_CONFIG_PATH.write_text(json.dumps({"email": email, "password": password}, indent=2), encoding="utf-8")
    except Exception as e:
        log_event(f"AUTH_CONFIG_SAVE_FAIL | {e}")


def _current_auth_email() -> str:
    return _load_auth_config()["email"]


def _current_auth_password() -> str:
    return _load_auth_config()["password"]


def _ensure_users_table() -> None:
    conn = _db_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    create table if not exists public.screening_users (
                      id bigserial primary key,
                      email text unique not null,
                      password text not null,
                      created_at timestamptz default now(),
                      updated_at timestamptz default now()
                    )
                    """
                )
    except Exception as e:
        log_event(f"USERS_TABLE_ENSURE_FAIL | {e}")
    finally:
        conn.close()


def _get_user_password(email: str) -> str:
    target = (email or "").strip().lower()
    if not target:
        return ""
    conn = _db_conn()
    if not conn:
        return ""
    try:
        with conn.cursor() as cur:
            cur.execute("select password from public.screening_users where email=%s limit 1", (target,))
            row = cur.fetchone()
            return str(row[0] or "") if row else ""
    except Exception as e:
        log_event(f"USERS_LOOKUP_FAIL | {e}")
        return ""
    finally:
        conn.close()


def _user_exists(email: str) -> bool:
    return bool(_get_user_password(email))


def _upsert_user(email: str, password: str) -> bool:
    target = (email or "").strip().lower()
    pwd = password or ""
    if not target or not pwd:
        return False
    _ensure_users_table()
    conn = _db_conn()
    if not conn:
        return False
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into public.screening_users (email, password, updated_at)
                    values (%s,%s,now())
                    on conflict (email) do update set
                      password=excluded.password,
                      updated_at=now()
                    """,
                    (target, pwd),
                )
        return True
    except Exception as e:
        log_event(f"USERS_UPSERT_FAIL | {e}")
        return False
    finally:
        conn.close()


def _load_agent_profile() -> dict:
    default_profile = {
        "agent_name": "Adam",
        "display_name": "Adam - Master AI Controller",
        "role": "Master AI Controller",
        "company": "Joblynk",
        "work_email": "adam@joblynk.ai",
        "phone": "+17732739855",
        "timezone": "America/Chicago",
        "location": "Chicago, IL",
        "department": "Career Services AI",
        "date_of_joining": "2026-02-16",
        "bio": "I coordinate screening, resume audits, and candidate workflows for Joblynk.",
    }
    # Prefer DB record when available.
    conn = _db_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select agent_name, display_name, role, company, work_email, phone, timezone, location, department,
                           coalesce(to_char(date_of_joining, 'YYYY-MM-DD'), ''), bio
                    from public.screening_agent_profiles
                    where profile_id = 1
                    limit 1
                    """
                )
                row = cur.fetchone()
                if row:
                    keys = [
                        "agent_name", "display_name", "role", "company", "work_email", "phone",
                        "timezone", "location", "department", "date_of_joining", "bio"
                    ]
                    default_profile.update({k: str(v or "") for k, v in zip(keys, row)})
                    return default_profile
        except Exception as e:
            log_event(f"AGENT_PROFILE_DB_LOAD_FAIL | {e}")
        finally:
            conn.close()

    # Fallback to file-based profile.
    try:
        if AGENT_PROFILE_PATH.exists():
            raw = json.loads(AGENT_PROFILE_PATH.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                default_profile.update({k: str(v) for k, v in raw.items() if isinstance(v, (str, int, float))})
    except Exception as e:
        log_event(f"AGENT_PROFILE_LOAD_FAIL | {e}")
    return default_profile


def _save_agent_profile(profile: dict) -> bool:
    saved_ok = False
    # Save to DB first
    conn = _db_conn()
    if conn:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into public.screening_agent_profiles (
                            profile_id, agent_name, display_name, role, company, work_email, phone,
                            timezone, location, department, date_of_joining, bio, updated_at
                        )
                        values (1,%s,%s,%s,%s,%s,%s,%s,%s,%s,nullif(%s,'')::date,%s,now())
                        on conflict (profile_id)
                        do update set
                            agent_name=excluded.agent_name,
                            display_name=excluded.display_name,
                            role=excluded.role,
                            company=excluded.company,
                            work_email=excluded.work_email,
                            phone=excluded.phone,
                            timezone=excluded.timezone,
                            location=excluded.location,
                            department=excluded.department,
                            date_of_joining=excluded.date_of_joining,
                            bio=excluded.bio,
                            updated_at=now()
                        """,
                        (
                            profile.get("agent_name", ""),
                            profile.get("display_name", ""),
                            profile.get("role", ""),
                            profile.get("company", ""),
                            profile.get("work_email", ""),
                            profile.get("phone", ""),
                            profile.get("timezone", ""),
                            profile.get("location", ""),
                            profile.get("department", ""),
                            profile.get("date_of_joining", ""),
                            profile.get("bio", ""),
                        ),
                    )
                    saved_ok = True
        except Exception as e:
            log_event(f"AGENT_PROFILE_DB_SAVE_FAIL | {e}")
        finally:
            conn.close()

    # Keep file backup as secondary persistence
    try:
        AGENT_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        AGENT_PROFILE_PATH.write_text(json.dumps(profile, indent=2), encoding="utf-8")
    except Exception as e:
        log_event(f"AGENT_PROFILE_SAVE_FAIL | {e}")

    return saved_ok


def _send_password_reset_email(to_email: str, code: str) -> bool:
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        log_event("SMTP_NOT_CONFIGURED | cannot send reset email")
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = "Joblynk Password Reset Code"
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        msg.set_content(
            f"You requested a password reset for Joblynk Screening Console.\n\n"
            f"Your one-time reset code is: {code}\n"
            f"This code expires in 20 minutes.\n\n"
            f"If you did not request this, you can ignore this email."
        )

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        log_event(f"SMTP_SEND_FAIL | {e}")
        return False


def _send_agent_notification(to_email: str, subject: str, body: str) -> bool:
    if not to_email:
        return False
    if not SMTP_HOST or not SMTP_USER or not SMTP_PASS:
        log_event("SMTP_NOT_CONFIGURED | cannot send agent notification")
        return False
    try:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = SMTP_FROM
        msg["To"] = to_email
        msg.set_content(body)
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
            if SMTP_USE_TLS:
                server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        return True
    except Exception as e:
        log_event(f"SMTP_AGENT_NOTIFY_FAIL | {e}")
        return False


def _is_rate_limited(key: str, limit: int, window_seconds: int) -> bool:
    now = time.time()
    arr = AUTH_RATE_LIMIT.get(key, [])
    arr = [t for t in arr if now - t <= window_seconds]
    if len(arr) >= limit:
        AUTH_RATE_LIMIT[key] = arr
        return True
    arr.append(now)
    AUTH_RATE_LIMIT[key] = arr
    return False


def _request_ip(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    if xff:
        return xff
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _generate_reset_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(6))


def _session_token(email: str) -> str:
    payload = f"{email}|{int(time.time())}"
    sig = hmac.new(APP_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
    raw = f"{payload}|{sig}".encode()
    return base64.urlsafe_b64encode(raw).decode()


def _session_email_from_token(token: str) -> str:
    try:
        raw = base64.urlsafe_b64decode(token.encode()).decode()
        email, ts, sig = raw.split("|", 2)
        payload = f"{email}|{ts}"
        expected = hmac.new(APP_SESSION_SECRET.encode(), payload.encode(), hashlib.sha256).hexdigest()
        if hmac.compare_digest(sig, expected):
            return (email or "").strip().lower()
    except Exception:
        return ""
    return ""


def _is_authenticated(request: Request) -> bool:
    token = request.cookies.get(APP_SESSION_COOKIE, "")
    if not token:
        return False
    email = _session_email_from_token(token)
    if not email:
        return False
    return email == _current_auth_email() or _user_exists(email)


@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    path = request.url.path or "/"
    if path == "/":
        return await call_next(request)

    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)

    if any(path.startswith(p) for p in PROTECTED_PREFIXES):
        if not _is_authenticated(request):
            wants_html = "text/html" in (request.headers.get("accept", ""))
            if wants_html:
                return RedirectResponse(url="/login", status_code=303)
            return JSONResponse({"detail": "Authentication required"}, status_code=401)

    return await call_next(request)


def _db_conn():
    if not psycopg2:
        return None
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        log_event(f"DB_CONNECT_FAIL | {e}")
        return None


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def _generate_referral_code() -> str:
    return f"JL{secrets.token_hex(4).upper()}"


def _ensure_referral_profile(owner_email: str) -> dict:
    email_n = _normalize_email(owner_email)
    conn = _db_conn()
    if not conn or not email_n:
        return {}
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "select owner_email, referral_code from public.referral_profiles where owner_email=%s",
                    (email_n,),
                )
                row = cur.fetchone()
                if row:
                    return {"owner_email": row[0], "referral_code": row[1]}

                for _ in range(10):
                    code = _generate_referral_code()
                    cur.execute("select 1 from public.referral_profiles where referral_code=%s", (code,))
                    if not cur.fetchone():
                        cur.execute(
                            "insert into public.referral_profiles (owner_email, referral_code, updated_at) values (%s,%s,now())",
                            (email_n, code),
                        )
                        return {"owner_email": email_n, "referral_code": code}
    except Exception as e:
        log_event(f"REFERRAL_PROFILE_FAIL | {e}")
    finally:
        conn.close()
    return {}


def _referral_stats(referral_code: str) -> dict:
    conn = _db_conn()
    if not conn or not referral_code:
        return {"clicks": 0, "signups": 0}
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select
                      sum(case when event_type='click' then 1 else 0 end) as clicks,
                      sum(case when event_type='signup' then 1 else 0 end) as signups
                    from public.referral_events
                    where referral_code=%s
                    """,
                    (referral_code,),
                )
                row = cur.fetchone() or (0, 0)
                return {"clicks": int(row[0] or 0), "signups": int(row[1] or 0)}
    except Exception as e:
        log_event(f"REFERRAL_STATS_FAIL | {e}")
        return {"clicks": 0, "signups": 0}
    finally:
        conn.close()


def _record_referral_event(referral_code: str, event_type: str, event_email: str = "", metadata: dict | None = None):
    conn = _db_conn()
    if not conn or not referral_code:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "insert into public.referral_events (referral_code, event_type, event_email, metadata_json) values (%s,%s,%s,%s)",
                    (referral_code, event_type, _normalize_email(event_email), json.dumps(metadata or {})),
                )
    except Exception as e:
        log_event(f"REFERRAL_EVENT_FAIL | {e}")
    finally:
        conn.close()


def _normalize_phone(phone: str) -> str:
    return re.sub(r"[^+\d]", "", (phone or "").strip())


def _generate_candidate_id(conn) -> str:
    # Candidate IDs must start with 301 and be 10 digits total.
    for _ in range(50):
        cid = "301" + "".join(random.choice("0123456789") for _ in range(7))
        with conn.cursor() as cur:
            cur.execute("select 1 from public.screening_candidates where candidate_id=%s", (cid,))
            if not cur.fetchone():
                return cid
    return "301" + str(int(time.time()))[-7:]


def _upsert_candidate(full_name: str, email: str, phone_number: str = "", linkedin_profile: str = "", skill_mapping: dict | None = None, assigned_agent_email: str = "") -> dict:
    email_n = _normalize_email(email)
    phone_n = _normalize_phone(phone_number)
    if not email_n:
        return {}
    conn = _db_conn()
    if not conn:
        return {}
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute("select candidate_id from public.screening_candidates where email=%s", (email_n,))
                row = cur.fetchone()
                cid = row[0] if row else _generate_candidate_id(conn)
                cur.execute(
                    """
                    insert into public.screening_candidates (
                      candidate_id, full_name, email, phone_number, linkedin_profile, skill_mapping_json, assigned_agent_email, status, updated_at
                    ) values (%s,%s,%s,%s,%s,%s,%s,'initialized',now())
                    on conflict (email) do update set
                      full_name=excluded.full_name,
                      phone_number=excluded.phone_number,
                      linkedin_profile=excluded.linkedin_profile,
                      skill_mapping_json=excluded.skill_mapping_json,
                      assigned_agent_email=excluded.assigned_agent_email,
                      updated_at=now()
                    returning candidate_id
                    """,
                    (
                        cid,
                        (full_name or "").strip() or "Unknown Candidate",
                        email_n,
                        phone_n,
                        (linkedin_profile or "").strip(),
                        json.dumps(skill_mapping or {}),
                        (assigned_agent_email or "").strip() or _current_auth_email(),
                    ),
                )
                out = cur.fetchone()
                candidate_id = (out[0] if out else cid)
                _log_candidate_activity(candidate_id, "candidate_upserted", f"Candidate upserted from profile/resume data for email {email_n}")
                return {"candidate_id": candidate_id, "email": email_n}
    except Exception as e:
        log_event(f"CANDIDATE_UPSERT_FAIL | {e}")
        return {}
    finally:
        conn.close()


def _find_candidate_by_phone(phone: str) -> dict | None:
    phone_n = _normalize_phone(phone)
    if not phone_n:
        return None
    conn = _db_conn()
    if not conn:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                select candidate_id, full_name, email, phone_number, linkedin_profile, assigned_agent_email, last_session_id
                from public.screening_candidates
                where phone_number=%s
                order by updated_at desc
                limit 1
                """,
                (phone_n,),
            )
            r = cur.fetchone()
            if not r:
                return None
            return {
                "candidate_id": r[0], "full_name": r[1], "email": r[2], "phone_number": r[3],
                "linkedin_profile": r[4], "assigned_agent_email": r[5], "last_session_id": r[6]
            }
    except Exception as e:
        log_event(f"CANDIDATE_LOOKUP_PHONE_FAIL | {e}")
        return None
    finally:
        conn.close()


def _log_candidate_activity(candidate_id: str, event_type: str, details: str = "", session_id: str = "", call_sid: str = ""):
    if not candidate_id or not event_type:
        return
    conn = _db_conn()
    if not conn:
        return
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    insert into public.screening_candidate_activity (candidate_id, session_id, call_sid, event_type, details)
                    values (%s,%s,%s,%s,%s)
                    """,
                    (candidate_id, session_id or None, call_sid or None, event_type, (details or "")[:2000]),
                )
    except Exception as e:
        log_event(f"CANDIDATE_ACTIVITY_LOG_FAIL | {e}")
    finally:
        conn.close()


def _ensure_candidate_for_session(session_id: str, to_number: str = "") -> str:
    s = INTERVIEW_SESSIONS.get(session_id) or {}
    existing = (s.get("candidate_id") or "").strip()
    if existing:
        return existing

    ci = _extract_contact_info(s.get("resume", "") or "")
    full_name = (ci.get("full_name") or s.get("candidate_name") or "Unknown Candidate").strip()
    email = _normalize_email(ci.get("email") or "")
    phone = _normalize_phone(ci.get("phone") or to_number or "")
    linkedin = (ci.get("linkedin") or "").strip()

    # Ensure we always have an email key to avoid losing records.
    if not email:
        base = (phone or session_id or uuid.uuid4().hex[:10]).replace("+", "")
        email = f"candidate-{base[:20]}@joblynk.local"

    up = _upsert_candidate(
        full_name=full_name,
        email=email,
        phone_number=phone,
        linkedin_profile=linkedin,
        skill_mapping={"job_title": s.get("job_title", "")},
        assigned_agent_email=_current_auth_email(),
    )
    cid = (up.get("candidate_id") or "").strip()
    if cid:
        s["candidate_id"] = cid
        INTERVIEW_SESSIONS[session_id] = s
        conn = _db_conn()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "update public.screening_candidates set last_session_id=%s, status='screening_in_progress', updated_at=now() where candidate_id=%s",
                            (session_id, cid),
                        )
            finally:
                conn.close()
    return cid


def _restore_session_for_callback(candidate: dict) -> str:
    """Rehydrate an interview session for inbound callback when in-memory session is missing."""
    cid = (candidate or {}).get("candidate_id") or ""
    preferred_sid = (candidate or {}).get("last_session_id") or ""
    if not cid:
        return ""

    conn = _db_conn()
    if not conn:
        return ""
    try:
        with conn.cursor() as cur:
            if preferred_sid:
                cur.execute(
                    """
                    select ss.session_id, coalesce(ss.job_id,''), coalesce(ss.job_title,''), coalesce(j.job_description,''),
                           coalesce(c.full_name,''), coalesce(c.email,''), coalesce(c.phone_number,'')
                    from public.screening_sessions ss
                    left join public.screening_jobs j on j.job_id = ss.job_id
                    left join public.screening_candidates c on c.candidate_id = ss.candidate_id
                    where ss.session_id=%s and ss.candidate_id=%s
                    limit 1
                    """,
                    (preferred_sid, cid),
                )
                row = cur.fetchone()
            else:
                row = None

            if not row:
                cur.execute(
                    """
                    select ss.session_id, coalesce(ss.job_id,''), coalesce(ss.job_title,''), coalesce(j.job_description,''),
                           coalesce(c.full_name,''), coalesce(c.email,''), coalesce(c.phone_number,'')
                    from public.screening_sessions ss
                    left join public.screening_jobs j on j.job_id = ss.job_id
                    left join public.screening_candidates c on c.candidate_id = ss.candidate_id
                    where ss.candidate_id=%s
                    order by ss.updated_at desc
                    limit 1
                    """,
                    (cid,),
                )
                row = cur.fetchone()

            if not row:
                return ""

            sid, job_id, job_title, job_description, full_name, email, phone = row

            # Try to load resume text from latest upload for this session.
            resume_text = ""
            try:
                cur.execute(
                    """
                    select coalesce(stored_path,'')
                    from public.screening_resume_uploads
                    where session_id=%s
                    order by created_at desc
                    limit 1
                    """,
                    (sid,),
                )
                rr = cur.fetchone()
                if rr and rr[0] and os.path.exists(rr[0]):
                    with open(rr[0], 'rb') as f:
                        raw = f.read()
                    class DummyUpload:
                        filename = rr[0]
                    resume_text = _extract_text_from_resume_upload(DummyUpload(), raw) or ""
            except Exception:
                pass

            plan = _generate_candidate_questions(job_description or "", resume_text or "")
            INTERVIEW_SESSIONS[sid] = {
                "status": "ready",
                "ready": True,
                "start_triggered": True,
                "job_description": job_description or "",
                "resume": resume_text or "",
                "job_title": job_title or "this position",
                "job_id": job_id or "",
                "candidate_name": (full_name or "").strip(),
                "candidate_phone": _normalize_phone(phone or ""),
                "candidate_email": _normalize_email(email or ""),
                "skills": extract_skills(job_description or "", resume_text or ""),
                "fit_evaluation": "Pending skill mapping...",
                "plan": plan,
                "current_idx": 0,
                "current_question": plan[0] if plan else "Could you share a quick summary of your relevant experience?",
                "completed_questions": [],
                "scores": [],
                "clarifications": 0,
                "started": False,
                "completed": False,
                "call_in_progress": True,
                "last_call_status": "inbound_callback",
                "recommendation": "",
                "calls": [],
                "candidate_id": cid,
                "created_at": _now(),
                "intro_phase": "callback_confirm",
                "callback_received": True,
            }
            return sid
    except Exception as e:
        log_event(f"CALLBACK_RESTORE_FAIL | {e}")
        return ""
    finally:
        conn.close()


def init_db():
    conn = _db_conn()
    if not conn:
        return False
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    create table if not exists public.screening_jobs (
                      job_id text primary key,
                      title text not null,
                      job_description text not null,
                      created_at timestamptz not null default now()
                    );
                    create table if not exists public.screening_resume_uploads (
                      upload_id text primary key,
                      session_id text,
                      original_filename text,
                      stored_path text not null,
                      content_type text,
                      size_bytes bigint,
                      created_at timestamptz not null default now()
                    );
                    create table if not exists public.screening_candidate_assessments (
                      assessment_id text primary key,
                      resume_upload_id text not null,
                      job_description text not null,
                      questions_json text not null,
                      answers_json text not null,
                      summary text not null,
                      created_at timestamptz not null default now()
                    );
                    create table if not exists public.screening_agent_profiles (
                      profile_id int primary key,
                      agent_name text not null,
                      display_name text not null,
                      role text not null,
                      company text not null,
                      work_email text not null,
                      phone text not null,
                      timezone text not null,
                      location text not null,
                      department text not null,
                      date_of_joining date,
                      bio text not null,
                      updated_at timestamptz not null default now()
                    );
                    create table if not exists public.screening_candidates (
                      candidate_id char(10) primary key,
                      full_name text not null,
                      email text not null unique,
                      phone_number text,
                      linkedin_profile text,
                      skill_mapping_json text not null default '{}',
                      assigned_agent_email text,
                      status text not null default 'initialized',
                      last_session_id text,
                      callback_received_at timestamptz,
                      screening_completed_at timestamptz,
                      last_summary text,
                      updated_at timestamptz not null default now(),
                      created_at timestamptz not null default now()
                    );
                    create table if not exists public.screening_calls (
                      call_sid text primary key,
                      candidate_id char(10),
                      session_id text,
                      direction text,
                      from_number text,
                      to_number text,
                      call_status text,
                      provider_used text,
                      provider_reason text,
                      created_at timestamptz not null default now(),
                      updated_at timestamptz not null default now()
                    );
                    create table if not exists public.screening_sessions (
                      session_id text primary key,
                      candidate_id char(10),
                      job_id text,
                      job_title text,
                      created_at timestamptz not null default now(),
                      updated_at timestamptz not null default now()
                    );
                    alter table if exists public.screening_calls add column if not exists provider_used text;
                    alter table if exists public.screening_calls add column if not exists provider_reason text;
                    create table if not exists public.screening_candidate_activity (
                      activity_id bigserial primary key,
                      candidate_id char(10) not null,
                      session_id text,
                      call_sid text,
                      event_type text not null,
                      details text,
                      created_at timestamptz not null default now()
                    );
                    create table if not exists public.referral_profiles (
                      id bigserial primary key,
                      owner_email text not null unique,
                      referral_code text not null unique,
                      created_at timestamptz not null default now(),
                      updated_at timestamptz not null default now()
                    );
                    create table if not exists public.referral_events (
                      id bigserial primary key,
                      referral_code text not null,
                      event_type text not null,
                      event_email text,
                      metadata_json text not null default '{}',
                      created_at timestamptz not null default now()
                    );
                    create index if not exists idx_referral_events_code on public.referral_events(referral_code);
                    """
                )
        return True
    except Exception as e:
        log_event(f"DB_INIT_FAIL | {e}")
        return False
    finally:
        conn.close()


def _validate_required():
    missing = []
    for key, value in {
        "TWILIO_ACCOUNT_SID": TWILIO_ACCOUNT_SID,
        "TWILIO_AUTH_TOKEN": TWILIO_AUTH_TOKEN,
        "TWILIO_PHONE_NUMBER": TWILIO_PHONE_NUMBER,
        "PUBLIC_BASE_URL": PUBLIC_BASE_URL,
        "ELEVENLABS_API_KEY": ELEVENLABS_API_KEY,
    }.items():
        if not value:
            missing.append(key)
    if missing:
        raise HTTPException(status_code=500, detail=f"Missing env vars: {', '.join(missing)}")


def verify_call_api_key(x_api_key: str | None):
    if not CALL_API_KEY:
        return
    if not x_api_key:
        raise HTTPException(status_code=401, detail="Missing x-api-key")
    if not hmac.compare_digest(x_api_key, CALL_API_KEY):
        raise HTTPException(status_code=403, detail="Invalid x-api-key")


async def validate_twilio_request(request: Request):
    if not VALIDATE_TWILIO_SIGNATURE:
        return
    signature = request.headers.get("X-Twilio-Signature", "")
    validator = RequestValidator(TWILIO_AUTH_TOKEN)
    form = await request.form()
    ok = validator.validate(str(request.url), dict(form), signature)
    if not ok:
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")


def _classify_response(text: str, current_question: str) -> str:
    t = (text or "").lower()
    if len(t.split()) < 4:
        return "Unclear"
    if any(x in t for x in ["not sure", "i don't know", "dont know"]):
        return "Incorrect"
    if "hard link" in current_question.lower() and "soft" in t and ("inode" in t or "symbolic" in t or "symlink" in t):
        return "Correct"
    if any(x in t for x in ["maybe", "i think", "kind of", "probably"]):
        return "Partially correct"
    return "Partially correct"


def extract_skills(jd: str, resume: str) -> list[str]:
    text = f"{jd} {resume}".lower()
    skills = []
    for s in ["linux administration", "unix", "process management", "troubleshooting", "shell scripting", "production operations", "networking", "security"]:
        if s in text:
            skills.append(s)
    return skills or ["linux administration", "shell scripting", "troubleshooting"]


def build_question_plan(skills: list[str]) -> list[str]:
    bank = {
        "process management": "In Linux production, how would you identify and safely stop a runaway process?",
        "shell scripting": "How would you write a shell script to monitor disk usage and alert at threshold?",
        "troubleshooting": "Walk me through your incident troubleshooting flow for a degraded Linux service.",
        "production operations": "How do you perform a safe service restart in production with minimal impact?",
        "unix": "What is the difference between a hard link and soft link, and when would you use each?",
        "linux administration": "How would you diagnose high load average on a Linux server?",
        "networking": "A service is reachable by ping but not by TCP port. How do you debug it?",
        "security": "What SSH hardening controls do you apply on internet-facing Linux hosts?",
    }
    plan = []
    for s in skills:
        q = bank.get(s)
        if q and q not in plan:
            plan.append(q)
    return plan[:8] if plan else [bank["linux administration"], bank["troubleshooting"], bank["shell scripting"]]


def build_reply_text(user_text: str, call_sid: str = "") -> str:
    user_text = (user_text or "").strip()
    if not user_text:
        return "I didn't catch that. Could you please repeat?"

    lower = user_text.lower()
    state = CONVERSATION_STATE.setdefault(
        call_sid or "default",
        {
            "phase": "analyze",
            "skills": [],
            "plan": [],
            "current_idx": 0,
            "current_question": "",
            "completed_questions": [],
            "scores": [],
            "clarifications": 0,
            "resume_text": "",
            "job_description": "",
            "last_user": "",
            "last_reply": "",
        },
    )

    if any(k in lower for k in ["start over", "new topic"]):
        state.update({
            "phase": "analyze", "skills": [], "plan": [], "current_idx": 0,
            "current_question": "", "completed_questions": [], "scores": [], "clarifications": 0,
            "resume_text": "", "job_description": ""
        })
        return "Understood. Let’s start over. Please share the job description and candidate resume summary for Softwise Solutions screening."

    if state["phase"] == "analyze":
        state["resume_text"] += f" {user_text}"
        if "job description" in lower or "resume" in lower or len(state["resume_text"].split()) > 20:
            state["skills"] = ["Linux administration", "Shell scripting", "Networking", "Troubleshooting", "Security"]
            state["phase"] = "plan"
            return "Analysis complete. I identified the key skills and experience areas. I will now build the interview plan."
        return "Please provide the job description and candidate resume summary so I can extract required skills."

    if state["phase"] == "plan":
        state["plan"] = [
            "Linux process and service management",
            "Filesystem and permissions",
            "Shell scripting and automation",
            "Networking diagnostics",
            "Production troubleshooting",
            "Security and hardening",
        ]
        state["phase"] = "ask"
        return "Interview plan is ready. First question: explain how you would identify and safely stop a runaway process on a Linux production server."

    if state["phase"] in ["ask", "evaluate", "clarify"]:
        if not state["current_question"]:
            questions = [
                "Explain how you would identify and safely stop a runaway process on a Linux production server.",
                "What is the difference between a hard link and a soft link, and when would you use each?",
                "How would you troubleshoot high CPU usage on a Linux host?",
                "Write the logic of a shell script to monitor disk usage and alert on threshold.",
                "How do you debug a service that is reachable by ping but not by TCP port?",
                "What hardening steps would you apply to SSH on a public Linux server?",
            ]
            idx = min(state["current_idx"], len(questions) - 1)
            state["current_question"] = questions[idx]
            state["phase"] = "evaluate"
            return state["current_question"]

        if any(k in lower for k in ["hint", "help"]):
            return "Hint: structure your answer as command sequence, validation checks, and safety considerations."

        if any(k in lower for k in ["full answer", "give answer"]):
            ans = "Use ps/top to identify PID, verify ownership and impact, send SIGTERM first, confirm shutdown, then SIGKILL only if needed, and validate service recovery."
            state["completed_questions"].append(state["current_question"])
            state["scores"].append("Incorrect")
            state["current_idx"] += 1
            state["current_question"] = ""
            state["clarifications"] = 0
            state["phase"] = "ask"
            return ans

        cls = _classify_response(user_text, state["current_question"])
        if cls == "Unclear":
            state["clarifications"] += 1
            if state["clarifications"] >= 2:
                cls = "Incorrect"
            else:
                return "Could you clarify with the exact commands and order you would use?"

        state["completed_questions"].append(state["current_question"])
        state["scores"].append(cls)
        state["current_idx"] += 1
        state["current_question"] = ""
        state["clarifications"] = 0

        if state["current_idx"] >= 6:
            state["phase"] = "summary"
        else:
            state["phase"] = "ask"

        if state["phase"] == "summary":
            c = state["scores"].count("Correct")
            p = state["scores"].count("Partially correct")
            i = state["scores"].count("Incorrect")
            return f"Interview completed. Summary: Correct {c}, Partially correct {p}, Incorrect {i}. Strengths: Linux fundamentals and operational reasoning. Recommendation: improve troubleshooting depth and concise command-level explanations."

        return "Thank you. Next question: " + build_reply_text("next", call_sid)

    return "Please continue with your response."


def _cleanup_tts_cache() -> None:
    try:
        files = sorted(AUDIO_DIR.glob("tts_*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
        now_ts = time.time()
        max_age_secs = max(1, TTS_CACHE_MAX_DAYS) * 86400

        removed = 0
        # Remove files older than max age.
        for p in files:
            if now_ts - p.stat().st_mtime > max_age_secs:
                try:
                    p.unlink(missing_ok=True)
                    removed += 1
                except Exception:
                    pass

        # Refresh list and enforce max file count.
        files = sorted(AUDIO_DIR.glob("tts_*.mp3"), key=lambda p: p.stat().st_mtime, reverse=True)
        for p in files[max(1, TTS_CACHE_MAX_FILES):]:
            try:
                p.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass

        if removed:
            log_event(f"TTS_CACHE_CLEANUP removed={removed}")
    except Exception as e:
        log_event(f"TTS_CACHE_CLEANUP_FAIL | {e}")


def synthesize_tts(text: str, voice_id: str | None = None) -> str:
    if not ELEVENLABS_API_KEY:
        raise HTTPException(status_code=500, detail="Missing ELEVENLABS_API_KEY")

    # light phrasing cleanup for more natural spoken cadence
    spoken = (text or "").replace("...", ". ").replace("  ", " ").strip()

    vid = (voice_id or ELEVENLABS_VOICE_ID or "").strip() or ELEVENLABS_VOICE_ID

    # deterministic local cache to reduce repeated ElevenLabs credit usage
    cache_key = hashlib.sha1(f"{vid}|{spoken}".encode("utf-8")).hexdigest()[:20]
    out_name = f"tts_{cache_key}.mp3"
    out_path = AUDIO_DIR / out_name
    if out_path.exists() and out_path.stat().st_size > 0:
        return f"{PUBLIC_BASE_URL}/audio/{out_name}"

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}"
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    # Tune for warmer, more natural recruiter tone
    payload = {
        "text": spoken,
        "model_id": "eleven_turbo_v2_5",
        "voice_settings": {
            "stability": 0.62,
            "similarity_boost": 0.84,
            "style": 0.58,
            "use_speaker_boost": True,
        },
    }

    r = requests.post(url, headers=headers, json=payload, timeout=60)
    if r.status_code >= 300:
        raise HTTPException(status_code=500, detail=f"ElevenLabs error: {r.status_code} {r.text}")

    out_path.write_bytes(r.content)
    return f"{PUBLIC_BASE_URL}/audio/{out_name}"


def _resolve_agent_profile(profile_key: str | None) -> dict:
    k = (profile_key or "adam").strip().lower()
    return AGENT_VOICE_PROFILES.get(k, AGENT_VOICE_PROFILES["adam"])


def _speak_or_fallback(vr: VoiceResponse, text: str, voice_id: str | None = None, fallback_voice: str | None = None):
    try:
        audio_url = synthesize_tts(text, voice_id=voice_id)
        vr.play(audio_url)
    except Exception as e:
        log_event(f"TTS_FALLBACK | {e}")
        vr.say((text or "").strip()[:800], voice=(fallback_voice or TWILIO_FALLBACK_VOICE), language="en-US")


def _livekit_orchestrator() -> LiveKitVoiceOrchestrator | None:
    if not LiveKitVoiceOrchestrator:
        return None
    try:
        return LiveKitVoiceOrchestrator.from_env()
    except Exception as e:
        log_event(f"LIVEKIT_ORCHESTRATOR_UNAVAILABLE | {e}")
        return None


def _mark_call_provider(call_sid: str, provider_used: str, reason: str = "") -> None:
    sid = (call_sid or "").strip()
    if not sid:
        return
    CALL_PROVIDER_TRACK[sid] = {"provider_used": provider_used, "provider_reason": reason, "updated_at": _now()}
    try:
        conn = _db_conn()
        if conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        update public.screening_calls
                        set provider_used=%s,
                            provider_reason=%s,
                            updated_at=now()
                        where call_sid=%s
                        """,
                        (provider_used or None, reason or None, sid),
                    )
            conn.close()
    except Exception:
        pass


def _provider_mode() -> str:
    m = (VOICE_PROVIDER or "legacy").lower().strip()
    return m if m in {"legacy", "livekit", "auto"} else "legacy"


def _is_livekit_ready() -> bool:
    if not check_livekit_health:
        return False
    try:
        return bool((check_livekit_health() or {}).get("ok"))
    except Exception:
        return False


def _looks_like_voicemail_greeting(text: str) -> bool:
    t = (text or "").lower().strip()
    if not t:
        return False
    patterns = [
        "leave your name", "leave a message", "at the tone", "beep", "mailbox",
        "can't take your call", "cannot take your call", "not available", "get back to you",
    ]
    return any(p in t for p in patterns)


def _generate_text_reply_with_fallback(user_text: str, call_sid: str = "") -> str:
    """Generate reply using configured provider with safe fallback to legacy."""
    mode = _provider_mode()

    if mode == "legacy":
        _mark_call_provider(call_sid, "legacy", "mode_legacy")
        return build_reply_text(user_text, call_sid)

    if mode in {"livekit", "auto"}:
        if _is_livekit_ready():
            orch = _livekit_orchestrator()
            if orch:
                try:
                    out = orch.generate_text_reply(prompt=user_text or "", context={"call_sid": call_sid})
                    if out:
                        _mark_call_provider(call_sid, "livekit", f"mode_{mode}")
                        return out
                except Exception as e:
                    log_event(f"LIVEKIT_REPLY_FAIL | {e}")
                    _mark_call_provider(call_sid, "legacy", f"livekit_error:{str(e)[:120]}")
                    if mode == "livekit":
                        # explicit livekit mode still degrades gracefully to keep call continuity
                        return build_reply_text(user_text, call_sid)

    _mark_call_provider(call_sid, "legacy", f"fallback_from_{mode}")
    return build_reply_text(user_text, call_sid)


@app.get("/", response_class=HTMLResponse)
def homepage():
    html_doc = """
<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>Joblynk Screening Platform</title>
<style>
body{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;color:#0f172a;background:#eef4ff}
.top{background:#0b5fff;color:#fff;padding:14px 20px}
.topin{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.nav a{color:#fff;text-decoration:none;font-weight:700;margin-left:12px}
.logo{width:34px;height:34px;border-radius:8px;background:#fff;color:#0b5fff;display:flex;align-items:center;justify-content:center;font-weight:900}
.hero{max-width:1100px;margin:16px auto;padding:28px;border-radius:16px;color:#fff;background:linear-gradient(rgba(8,36,99,.72),rgba(8,36,99,.72)),url('https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=1600&q=80') center/cover;box-shadow:0 10px 28px rgba(0,51,128,.25)}
.hero h1{margin:0 0 8px 0;font-size:32px}.hero p{max-width:760px;opacity:.96}
.btn{display:inline-block;padding:11px 16px;border-radius:10px;background:#fff;color:#0b5fff;text-decoration:none;font-weight:800}
.wrap{max-width:1100px;margin:0 auto;padding:0 16px 20px}
.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
.card{background:#fff;border:1px solid #d7e5ff;border-radius:14px;padding:14px;box-shadow:0 8px 20px rgba(0,51,102,.06)}
.card h3{margin:0 0 8px 0;color:#0a3f9a}.small{color:#5b6b83;font-size:13px;line-height:1.6}
.footer{max-width:1100px;margin:10px auto 20px;color:#5b6b83;font-size:13px;padding:0 16px}
@media(max-width:900px){.grid{grid-template-columns:1fr}.hero h1{font-size:24px}.nav a{margin-left:8px;font-size:14px}}
</style></head><body>
<header class='top'><div class='topin'><div style='display:flex;align-items:center;gap:10px'><div class='logo'>AL</div><b>Joblynk Screening Platform</b></div><nav class='nav'><a href='/'>Home</a><a href='/login'>Login</a><a href='/contact-us'>Contact Us</a></nav></div></header>
<section class='hero'><h1>Enterprise AI Screening</h1><p>Structured candidate screening with robust persistence, voice automation, and production-grade reliability.</p><a class='btn' href='/login'>Login to Continue</a></section>
<div class='wrap'><div class='grid'>
<div class='card'><img src='https://images.unsplash.com/photo-1486406146926-c627a92ad1ab?auto=format&fit=crop&w=900&q=80' style='width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:8px'/><h3>Screening Operations</h3><div class='small'>Dashboard, InstantScreen, Candidates, and Profile flows unified for recruiters.</div></div>
<div class='card'><img src='https://images.unsplash.com/photo-1518770660439-4636190af475?auto=format&fit=crop&w=900&q=80' style='width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:8px'/><h3>Voice Intelligence</h3><div class='small'>LiveKit + legacy fallback routing with call-level provider tracking and auditability.</div></div>
<div class='card'><img src='https://images.unsplash.com/photo-1551288049-bebda4e38f71?auto=format&fit=crop&w=900&q=80' style='width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:8px'/><h3>Data Integrity</h3><div class='small'>Persistent candidates, calls, timelines, and activity logs with callback handling.</div></div>
<div class='card'><img src='https://images.unsplash.com/photo-1521737711867-e3b97375f902?auto=format&fit=crop&w=900&q=80' style='width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:8px'/><h3>Deployment</h3><div class='small'>CI-driven cloud deployment and hardened runtime controls for enterprise operations.</div></div>
<div class='card'><img src='https://images.unsplash.com/photo-1454165804606-c3d57bc86b40?auto=format&fit=crop&w=900&q=80' style='width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:8px'/><h3>Cost Controls</h3><div class='small'>Deterministic local TTS caching with cleanup policies to reduce recurring credit burn.</div></div>
<div class='card'><img src='https://images.unsplash.com/photo-1563013544-824ae1b704d3?auto=format&fit=crop&w=900&q=80' style='width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:8px'/><h3>Security</h3><div class='small'>Internal routes protected by authentication, with clean public entry points.</div></div>
</div></div>
<div class='footer'>© Joblynk · Secure and auditable screening platform.</div>
</body></html>
"""
    return HTMLResponse(html_doc, headers={"Cache-Control": "no-store"})


@app.get('/contact-us', response_class=HTMLResponse)
def contact_us_page(sent: str = ""):
    notice = "Thanks! Your message has been received." if sent == "1" else ""
    html_doc = """
<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>Contact Us - Joblynk</title>
<style>
body{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;background:#eef4ff;color:#0f172a}
.top{background:#0b5fff;color:#fff;padding:14px 20px}
.topin{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap}
.nav a{color:#fff;text-decoration:none;font-weight:700;margin-left:12px}
.wrap{max-width:1100px;margin:0 auto;padding:16px}
.hero{border-radius:14px;padding:20px;color:#fff;background:linear-gradient(rgba(8,36,99,.72),rgba(8,36,99,.72)),url('https://images.unsplash.com/photo-1552581234-26160f608093?auto=format&fit=crop&w=1600&q=80') center/cover}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:14px}
.card{background:#fff;border:1px solid #d7e5ff;border-radius:14px;padding:14px;box-shadow:0 8px 20px rgba(0,51,102,.06)}
label{font-size:13px;font-weight:700;color:#29415f} input,textarea{width:100%;padding:10px;border:1px solid #bfd3f8;border-radius:10px;margin-top:6px;margin-bottom:10px}
button{background:#0b5fff;color:#fff;border:none;border-radius:10px;padding:10px 14px;font-weight:700}
.small{font-size:13px;color:#5b6b83;line-height:1.6}
@media(max-width:900px){.grid{grid-template-columns:1fr}}
</style></head><body>
<header class='top'><div class='topin'><div style='display:flex;align-items:center;gap:10px'><div style='width:34px;height:34px;border-radius:8px;background:#fff;color:#0b5fff;display:flex;align-items:center;justify-content:center;font-weight:900'>AL</div><b>Joblynk Screening Platform</b></div><nav class='nav'><a href='/'>Home</a><a href='/login'>Login</a><a href='/contact-us'>Contact Us</a></nav></div></header>
<div class='wrap'>
<div class='hero'><h1 style='margin:0 0 8px 0'>Contact Us</h1><div>Talk to the Joblynk team for onboarding, integrations, and enterprise rollout support.</div></div>
<div class='grid'>
  <div class='card'><img src='https://images.unsplash.com/photo-1516383607781-913a19294fd1?auto=format&fit=crop&w=1200&q=80' style='width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:8px'/><h3 style='margin-top:0;color:#0a3f9a'>Send a Message</h3><div style='color:#166534;font-size:13px;margin-bottom:8px'>__NOTICE__</div><form method='POST' action='/contact-us'><label>Name</label><input name='name' required placeholder='Your name'/><label>Email</label><input name='email' type='email' required placeholder='you@company.com'/><label>Message</label><textarea name='message' rows='5' required placeholder='Tell us what you need...'></textarea><button type='submit'>Submit</button></form></div>
  <div class='card'><img src='https://images.unsplash.com/photo-1525182008055-f88b95ff7980?auto=format&fit=crop&w=1200&q=80' style='width:100%;height:130px;object-fit:cover;border-radius:10px;margin-bottom:8px'/><h3 style='margin-top:0;color:#0a3f9a'>Contact Details</h3><div class='small'><b>Email:</b> support@joblynk.ai<br/><b>Hours:</b> Mon–Fri, 9:00 AM – 6:00 PM<br/><b>Use Cases:</b> Resume screening, voice interviews, candidate pipelines, and workflow automation.</div></div>
</div>
</div>
</body></html>
"""
    html_doc = html_doc.replace("__NOTICE__", html.escape(notice))
    return HTMLResponse(html_doc, headers={"Cache-Control": "no-store"})


@app.post('/contact-us')
def contact_us_submit(name: str = Form(...), email: str = Form(...), message: str = Form(...)):
    n = (name or '').strip()
    e = (email or '').strip()
    m = (message or '').strip()
    log_event(f"CONTACT_US from={e} name={n} msg={m[:240]}")
    return RedirectResponse(url='/contact-us?sent=1', status_code=303)


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, err: str = "", msg: str = ""):
    if _is_authenticated(request):
        return RedirectResponse(url="/ui", status_code=303)
    message = "Invalid email or password." if err == "1" else ("Password reset email sent." if msg == "sent" else "")
    html_doc = f"""
<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/><title>Login - Joblynk</title>
<style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;margin:0;background:#f6f8ff;color:#0f172a}}
.shell{{max-width:1180px;margin:16px auto;padding:0 16px}}
.nav{{background:#fff;border:1px solid #e8ecff;border-radius:999px;padding:10px 14px;display:flex;justify-content:space-between;align-items:center;box-shadow:0 8px 30px rgba(26,44,93,.08)}}
.brand{{display:flex;align-items:center;gap:10px;font-weight:800}}
.logo{{width:34px;height:34px;border-radius:999px;background:#0b5fff;color:#fff;display:flex;align-items:center;justify-content:center;font-weight:900}}
.links a{{text-decoration:none;color:#344a77;font-weight:700;font-size:14px;margin-left:14px}}
.hero{{margin-top:14px;border-radius:22px;padding:26px;background:linear-gradient(120deg,#e9efff,#f6fbff);border:1px solid #dfe8ff;display:grid;grid-template-columns:1.1fr .9fr;gap:16px}}
.left h1{{margin:0 0 8px;font-size:36px;line-height:1.12;color:#15254d}}
.left p{{margin:0;color:#60759e;line-height:1.7}}
.badge{{display:inline-block;padding:6px 10px;border-radius:999px;background:#edf3ff;border:1px solid #c9d9ff;color:#2150b9;font-size:12px;font-weight:800;margin-bottom:10px}}
.card{{background:#fff;border:1px solid #e5ebff;border-radius:18px;padding:18px;box-shadow:0 12px 28px rgba(31,58,118,.08)}}
label{{display:block;font-size:13px;font-weight:700;color:#33476f;margin-top:10px;margin-bottom:6px}}
input{{width:100%;padding:11px;border:1px solid #cddcfb;border-radius:12px;outline:none}}
input:focus{{border-color:#6c90ff;box-shadow:0 0 0 3px rgba(108,144,255,.18)}}
button{{width:100%;margin-top:12px;background:#0b5fff;color:#fff;border:none;border-radius:12px;padding:11px;font-weight:800;cursor:pointer}}
.err{{min-height:18px;color:#c11f3a;font-size:13px}}
.help{{display:block;margin-top:10px;text-align:right;font-size:12px;color:#4567ad;text-decoration:none}}
@media(max-width:900px){{.hero{{grid-template-columns:1fr}}.left h1{{font-size:30px}}}}
</style></head><body>
<div class='shell'>
  <div class='nav'>
    <div class='brand'><div class='logo'>JL</div><span>Joblynk</span></div>
    <div class='links'><a href='/'>Home</a><a href='/pricing'>Pricing</a><a href='/contact-us'>Contact</a></div>
  </div>
  <div class='hero'>
    <section class='left'>
      <span class='badge'>Talent Platform</span>
      <h1>Welcome back to Joblynk Talent</h1>
      <p>Continue to your talent workspace for voice screening, candidate tracking, and interviewer workflows — all in one project experience.</p>
    </section>
    <section class='card'>
      <h3 style='margin:0 0 6px'>Sign in</h3>
      <div style='font-size:13px;color:#6b7fa6;margin-bottom:8px'>Use your Joblynk credentials to continue.</div>
      <div class='err'>{html.escape(message)}</div>
      <form method='POST' action='/login'>
        <label>Email</label><input type='email' name='email' required placeholder='you@joblynk.ai'/>
        <label>Password</label><input type='password' name='password' required placeholder='Password'/>
        <button type='submit'>Continue</button>
      </form>
      <a class='help' href='/forgot-password'>Forgot password?</a>
    </section>
  </div>
</div>
</body></html>
"""
    return HTMLResponse(html_doc, headers={"Cache-Control": "no-store"})


@app.get("/signup", response_class=HTMLResponse)
def signup_page(status: str = ""):
    target = "/signup?status=created" if status == "created" else ("/signup?status=error" if status == "error" else "/signup")
    return RedirectResponse(url=target, status_code=307)


@app.post("/signup")
def signup_submit(
    request: Request,
    username: str = Form(default=""),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    ref_code: str = Form(default=""),
):
    ip = _request_ip(request)
    if _is_rate_limited(f"signup:{ip}", limit=8, window_seconds=900):
        return RedirectResponse(url="/signup?status=error", status_code=303)

    target = (email or "").strip().lower()
    pwd = password or ""
    cpwd = confirm_password or ""
    if not target or len(pwd) < 10 or pwd != cpwd:
        return RedirectResponse(url="/signup?status=error", status_code=303)

    _upsert_user(target, pwd)
    log_event(f"SIGNUP_CREATED email={target} name={(username or '').strip()[:80]}")

    ref = (ref_code or "").strip().upper()
    if ref:
        conn = _db_conn()
        try:
            if conn:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("select owner_email from public.referral_profiles where referral_code=%s", (ref,))
                        owner = cur.fetchone()
                        if owner and _normalize_email(owner[0]) != target:
                            _record_referral_event(ref, "signup", target, {"source": "talent_signup"})
        except Exception as e:
            log_event(f"REFERRAL_SIGNUP_LINK_FAIL | {e}")
        finally:
            if conn:
                conn.close()

    resp = RedirectResponse(url="/ui", status_code=303)
    resp.set_cookie(APP_SESSION_COOKIE, _session_token(target), httponly=True, samesite="lax", secure=False, path="/")
    return resp


@app.get("/referrals/me")
def referrals_me(request: Request):
    if not _is_authenticated(request):
        return JSONResponse({"detail": "Authentication required"}, status_code=401)
    owner_email = _current_auth_email()
    profile = _ensure_referral_profile(owner_email)
    if not profile:
        return JSONResponse({"detail": "Could not load referral profile"}, status_code=500)
    code = profile.get("referral_code", "")
    base = (PUBLIC_BASE_URL or "").rstrip("/")
    referral_link = f"{base}/talent/r/{code}" if base else f"/talent/r/{code}"
    stats = _referral_stats(code)
    return JSONResponse({
        "owner_email": owner_email,
        "referral_code": code,
        "referral_link": referral_link,
        **stats,
    })


@app.get("/r/{referral_code}")
def referral_redirect(referral_code: str, request: Request):
    code = (referral_code or "").strip().upper()
    conn = _db_conn()
    exists = False
    try:
        if conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("select 1 from public.referral_profiles where referral_code=%s", (code,))
                    exists = bool(cur.fetchone())
    except Exception as e:
        log_event(f"REFERRAL_REDIRECT_LOOKUP_FAIL | {e}")
    finally:
        if conn:
            conn.close()

    if exists:
        _record_referral_event(code, "click", "", {"ip": _request_ip(request)})
        return RedirectResponse(url=f"/signup?ref={code}", status_code=303)
    return RedirectResponse(url="/signup", status_code=303)


@app.get("/forgot-password", response_class=HTMLResponse)
def forgot_password_page(msg: str = ""):
    target = "/forgot-password?msg=sent" if msg == "sent" else "/forgot-password"
    return RedirectResponse(url=target, status_code=307)


@app.post("/forgot-password")
def forgot_password_submit(request: Request, email: str = Form(...)):
    ip = _request_ip(request)
    if _is_rate_limited(f"forgot:{ip}", limit=5, window_seconds=900):
        return RedirectResponse(url="/forgot-password?msg=sent", status_code=303)

    target = (email or "").strip().lower()
    if target == _current_auth_email():
        code = _generate_reset_code()
        PASSWORD_RESET_CODES[target] = {
            "code": code,
            "expires_at": datetime.now(timezone.utc) + timedelta(minutes=20),
            "attempts": 0,
        }
        _send_password_reset_email(target, code)
    return RedirectResponse(url="/forgot-password?msg=sent", status_code=303)


@app.get("/reset-password", response_class=HTMLResponse)
def reset_password_page(err: str = ""):
    target = "/reset-password?err=1" if err == "1" else "/reset-password"
    return RedirectResponse(url=target, status_code=307)


@app.post("/reset-password")
def reset_password_submit(request: Request, email: str = Form(...), code: str = Form(...), password: str = Form(...)):
    ip = _request_ip(request)
    if _is_rate_limited(f"reset:{ip}", limit=10, window_seconds=900):
        return RedirectResponse(url="/reset-password?err=1", status_code=303)

    target = (email or "").strip().lower()
    rec = PASSWORD_RESET_CODES.get(target)
    if not rec or datetime.now(timezone.utc) >= rec.get("expires_at", datetime.now(timezone.utc)):
        return RedirectResponse(url="/reset-password?err=1", status_code=303)

    rec["attempts"] = int(rec.get("attempts", 0)) + 1
    if rec["attempts"] > 8:
        PASSWORD_RESET_CODES.pop(target, None)
        return RedirectResponse(url="/reset-password?err=1", status_code=303)

    if (code or "").strip() != str(rec.get("code", "")):
        return RedirectResponse(url="/reset-password?err=1", status_code=303)

    if len(password or "") < 10:
        return RedirectResponse(url="/reset-password?err=1", status_code=303)

    _save_auth_config(target, password)
    PASSWORD_RESET_CODES.pop(target, None)
    return RedirectResponse(url="/login?msg=sent", status_code=303)


@app.get("/account", response_class=HTMLResponse)
def account_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    return RedirectResponse(url="/profile", status_code=303)


@app.get("/profile", response_class=HTMLResponse)
def profile_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    p = _load_agent_profile()
    saved = request.query_params.get("saved", "")
    msg = "Profile saved successfully." if saved == "1" else ("Could not save profile. Please try again." if saved == "0" else "")
    msg_bg = "#e8fff1" if saved == "1" else "#fff5f5"
    msg_color = "#0f6b3b" if saved == "1" else "#b42318"
    html_doc = f"""
<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/><title>Agent Profile - Joblynk</title>
<style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:linear-gradient(180deg,#eef4ff 0%,#f8fbff 100%);margin:0;color:#0a1f44;overflow-x:hidden}}
.site-header{{background:linear-gradient(90deg,#0b5fff,#0051c8);color:#fff;padding:14px 24px;box-shadow:0 6px 20px rgba(0,51,128,.2)}}
.header-inner{{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}}
.nav a{{color:#fff;text-decoration:none;font-weight:700;margin-left:12px;font-size:13px}}
.burger{{display:none;background:transparent;border:1px solid rgba(255,255,255,.45);color:#fff;border-radius:8px;padding:6px 10px;font-weight:700}}
.brand{{font-size:18px;font-weight:800;line-height:1.2}}
.tag{{font-size:12px;opacity:.9}}
.wrap{{width:min(1100px,100%);max-width:1100px;margin:22px auto;padding:0 16px}}
.card{{background:#fff;border:1px solid #d7e5ff;border-radius:14px;padding:20px;box-shadow:0 10px 28px rgba(0,51,102,.08);min-width:0;overflow:hidden}}
.profile-layout{{display:grid;grid-template-columns:minmax(0,2fr) minmax(0,1fr);gap:14px;align-items:start}}
.stack{{display:grid;gap:14px;min-width:0}}
.grid{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;align-items:start}}
.grid>div{{min-width:0}}
label{{font-size:13px;font-weight:700;color:#29415f}}
input,textarea{{width:100%;max-width:100%;min-width:0;display:block;box-sizing:border-box;padding:10px 11px;border:1px solid #bfd3f8;border-radius:10px;margin-top:6px;margin-bottom:10px}}
textarea{{min-height:100px;resize:vertical}}
.password-grid{{grid-template-columns:1fr}}
.btn{{background:#0b5fff;color:#fff;border:none;border-radius:10px;padding:8px 12px;font-weight:700;cursor:pointer;min-width:170px}}
form .btn{{margin-top:8px}}
form .grid > div{{padding-bottom:4px}}
@media (max-width: 900px){{
  .site-header{{padding:12px}}
  .burger{{display:inline-flex;align-items:center;justify-content:center}}
  .nav{{position:fixed;top:0;right:-260px;width:240px;height:100vh;background:#0b5fff;padding:70px 14px 14px;display:flex;flex-direction:column;gap:8px;transition:right .25s ease;z-index:20;box-shadow:-8px 0 24px rgba(0,0,0,.2)}}
  .nav.open{{right:0}}
  .nav a{{margin-left:0;font-size:14px;padding:8px 4px}}
  .profile-layout{{grid-template-columns:1fr}}
  .grid{{grid-template-columns:1fr}}
}}
</style></head><body>
<header class='site-header'><div class='header-inner'><div><div class='brand'>Joblynk Screening Console</div><div class='tag'>Enterprise Interview Workflow</div></div><button id='burgerProfile' class='burger' type='button'>☰</button><div class='nav' id='profileNav'><a href='/dashboard'>Dashboard</a><a href='/ui'>InstantScreen</a><a href='/candidates'>Candidates</a><a href='/profile'>Profile</a><a href='/logout'>Logout</a></div></div></header>
<div class='wrap'><div class='profile-layout'><div class='card'>
<h2 style='margin-top:0'>Agent Profile</h2>
<div style='display:{"block" if msg else "none"};margin:8px 0 14px 0;padding:10px 12px;border:1px solid #d7e5ff;border-radius:10px;background:{msg_bg};color:{msg_color};font-size:13px;font-weight:700'>{html.escape(msg)}</div>
<form method='POST' action='/profile'>
<div class='grid'>
<div><label>Agent Name *</label><input name='agent_name' required value='{html.escape(p.get("agent_name", ""))}'/></div>
<div><label>Display Name *</label><input name='display_name' required value='{html.escape(p.get("display_name", ""))}'/></div>
<div><label>Role *</label><input name='role' required value='{html.escape(p.get("role", ""))}'/></div>
<div><label>Company *</label><input name='company' required value='{html.escape(p.get("company", ""))}'/></div>
<div><label>Work Email *</label><input type='email' name='work_email' required value='{html.escape(p.get("work_email", ""))}'/></div>
<div><label>Phone *</label><input name='phone' required value='{html.escape(p.get("phone", ""))}'/></div>
<div><label>Timezone *</label><input name='timezone' required value='{html.escape(p.get("timezone", ""))}'/></div>
<div><label>Location *</label><input name='location' required value='{html.escape(p.get("location", ""))}'/></div>
<div><label>Department *</label><input name='department' required value='{html.escape(p.get("department", ""))}'/></div>
<div><label>Date of Joining *</label><input type='date' name='date_of_joining' required value='{html.escape(p.get("date_of_joining", ""))}'/></div>
</div>
<label>Bio *</label><textarea name='bio' required>{html.escape(p.get("bio", ""))}</textarea>
<button class='btn' type='submit'>Save Profile</button>
</form>
</div>
<div class='stack'>
<div class='card'>
<h2 style='margin-top:0'>Change Password</h2>
<form method='POST' action='/profile/password'>
<div class='grid password-grid'>
<div><label>Current Password *</label><input type='password' name='current_password' required /></div>
<div><label>New Password * (min 10 chars)</label><input type='password' name='new_password' required /></div>
</div>
<button class='btn' type='submit'>Update Password</button>
</form>
</div>
<div class='card'>
<h3 style='margin:0 0 8px 0;color:#0a3f9a'>Profile Checklist</h3>
<div style='font-size:13px;color:#5b6b83;line-height:1.5'>Keep this profile current for enterprise readiness: agent identity, contact info, timezone, and department ownership.</div>
</div>
</div></div></div>
<script>
const burgerProfile=document.getElementById('burgerProfile');
const profileNav=document.getElementById('profileNav');
if(burgerProfile && profileNav){{
  burgerProfile.addEventListener('click',(e)=>{{ e.stopPropagation(); profileNav.classList.toggle('open'); }});
  profileNav.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>profileNav.classList.remove('open')));
  document.addEventListener('click',(e)=>{{
    if(!profileNav.classList.contains('open')) return;
    const t=e.target;
    if(t instanceof Node && !profileNav.contains(t) && t!==burgerProfile) profileNav.classList.remove('open');
  }});
}}
</script>
</body></html>
"""
    return HTMLResponse(html_doc, headers={"Cache-Control": "no-store"})


@app.post("/profile")
def profile_submit(
    request: Request,
    agent_name: str = Form(...),
    display_name: str = Form(...),
    role: str = Form(...),
    company: str = Form(...),
    work_email: str = Form(...),
    phone: str = Form(...),
    timezone: str = Form(...),
    location: str = Form(...),
    department: str = Form(...),
    date_of_joining: str = Form(...),
    bio: str = Form(...),
):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    profile = {
        "agent_name": (agent_name or "").strip(),
        "display_name": (display_name or "").strip(),
        "role": (role or "").strip(),
        "company": (company or "").strip(),
        "work_email": (work_email or "").strip(),
        "phone": (phone or "").strip(),
        "timezone": (timezone or "").strip(),
        "location": (location or "").strip(),
        "department": (department or "").strip(),
        "date_of_joining": (date_of_joining or "").strip(),
        "bio": (bio or "").strip(),
    }
    ok = _save_agent_profile(profile)
    return RedirectResponse(url="/profile?saved=1" if ok else "/profile?saved=0", status_code=303)


@app.post("/account/password")
@app.post("/profile/password")
def account_password_update(request: Request, current_password: str = Form(...), new_password: str = Form(...)):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    if current_password != _current_auth_password() or len(new_password or "") < 10:
        return RedirectResponse(url="/profile", status_code=303)
    _save_auth_config(_current_auth_email(), new_password)
    return RedirectResponse(url="/profile", status_code=303)


@app.post("/login")
def login_submit(request: Request, email: str = Form(...), password: str = Form(...)):
    ip = _request_ip(request)
    if _is_rate_limited(f"login:{ip}", limit=12, window_seconds=900):
        return RedirectResponse(url="/login?err=1", status_code=303)

    target_email = (email or "").strip().lower()
    target_password = password or ""

    # Allow legacy single-admin auth config.
    auth_email = _current_auth_email()
    auth_password = _current_auth_password()
    if target_email == auth_email and target_password == auth_password:
        resp = RedirectResponse(url="/ui", status_code=303)
        resp.set_cookie(APP_SESSION_COOKIE, _session_token(target_email), httponly=True, samesite="lax", secure=False, path="/")
        return resp

    # Allow DB-backed user accounts (created by signup or billing automation).
    user_password = _get_user_password(target_email)
    if user_password and target_password == user_password:
        resp = RedirectResponse(url="/ui", status_code=303)
        resp.set_cookie(APP_SESSION_COOKIE, _session_token(target_email), httponly=True, samesite="lax", secure=False, path="/")
        return resp

    return RedirectResponse(url="/login?err=1", status_code=303)


@app.post("/logout")
@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(APP_SESSION_COOKIE, path="/")
    return resp


@app.get("/admin/subscriptions", response_class=HTMLResponse)
def admin_subscriptions_page(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)

    viewer = _session_email_from_token(request.cookies.get(APP_SESSION_COOKIE, ""))
    if viewer != _current_auth_email():
        return HTMLResponse("<h3>Forbidden</h3><p>Admin access required.</p>", status_code=403)

    rows: list[tuple] = []
    conn = _db_conn()
    try:
        if conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select coalesce(customer_email,''), coalesce(stripe_subscription_id,''), coalesce(stripe_price_id,''),
                           coalesce(status,''), created_at, updated_at
                    from public.stripe_subscriptions
                    order by updated_at desc
                    limit 200
                    """
                )
                rows = cur.fetchall() or []
    except Exception as e:
        log_event(f"ADMIN_SUBSCRIPTIONS_LOAD_FAIL | {e}")
    finally:
        if conn:
            conn.close()

    body_rows = "".join(
        f"<tr><td>{html.escape(str(r[0] or ''))}</td><td>{html.escape(str(r[1] or ''))}</td><td>{html.escape(str(r[2] or ''))}</td><td>{html.escape(str(r[3] or ''))}</td><td>{html.escape(str(r[4] or ''))}</td><td>{html.escape(str(r[5] or ''))}</td></tr>"
        for r in rows
    )
    if not body_rows:
        body_rows = "<tr><td colspan='6'>No subscriptions found yet.</td></tr>"

    html_doc = f"""
<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/><title>Admin Subscriptions</title>
<style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:#f6f8ff;color:#0f172a;margin:0}}
.wrap{{max-width:1200px;margin:24px auto;padding:0 14px}}
.card{{background:#fff;border:1px solid #e5ebff;border-radius:14px;padding:14px;box-shadow:0 8px 20px rgba(31,58,118,.08)}}
table{{width:100%;border-collapse:collapse;font-size:13px}} th,td{{border-bottom:1px solid #eef2ff;padding:10px;text-align:left;vertical-align:top}} th{{background:#f8faff}}
a{{color:#0b5fff;text-decoration:none;font-weight:700}}
</style></head><body>
<div class='wrap'>
  <p><a href='/ui'>← Back to dashboard</a></p>
  <div class='card'>
    <h2 style='margin:0 0 8px 0'>Admin • Subscriptions</h2>
    <p style='margin:0 0 12px 0;color:#5b6b83'>Latest Stripe subscriptions synced via webhook.</p>
    <table>
      <thead><tr><th>Email</th><th>Subscription ID</th><th>Price ID</th><th>Status</th><th>Created</th><th>Updated</th></tr></thead>
      <tbody>{body_rows}</tbody>
    </table>
  </div>
</div>
</body></html>
"""
    return HTMLResponse(html_doc, headers={"Cache-Control": "no-store"})


@app.post("/call/start")
def start_call(
    to: str = Form(...),
    session_id: str = Form(default=""),
    x_api_key: str | None = Header(default=None),
):
    verify_call_api_key(x_api_key)
    _validate_required()
    if session_id:
        s = INTERVIEW_SESSIONS.get(session_id)
        if not s or not s.get("ready"):
            raise HTTPException(status_code=400, detail="Interview session is not ready")
        if not s.get("start_triggered"):
            raise HTTPException(status_code=400, detail="start interview trigger not set")

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    voice_url = f"{PUBLIC_BASE_URL}/twilio/voice"
    if session_id:
        voice_url += f"?session_id={session_id}"

    status_cb = f"{PUBLIC_BASE_URL}/twilio/status"
    if session_id:
        status_cb += f"?session_id={session_id}"
    call = client.calls.create(
        to=to,
        from_=TWILIO_PHONE_NUMBER,
        url=voice_url,
        method="POST",
        status_callback=status_cb,
        status_callback_event=["initiated", "ringing", "answered", "completed"],
        status_callback_method="POST",
    )
    if session_id and session_id in INTERVIEW_SESSIONS:
        INTERVIEW_SESSIONS[session_id]["call_in_progress"] = True
        INTERVIEW_SESSIONS[session_id]["last_call_status"] = "initiated"
    log_event(f"CALL_START to={to} sid={call.sid} interview_session={session_id}")
    return {"status": "started", "call_sid": call.sid, "to": to, "session_id": session_id}


def _answer_candidate_question_or_handoff(session: dict, question: str, call_sid: str = "") -> tuple[str, bool]:
    q = (question or "").strip()
    if not q:
        return ("Could you please repeat your question?", False)

    # If no model key, route to manager directly.
    if not (OpenAI and OPENAI_API_KEY):
        return ("I want to make sure you get the most accurate answer. Let me connect you with my manager now.", True)

    try:
        client = OpenAI(api_key=OPENAI_API_KEY)
        payload = {
            "job_title": session.get("job_title", ""),
            "job_description": (session.get("job_description", "") or "")[:2500],
            "candidate_question": q[:800],
            "instruction": "If you can answer confidently from available context, return concise helpful answer. If uncertain or policy-sensitive, return HANDOFF.",
        }
        r = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "You are a recruiter assistant on a live call. Keep answers short and clear. If uncertain, reply exactly HANDOFF."},
                {"role": "user", "content": json.dumps(payload)},
            ],
            max_tokens=140,
        )
        out = (r.choices[0].message.content or "").strip()
        if (not out) or out.upper().startswith("HANDOFF") or "I DON'T KNOW" in out.upper() or "NOT SURE" in out.upper():
            return ("I want to make sure you get the most accurate answer. Let me connect you with my manager now.", True)
        return (out, False)
    except Exception as e:
        log_event(f"CANDIDATE_QA_FAIL | {e}")
        return ("I want to make sure you get the most accurate answer. Let me connect you with my manager now.", True)


def _trigger_manager_handoff(session_id: str, room: str) -> bool:
    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        url = f"{PUBLIC_BASE_URL}/twilio/manager/join?room={room}&session_id={session_id}"
        client.calls.create(
            to=MANAGER_PHONE_NUMBER,
            from_=TWILIO_PHONE_NUMBER,
            url=url,
            method="POST",
        )
        return True
    except Exception as e:
        log_event(f"MANAGER_HANDOFF_FAIL | {e}")
        return False


@app.api_route("/twilio/manager/join", methods=["GET", "POST"])
async def twilio_manager_join(request: Request):
    room = (request.query_params.get("room", "") or "").strip() or f"joblynk-{uuid.uuid4().hex[:10]}"
    vr = VoiceResponse()
    vr.say("You are now being connected to the candidate.", voice=TWILIO_FALLBACK_VOICE, language="en-US")
    d = vr.dial()
    d.conference(room, start_conference_on_enter=True, end_conference_on_exit=False)
    return Response(str(vr), media_type="text/xml")


@app.api_route("/twilio/voice", methods=["GET", "POST"])
@app.api_route("/twiml/welcome", methods=["GET", "POST"])
async def twiml_welcome(request: Request):
    await validate_twilio_request(request)
    vr = VoiceResponse()

    form = await request.form()
    incoming_from = (form.get("From") or "").strip()
    answered_by = (form.get("AnsweredBy") or "").strip().lower()
    inbound_call_sid = (form.get("CallSid") or "").strip()
    user_text = (form.get("SpeechResult") or form.get("Body") or "").strip()
    log_event(f"TWIML_WELCOME call_sid={inbound_call_sid or 'none'} answered_by={answered_by or 'none'} from={incoming_from} session={request.query_params.get('session_id','')}")

    session_id = request.query_params.get("session_id", "")
    intro = "Hi, this is Adam from Softwise Solutions."
    voice_id = ELEVENLABS_VOICE_ID
    fallback_voice = TWILIO_FALLBACK_VOICE

    if session_id and session_id in INTERVIEW_SESSIONS:
        s = INTERVIEW_SESSIONS[session_id]
        # On initial answer webhook, Twilio does not provide SpeechResult.
        # Do not play "didn't catch that" here; always deliver interviewer greeting first.
        s["silence_count"] = 0
        profile_key = (s.get("agent_profile") or "").strip().lower()
        profile = _resolve_agent_profile(profile_key)
        assistant_name = s.get("assistant_name") or profile.get("assistant_name") or ASSISTANT_NAME
        voice_id = s.get("elevenlabs_voice_id") or profile.get("elevenlabs_voice_id") or ELEVENLABS_VOICE_ID
        fallback_voice = s.get("twilio_fallback_voice") or profile.get("twilio_fallback_voice") or TWILIO_FALLBACK_VOICE
        if s.get("ready") and s.get("start_triggered"):
            if profile_key in {"sara", "adam"}:
                intro = _prompt_line(s, "intro", f"Hi, this is {assistant_name} from Joblynk. Is this a good time to talk?")
                s["started"] = True
                s["completed"] = False
                s.setdefault("dialogue", []).append({"role": "interviewer", "text": intro[:1400]})
            else:
                script = _load_call_script_config(profile_key)
                if not s.get("started"):
                    s["started"] = True
                    s["completed"] = False
                    s["intro_phase"] = "consent"
                    s["current_idx"] = 0
                    s["current_question"] = s["plan"][0] if s.get("plan") else "Tell me about your recent relevant experience for this role."
                    role = s.get("job_title") or "this position"
                    summary = s.get("job_summary") or "It’s a role focused on strong execution, collaboration, and delivery quality."
                    candidate_name = (s.get("candidate_name") or "").strip() or "there"
                    intro = script["intro_template"].format(first_name=candidate_name, agent_name=assistant_name, job_title=role, job_summary=summary, first_question=s.get("current_question") or "")
                    s.setdefault("dialogue", []).append({"role": "interviewer", "text": intro[:1400]})
                else:
                    intro = s.get("current_question") or "Please continue with your answer."
        else:
            intro = "Interview session is not ready yet. Please initialize from the dashboard first."
    else:
        # Callback handling: identify candidate by inbound phone number and resume last session.
        cand = _find_candidate_by_phone(incoming_from)
        if cand and cand.get("last_session_id") and cand.get("last_session_id") in INTERVIEW_SESSIONS:
            session_id = cand.get("last_session_id")
            s = INTERVIEW_SESSIONS.get(session_id, {})
            s["callback_received"] = True
            s["status"] = s.get("status") or "ready"
            s["intro_phase"] = "callback_confirm"
            profile = _resolve_agent_profile(s.get("agent_profile"))
            voice_id = s.get("elevenlabs_voice_id") or profile.get("elevenlabs_voice_id") or ELEVENLABS_VOICE_ID
            fallback_voice = s.get("twilio_fallback_voice") or profile.get("twilio_fallback_voice") or TWILIO_FALLBACK_VOICE
            jt = (s.get("job_title") or "this position").strip()
            intro = f"Hi {cand.get('full_name') or 'there'}, welcome back. Are you calling regarding the {jt} position? Please say yes to continue."
            try:
                conn = _db_conn()
                if conn:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("update public.screening_candidates set status='callback_received', callback_received_at=now(), updated_at=now() where candidate_id=%s", (cand.get("candidate_id"),))
                    conn.close()
                    _log_candidate_activity(cand.get("candidate_id"), "callback_received", "Candidate called back and screening resumed", session_id=session_id)
            except Exception as e:
                log_event(f"CALLBACK_STATUS_UPDATE_FAIL | {e}")
        elif cand:
            restored_sid = _restore_session_for_callback(cand)
            if restored_sid and restored_sid in INTERVIEW_SESSIONS:
                session_id = restored_sid
                rs = INTERVIEW_SESSIONS.get(session_id, {})
                profile = _resolve_agent_profile(rs.get("agent_profile"))
                voice_id = rs.get("elevenlabs_voice_id") or profile.get("elevenlabs_voice_id") or ELEVENLABS_VOICE_ID
                fallback_voice = rs.get("twilio_fallback_voice") or profile.get("twilio_fallback_voice") or TWILIO_FALLBACK_VOICE
                jt = (rs.get("job_title") or "this position").strip()
                intro = f"Hi {cand.get('full_name') or 'there'}, welcome back. Are you calling regarding the {jt} position? Please say yes to continue."
            else:
                intro = f"Welcome back {cand.get('full_name') or 'there'}. We found your profile, but could not restore the interview session right now. Please hold while our team reconnects your screening."
        else:
            intro = "We could not identify your profile from this number. Please call back from your registered number, or contact the recruiter to continue your screening."

    # If carrier confirms voicemail/answering machine, leave callback voicemail and end.
    # NOTE: do NOT treat "unknown" as voicemail, to avoid false positives when humans answer.
    if answered_by in {"machine_start", "machine_end_beep", "machine_end_silence", "fax"} and session_id and session_id in INTERVIEW_SESSIONS:
        ss = INTERVIEW_SESSIONS.get(session_id, {})
        role = (ss.get("job_title") or "this position").strip()
        vm = (
            f"Hello, this is {COMPANY_NAME}. "
            f"We were trying to reach you regarding the {role} position. "
            f"Please call us back at this same number at your convenience. "
            f"Thank you, and we look forward to speaking with you."
        )
        _speak_or_fallback(vr, vm, voice_id=voice_id, fallback_voice=fallback_voice)
        vr.hangup()
        return Response(str(vr), media_type="text/xml")

    log_event(f"VOICE_REPLY sid={inbound_call_sid or 'none'} session={session_id} text={str(intro)[:1200]}")
    _speak_or_fallback(vr, intro, voice_id=voice_id, fallback_voice=fallback_voice)

    action_url = "/twilio/process"
    if session_id:
        action_url += f"?session_id={session_id}"

    gather = Gather(
        input="speech dtmf",
        action=action_url,
        method="POST",
        speech_timeout="3",
        language="en-US",
        timeout=5,
        action_on_empty_result=True,
    )
    vr.append(gather)
    return Response(str(vr), media_type="text/xml")


@app.post('/script/preview-tts')
def script_preview_tts(text: str = Form(...)):
    try:
        audio_url = synthesize_tts((text or "")[:1500])
        return {"ok": True, "audio_url": audio_url}
    except Exception as e:
        log_event(f"SCRIPT_PREVIEW_TTS_FAIL | {e}")
        return JSONResponse({"ok": False, "detail": "Preview voice unavailable right now."}, status_code=200)


@app.post('/agent/voice-sample')
def agent_voice_sample(agent_profile: str = Form('sara')):
    p = _resolve_agent_profile(agent_profile)
    profile_key = (agent_profile or 'sara').strip().lower()
    sample_name = p.get('assistant_name') or 'Agent'
    sample_text = f"Hi, this is {sample_name}."

    # Stable local cache so we don't spend TTS credits on every click.
    cached_name = f"voice_sample_{profile_key}.mp3"
    cached_path = AUDIO_DIR / cached_name
    if cached_path.exists() and cached_path.stat().st_size > 0:
        return {"ok": True, "audio_url": f"{PUBLIC_BASE_URL}/audio/{cached_name}", "agent": sample_name, "cached": True}

    try:
        fresh_url = synthesize_tts(sample_text, voice_id=p.get('elevenlabs_voice_id'))

        # Copy fresh generated audio into stable cache file.
        # synthesize_tts returns a URL like {PUBLIC_BASE_URL}/audio/reply_xxx.mp3
        generated_name = fresh_url.rsplit('/audio/', 1)[-1]
        generated_path = AUDIO_DIR / generated_name
        if generated_path.exists() and generated_path.stat().st_size > 0:
            cached_path.write_bytes(generated_path.read_bytes())
            return {"ok": True, "audio_url": f"{PUBLIC_BASE_URL}/audio/{cached_name}", "agent": sample_name, "cached": True}

        return {"ok": True, "audio_url": fresh_url, "agent": sample_name, "cached": False}
    except Exception as e:
        log_event(f"AGENT_VOICE_SAMPLE_FAIL | {e}")
        return JSONResponse({"ok": False, "detail": "Voice sample unavailable right now.", "agent": sample_name}, status_code=200)


@app.post("/twilio/status")
async def twilio_status(request: Request, CallSid: str = Form(default=""), CallStatus: str = Form(default="")):
    await validate_twilio_request(request)

    # Twilio may post only CallSid/CallStatus, but some providers/proxies can alter key casing.
    # Read raw form as a fallback so end-of-call state is not missed.
    form = await request.form()
    call_sid = (CallSid or form.get("CallSid") or form.get("call_sid") or "").strip()
    call_status = (CallStatus or form.get("CallStatus") or form.get("call_status") or "").strip().lower()
    from_number = (form.get("From") or "").strip()
    to_number = (form.get("To") or "").strip()

    # Primary lookup uses session_id in callback URL.
    session_id = request.query_params.get("session_id", "")

    # Fallback lookup: find session by call SID if query param is missing.
    if (not session_id or session_id not in INTERVIEW_SESSIONS) and call_sid:
        for sid, sess in INTERVIEW_SESSIONS.items():
            if any((c.get("call_sid") == call_sid) for c in sess.get("calls", [])):
                session_id = sid
                break

    if session_id and session_id in INTERVIEW_SESSIONS:
        s = INTERVIEW_SESSIONS[session_id]
        terminal = {"completed", "failed", "busy", "no-answer", "no answer", "canceled", "cancelled"}
        if not s.get("candidate_id"):
            try:
                s["candidate_id"] = _ensure_candidate_for_session(session_id, to_number)
            except Exception:
                pass

        # Ignore late non-terminal callbacks after completion to prevent stale "in progress" UI.
        if s.get("completed") and (s.get("last_call_status") or "").lower() in terminal and call_status not in terminal:
            return {"ok": True, "session_id": session_id, "call_sid": call_sid, "call_status": call_status, "ignored": True}

        s["last_call_status"] = call_status
        s["call_in_progress"] = call_status not in terminal

        # persist call status record
        try:
            conn = _db_conn()
            if conn:
                candidate_id = s.get("candidate_id", "")
                with conn:
                    with conn.cursor() as cur:
                        provider_meta = CALL_PROVIDER_TRACK.get(call_sid or "", {})
                        cur.execute(
                            """
                            insert into public.screening_calls (
                              call_sid, candidate_id, session_id, direction, from_number, to_number, call_status, provider_used, provider_reason, updated_at
                            )
                            values (%s,%s,%s,'outbound',%s,%s,%s,%s,%s,now())
                            on conflict (call_sid) do update set
                              call_status=excluded.call_status,
                              from_number=excluded.from_number,
                              to_number=excluded.to_number,
                              provider_used=coalesce(excluded.provider_used, public.screening_calls.provider_used),
                              provider_reason=coalesce(excluded.provider_reason, public.screening_calls.provider_reason),
                              updated_at=now()
                            """,
                            (
                                call_sid,
                                candidate_id or None,
                                session_id,
                                from_number,
                                to_number,
                                call_status,
                                provider_meta.get("provider_used"),
                                provider_meta.get("provider_reason"),
                            ),
                        )
                conn.close()
                if candidate_id:
                    _log_candidate_activity(candidate_id, "call_status_updated", f"Call status changed to {call_status}", session_id=session_id, call_sid=call_sid)
        except Exception as e:
            log_event(f"CALL_STATUS_PERSIST_FAIL | {e}")

        for c in s.get("calls", []):
            if not call_sid or c.get("call_sid") == call_sid:
                c["status"] = call_status or c.get("status", "")
                c["updated_at"] = _now()

        # Always finalize the session when call reaches terminal state so UI does not stay in-progress.
        if call_status in terminal:
            s["completed"] = True
            s["intro_phase"] = "done"
            s["current_question"] = ""
            if not s.get("recommendation"):
                # Generate fallback recommendation even for short/partial calls.
                s["recommendation"] = _recommendation_for_session(s)

            # candidate table consistency updates + notification
            try:
                cid = s.get("candidate_id", "")
                conn = _db_conn()
                if conn and cid:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute(
                                """
                                update public.screening_candidates
                                set status=%s,
                                    screening_completed_at=case when %s='completed' then now() else screening_completed_at end,
                                    last_summary=%s,
                                    updated_at=now()
                                where candidate_id=%s
                                returning assigned_agent_email, full_name
                                """,
                                (
                                    "screening_completed" if call_status == "completed" else "outbound_no_answer",
                                    call_status,
                                    s.get("recommendation", ""),
                                    cid,
                                ),
                            )
                            row = cur.fetchone()
                    conn.close()

                    # Missed call handling: place short callback message (best-effort voicemail-style call).
                    if call_status in {"no-answer", "no answer", "busy", "failed"}:
                        _log_candidate_activity(cid, "missed_call", "Outbound call not answered. Callback requested.", session_id=session_id, call_sid=call_sid)
                        try:
                            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
                            role = (s.get("job_title") or "this position").strip()
                            msg = (
                                f"Hello, this is {COMPANY_NAME}. "
                                f"We were trying to reach you regarding the {role} position. "
                                f"Please call us back at this same number at your convenience. "
                                f"Thank you, and we look forward to speaking with you."
                            )
                            client.calls.create(to=to_number, from_=TWILIO_PHONE_NUMBER, twiml=f"<Response><Say>{html.escape(msg)}</Say></Response>")
                        except Exception as ve:
                            log_event(f"MISSED_CALL_MESSAGE_FAIL | {ve}")

                    if call_status == "completed" and row and row[0]:
                        _log_candidate_activity(cid, "screening_completed", "Screening interview marked completed.", session_id=session_id, call_sid=call_sid)
                        _send_agent_notification(
                            row[0],
                            f"Candidate callback + screening completed ({cid})",
                            f"Candidate {row[1] or cid} called back and screening completed. Session: {session_id}. Summary: {s.get('recommendation','Pending')}"
                        )
            except Exception as e:
                log_event(f"CANDIDATE_FINALIZE_FAIL | {e}")

    return {"ok": True}


@app.api_route("/twilio/listen", methods=["GET", "POST"])
async def twilio_listen(request: Request):
    await validate_twilio_request(request)
    vr = VoiceResponse()
    session_id = request.query_params.get("session_id", "")
    try_n = int(request.query_params.get("n", "0") or "0")

    # Guard against endless ringing/loops when nobody answers meaningfully.
    if try_n >= 4 and session_id and session_id in INTERVIEW_SESSIONS:
        s = INTERVIEW_SESSIONS.get(session_id, {})
        role = (s.get("job_title") or "this position").strip()
        vm = (
            f"Hello, this is {COMPANY_NAME}. "
            f"We were trying to reach you regarding the {role} position. "
            f"Please call us back at this same number at your convenience. "
            f"Thank you, and we look forward to speaking with you."
        )
        _speak_or_fallback(vr, vm)
        vr.hangup()
        s["completed"] = True
        s["call_in_progress"] = False
        s["last_call_status"] = "no-answer"
        return Response(str(vr), media_type="text/xml")

    action_url = "/twilio/process"
    if session_id:
        action_url += f"?session_id={session_id}"
    gather = Gather(
        input="speech dtmf",
        action=action_url,
        method="POST",
        speech_timeout="3",
        language="en-US",
        timeout=5,
    )
    vr.append(gather)
    listen_url = "/twilio/listen"
    if session_id:
        listen_url += f"?session_id={session_id}&n={try_n+1}"
    else:
        listen_url += f"?n={try_n+1}"
    vr.redirect(listen_url)
    return Response(str(vr), media_type="text/xml")


@app.post("/twilio/process")
@app.post("/twiml/process")
async def twiml_process(
    request: Request,
    SpeechResult: str = Form(default=""),
    Digits: str = Form(default=""),
    Confidence: str = Form(default=""),
    CallSid: str = Form(default=""),
):
    await validate_twilio_request(request)
    user_text = (SpeechResult or "").strip()
    if not user_text and (Digits or "").strip():
        user_text = "yes" if Digits.strip() == "1" else Digits.strip()
    session_id = request.query_params.get("session_id", "")

    voice_id = ELEVENLABS_VOICE_ID
    fallback_voice = TWILIO_FALLBACK_VOICE
    if session_id and session_id in INTERVIEW_SESSIONS:
        s = INTERVIEW_SESSIONS[session_id]
        profile_key = (s.get("agent_profile") or "").strip().lower()
        script = _load_call_script_config(profile_key)
        profile = _resolve_agent_profile(profile_key)
        assistant_name = s.get("assistant_name") or profile.get("assistant_name") or ASSISTANT_NAME
        voice_id = s.get("elevenlabs_voice_id") or profile.get("elevenlabs_voice_id") or ELEVENLABS_VOICE_ID
        fallback_voice = s.get("twilio_fallback_voice") or profile.get("twilio_fallback_voice") or TWILIO_FALLBACK_VOICE

        # Prompt-driven interview mode for Adam/Sara: no rigid scripted branching.
        if profile_key in {"sara", "adam"}:
            low = (user_text or "").strip().lower()
            if not s.get("prompt_handshake_done"):
                if any(x in low for x in ["yes", "yeah", "yep", "sure", "ok", "okay", "go ahead", "1"]):
                    s["prompt_handshake_done"] = True
                    role = (s.get("job_title") or "this role").strip()
                    reply_text = f"Thank you. I am calling regarding the {role} position. Let's start the technical interview. Can you please introduce yourself and share your work experience, education, and a recent project you have completed?"
                elif any(x in low for x in ["no", "not now", "busy", "later", "2"]):
                    s["completed"] = True
                    s["call_in_progress"] = False
                    reply_text = "No problem at all. Thank you for your time. We can reconnect at a better time."
                else:
                    reply_text = _prompt_line(s, "intro", f"Hi, this is {assistant_name} from Joblynk. Is this a good time to talk?")
            else:
                reply_text = _prompt_driven_interview_turn(s, user_text, CallSid, session_id)

            log_event(f"VOICE_INPUT sid={CallSid} session={session_id} conf={Confidence} text={user_text[:1200]}")
            log_event(f"VOICE_REPLY sid={CallSid} session={session_id} text={reply_text[:1200]}")
            vr = VoiceResponse()
            _speak_or_fallback(vr, reply_text, voice_id=voice_id, fallback_voice=fallback_voice)
            if s.get("handoff_now"):
                room = s.get("handoff_room") or f"joblynk-{session_id[:10]}"
                s["handoff_now"] = False
                vr.pause(length=2)
                d = vr.dial()
                d.conference(room, start_conference_on_enter=True, end_conference_on_exit=False)
                return Response(str(vr), media_type="text/xml")
            if s.get("completed"):
                vr.hangup()
                return Response(str(vr), media_type="text/xml")
            action_url = "/twilio/process"
            if session_id:
                action_url += f"?session_id={session_id}"
            gather = Gather(
                input="speech dtmf",
                action=action_url,
                method="POST",
                speech_timeout="3",
                language="en-US",
                timeout=5,
                action_on_empty_result=True,
            )
            vr.append(gather)
            return Response(str(vr), media_type="text/xml")

        # Callback confirmation gate: confirm candidate intent/job before resuming interview.
        if s.get("intro_phase") == "callback_confirm":
            lower = user_text.lower()
            role = s.get("job_title") or "this role"
            if any(x in lower for x in ["yes", "yeah", "yep", "correct", "right", "that one", "1"]):
                s["intro_phase"] = "questions"
                if not s.get("current_question"):
                    s["current_idx"] = 0
                    s["current_question"] = s["plan"][0] if s.get("plan") else "Could you share a quick summary of your relevant experience?"
                reply_text = f"Great, thanks for confirming. {s.get('current_question')}"
            elif any(x in lower for x in ["no", "wrong", "not", "different"]):
                s["completed"] = True
                reply_text = f"No problem. Thank you for your time. If needed, please call us again regarding the {role} position."
            else:
                reply_text = f"Just to confirm, are you calling about the {role} position? Please say yes to continue."

        elif s.get("intro_phase") == "post_questions_prompt":
            lower = user_text.lower()
            if any(x in lower for x in ["yes", "yeah", "yep", "i do", "question", "1"]):
                s["intro_phase"] = "candidate_qna"
                reply_text = "Absolutely. Please go ahead with your question."
            elif any(x in lower for x in ["no", "nope", "none", "that's all", "2"]):
                s["completed"] = True
                s["call_in_progress"] = False
                reply_text = "Thank you for your time today. We look forward to speaking with you again. Goodbye."
            else:
                reply_text = "Do you have any questions before we close? Please say yes or no."

        elif s.get("intro_phase") == "candidate_qna":
            ans, handoff = _answer_candidate_question_or_handoff(s, user_text, CallSid)
            if handoff:
                room = f"joblynk-{session_id[:10]}-{uuid.uuid4().hex[:4]}"
                ok = _trigger_manager_handoff(session_id, room)
                if ok:
                    s["handoff_room"] = room
                    s["handoff_now"] = True
                    reply_text = ans
                else:
                    reply_text = "I'm unable to connect right now, but our manager will call you back shortly."
                    s["completed"] = True
                    s["call_in_progress"] = False
            else:
                reply_text = ans + " Do you have any other question?"

        # Natural intro + consent gate before screening questions.
        elif s.get("intro_phase") == "consent":
            lower = user_text.lower()
            if any(x in lower for x in ["yes", "sure", "okay", "ok", "go ahead", "1"]):
                s["intro_phase"] = "questions"
                role = s.get("job_title") or "this role"
                summary = s.get("job_summary") or (s.get("job_description") or "").strip().replace("\n", " ")[:220]
                reply_text = script["consent_yes_template"].format(job_title=role, job_summary=summary, first_question=s.get("current_question", "Could you share a quick summary of your relevant experience?"), first_name=s.get("candidate_name", "there"), agent_name=assistant_name)
            elif any(x in lower for x in ["no", "busy", "later", "not now"]):
                s["completed"] = True
                reply_text = script["consent_no"]
            else:
                reply_text = script["consent_retry"]
        else:
            cq = s.get("current_question", "")
            if cq:
                s.setdefault("completed_questions", []).append({"question": cq, "answer": user_text})

            s["current_idx"] = int(s.get("current_idx", 0)) + 1
            next_q = s["plan"][s["current_idx"]] if s["current_idx"] < len(s.get("plan", [])) else ""
            # Guard against accidental duplicate consecutive questions.
            while next_q and cq and next_q.strip().lower() == cq.strip().lower() and s["current_idx"] < len(s.get("plan", [])) - 1:
                s["current_idx"] += 1
                next_q = s["plan"][s["current_idx"]]
            s["current_question"] = next_q

            if not s.get("current_question"):
                s["intro_phase"] = "post_questions_prompt"
                s["call_in_progress"] = True
                if not s.get("recommendation"):
                    s["recommendation"] = _recommendation_for_session(s)
                reply_text = script["wrap_up"] + " Before we close, do you have any questions for me?"
            else:
                next_q = s['current_question']
                reply_text = ""
                mode = _provider_mode()
                # Strict LiveKit-first for session interviews when available.
                if mode in {"livekit", "auto"} and _is_livekit_ready():
                    orch = _livekit_orchestrator()
                    if orch:
                        try:
                            agent_key = (s.get("agent_profile") or "").strip().lower()
                            interviewer_prompt = ""
                            if agent_key == "sara":
                                interviewer_prompt = _build_sara_system_prompt(s)
                            elif agent_key == "adam":
                                interviewer_prompt = _build_adam_system_prompt(s)
                            prompt = (
                                (interviewer_prompt + "\n\n" if interviewer_prompt else "")
                                + f"You are conducting a phone interview. Candidate just answered: {(user_text or '').strip()[:700]}\n"
                                + f"Acknowledge briefly in one short sentence, then ask this next question verbatim: {next_q}"
                            )
                            out = orch.generate_text_reply(prompt=prompt, context={"call_sid": CallSid, "session_id": session_id, "phase": "next_question"})
                            if out:
                                if next_q.lower() not in out.lower():
                                    out = f"Thanks for sharing. {next_q}"
                                reply_text = out
                                _mark_call_provider(CallSid, "livekit", f"scripted_session_flow_livekit:{mode}")
                        except Exception as e:
                            log_event(f"LIVEKIT_SESSION_TURN_FAIL | {e}")
                            _mark_call_provider(CallSid, "legacy", f"livekit_error:{str(e)[:120]}")

                if not reply_text:
                    reply_text = _build_conversational_next_prompt(
                        current_question=cq,
                        candidate_answer=user_text,
                        next_question=next_q,
                        candidate_name=s.get('candidate_name', 'there'),
                        job_title=s.get('job_title', ''),
                        session=s,
                    )
                    _mark_call_provider(CallSid, "legacy", f"scripted_session_flow_fallback:{mode}")
    else:
        # Provider-routed non-session conversational flow (LiveKit primary, legacy fallback).
        reply_text = _generate_text_reply_with_fallback(user_text, CallSid)


    # Detect voicemail greeting text and switch to callback voicemail flow.
    if session_id and session_id in INTERVIEW_SESSIONS and _looks_like_voicemail_greeting(user_text):
        ss = INTERVIEW_SESSIONS.get(session_id, {})
        role = (ss.get("job_title") or "this position").strip()
        vm = (
            f"Hello, this is {COMPANY_NAME}. "
            f"We were trying to reach you regarding the {role} position. "
            f"Please call us back at this same number at your convenience. "
            f"Thank you, and we look forward to speaking with you."
        )
        log_event(f"VOICEMAIL_DETECTED sid={CallSid} session={session_id}")
        vr = VoiceResponse()
        _speak_or_fallback(vr, vm, voice_id=voice_id, fallback_voice=fallback_voice)
        vr.hangup()
        ss["completed"] = True
        ss["call_in_progress"] = False
        ss["last_call_status"] = "no-answer"
        _mark_call_provider(CallSid, "legacy", "voicemail_detected")
        return Response(str(vr), media_type="text/xml")

    log_event(f"VOICE_INPUT sid={CallSid} session={session_id} conf={Confidence} text={user_text[:1200]}")
    log_event(f"VOICE_REPLY sid={CallSid} session={session_id} text={reply_text[:1200]}")

    vr = VoiceResponse()
    _speak_or_fallback(vr, reply_text, voice_id=voice_id, fallback_voice=fallback_voice)

    if session_id and session_id in INTERVIEW_SESSIONS and INTERVIEW_SESSIONS[session_id].get("handoff_now"):
        room = INTERVIEW_SESSIONS[session_id].get("handoff_room") or f"joblynk-{session_id[:10]}"
        INTERVIEW_SESSIONS[session_id]["handoff_now"] = False
        vr.pause(length=2)
        d = vr.dial()
        d.conference(room, start_conference_on_enter=True, end_conference_on_exit=False)
        return Response(str(vr), media_type="text/xml")

    if session_id and session_id in INTERVIEW_SESSIONS and INTERVIEW_SESSIONS[session_id].get("completed"):
        vr.hangup()
        return Response(str(vr), media_type="text/xml")

    action_url = "/twilio/process"
    if session_id:
        action_url += f"?session_id={session_id}"
    gather = Gather(
        input="speech dtmf",
        action=action_url,
        method="POST",
        speech_timeout="3",
        language="en-US",
        timeout=5,
        action_on_empty_result=True,
    )
    vr.append(gather)
    return Response(str(vr), media_type="text/xml")


@app.api_route("/twilio/sms", methods=["GET", "POST"])
async def twilio_sms(request: Request, Body: str = Form(default=""), From: str = Form(default="")):
    await validate_twilio_request(request)
    text = (Body or "").strip()
    reply = "Thanks for messaging Joblynk. Reply in this thread and Adam will assist you shortly."
    if text:
        reply = f"Received: {text[:120]}. Adam from Joblynk will follow up shortly."
    log_event(f"SMS from={From} body={text[:180]}")
    mr = MessagingResponse()
    mr.message(reply)
    return Response(str(mr), media_type="text/xml")


@app.get("/audio/{filename}")
def get_audio(filename: str):
    path = AUDIO_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=404, detail="Audio not found")
    return FileResponse(path, media_type="audio/mpeg", filename=filename)


class InterviewInitRequest(BaseModel):
    job_description: str
    resume: str
    job_title: str = ""
    resume_upload_id: str | None = None
    job_id: str | None = None

class JobCreateRequest(BaseModel):
    title: str
    job_description: str


class JobGenerateRequest(BaseModel):
    prompt: str


class CandidateQuestionRequest(BaseModel):
    job_description: str
    resume_upload_id: str | None = None
    resume_text: str | None = None
    previous_questions: list[str] | None = None
    agent_profile: str | None = None


class CandidateSummaryRequest(BaseModel):
    resume_upload_id: str
    job_description: str
    questions: list[str]
    answers: list[str]


def _extract_contact_info(resume_text: str) -> dict:
    txt = (resume_text or "").strip()
    lines = [x.strip() for x in txt.replace("\r", "").split("\n") if x.strip()]
    full_name = ""
    if lines:
        first = re.sub(r"\s+", " ", lines[0]).strip()
        if 2 <= len(first.split()) <= 5 and len(first) <= 80:
            full_name = first

    email = ""
    m = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", txt)
    if m:
        email = m.group(0)

    phone = ""
    pm = re.search(r"(?:\+?1[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4})", txt)
    if pm:
        phone = pm.group(0)

    linkedin = ""
    lm = re.search(r"https?://(?:www\.)?linkedin\.com/[^\s)]+", txt, flags=re.IGNORECASE)
    if lm:
        linkedin = lm.group(0)

    return {
        "full_name": full_name,
        "email": email,
        "phone": phone,
        "linkedin": linkedin,
    }


def _extract_text_from_resume_upload(upload: UploadFile, raw: bytes) -> str:
    name = (upload.filename or "resume").lower()
    if name.endswith(".pdf") and PdfReader:
        import io
        reader = PdfReader(io.BytesIO(raw))
        return "\n".join([(p.extract_text() or "") for p in reader.pages]).strip()
    if (name.endswith(".docx") or name.endswith(".doc")) and docx:
        import tempfile
        with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tf:
            tf.write(raw)
            tmp = tf.name
        d = docx.Document(tmp)
        return "\n".join([p.text for p in d.paragraphs]).strip()
    return raw.decode("utf-8", errors="ignore").strip()


def _persist_resume_upload(upload: UploadFile, raw: bytes, session_id: str | None = None) -> dict:
    ext = Path(upload.filename or "resume.txt").suffix.lower() or ".txt"
    upload_id = uuid.uuid4().hex
    fname = f"{upload_id}{ext}"
    fpath = RESUME_DIR / fname
    fpath.write_bytes(raw)

    conn = _db_conn()
    if conn:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into public.screening_resume_uploads (upload_id, session_id, original_filename, stored_path, content_type, size_bytes) values (%s,%s,%s,%s,%s,%s)",
                        (upload_id, session_id, upload.filename or "", str(fpath), upload.content_type or "", len(raw)),
                    )
        except Exception as e:
            log_event(f"DB_RESUME_UPLOAD_INSERT_FAIL | {e}")
        finally:
            conn.close()

    return {"upload_id": upload_id, "stored_path": str(fpath), "size_bytes": len(raw)}


def _normalize_screening_question(q: str) -> str:
    t = (q or "").strip().replace("\n", " ")
    t = re.sub(r"\s+", " ", t)
    if not t:
        return ""
    # hard constraints: single-topic, no and/or combos
    lowered = t.lower()
    if " and/or " in lowered:
        return ""
    # reduce common compound joins into first clause only
    t = re.split(r"\?\s*(and|also|plus)\b", t, flags=re.IGNORECASE)[0].strip()
    # ensure it's a question
    if not t.endswith("?"):
        t = t.rstrip(".") + "?"
    return t


def _enforce_question_rules(candidates: list[str], previous_questions: list[str], first_q: str) -> list[str]:
    used = {x.lower().strip() for x in (previous_questions or [])}
    out: list[str] = []
    for raw in candidates or []:
        q = _normalize_screening_question(str(raw))
        if not q:
            continue
        lk = q.lower().strip()
        if lk == first_q.lower() or lk in used or lk in {x.lower().strip() for x in out}:
            continue
        out.append(q)
        if len(out) >= 3:
            break
    return out


def _generate_candidate_questions(job_description: str, resume_text: str, previous_questions: list[str] | None = None, agent_profile: str | None = None) -> list[str]:
    previous_questions = previous_questions or []
    first_q = "Why are you looking for new job opportunities?"

    # Primary path: OpenAI generation with strict recruiter prompt.
    if OpenAI and OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            nonce = uuid.uuid4().hex[:8]
            r = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.9,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are a domain subject matter expert relevant to the job being evaluated (technical, functional, clinical, operational, or managerial as appropriate). "
                            "You understand real-world execution requirements, not buzzwords. "
                            "Generate high-signal screening questions that determine if a candidate can realistically perform the job. "
                            "Return JSON object with key 'questions' containing exactly 3 strings only."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps({
                            "task": "Analyze the job description and generate 3 role-specific screening questions for an AI-led initial screen.",
                            "interviewer_profile": (agent_profile or "default").strip().lower(),
                            "mandatory_requirements": [
                                "First question is fixed and always asked separately: Why are you looking for new opportunities?",
                                "Each generated question must address only one topic",
                                "No compound or multi-part questions",
                                "No and/or combinations",
                                "Clear, open-ended, neutral, non-leading",
                                "Focus on core responsibilities, must-have skills, and real execution",
                                "Prefer experience-based prompts like Tell me about / Describe a time",
                            ],
                            "job_description": (job_description or "")[:7000],
                            "previous_questions": previous_questions[:10],
                            "nonce": nonce,
                        }),
                    },
                ],
                max_tokens=260,
                response_format={"type": "json_object"},
            )
            content = (r.choices[0].message.content or "{}").strip()
            obj = json.loads(content)
            arr = obj.get("questions") if isinstance(obj, dict) else None
            if isinstance(arr, list):
                out = _enforce_question_rules([str(x) for x in arr], previous_questions, first_q)
                if len(out) >= 3:
                    return [first_q] + out[:3]
        except Exception as e:
            log_event(f"OPENAI_QUESTION_GEN_FALLBACK | {e}")

    # Fallback path
    skills = extract_skills(job_description or "", resume_text or "")
    seed = skills[:3] if skills else ["hands-on role experience", "required technical stack", "production troubleshooting"]
    while len(seed) < 3:
        seed.append(seed[-1] if seed else "must-have skills")
    fallback_templates = [
        [
            f"How many years of hands-on experience do you have with {seed[0]}?",
            f"What recent project demonstrates your required competency in {seed[1]}?",
            f"Describe one real production issue you resolved involving {seed[2]}.",
        ],
        [
            f"Tell me about a time you delivered results using {seed[0]}.",
            f"Describe a project where {seed[1]} was essential to success.",
            f"Walk me through a critical incident you handled related to {seed[2]}.",
        ],
        [
            f"What is the most complex work you have completed involving {seed[0]}?",
            f"Share an example where your work in {seed[1]} directly impacted outcomes.",
            f"Describe a high-pressure situation where you applied {seed[2]} effectively.",
        ],
    ]
    fallback = random.choice(fallback_templates)
    return [first_q] + _enforce_question_rules(fallback, previous_questions, first_q)[:3]


def _summarize_candidate_responses(job_description: str, questions: list[str], answers: list[str]) -> str:
    lines = ["Candidate Screening Summary", "", "Role Context:", (job_description or "")[:600], "", "Responses:"]
    for i, q in enumerate(questions[:10]):
        a = answers[i] if i < len(answers) else ""
        lines.append(f"Q{i+1}: {q}")
        lines.append(f"A{i+1}: {a}")
    lines.append("")
    lines.append("Overall Impression: Candidate provided responses for initial screening. Review technical depth, specificity, and communication clarity before final decision.")
    return "\n".join(lines)


def _extract_candidate_name(resume_text: str) -> str:
    txt = (resume_text or "").strip()
    if not txt:
        return ""
    lines = [x.strip() for x in txt.replace("\r", "").split("\n") if x.strip()]
    if not lines:
        return ""
    first = lines[0]
    if 1 <= len(first.split()) <= 4 and len(first) <= 60:
        cleaned = "".join(ch for ch in first if ch.isalpha() or ch in " -.'").strip()
        if cleaned:
            return cleaned.split()[0]  # first name only
    return ""


def _recommendation_for_session(s: dict) -> str:
    qa = s.get("completed_questions", []) or []
    jd = s.get("job_description", "")
    resume = s.get("resume", "")
    if OpenAI and OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            prompt = {
                "job_title": s.get("job_title", ""),
                "job_description": jd[:3000],
                "resume": resume[:3000],
                "qa": qa[:10],
            }
            r = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": "You are a recruitment evaluator. Return concise hiring recommendation."},
                    {"role": "user", "content": json.dumps(prompt)},
                ],
                max_tokens=180,
            )
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                return txt
        except Exception as e:
            log_event(f"OPENAI_RECOMMENDATION_FALLBACK | {e}")
    answered = len([x for x in qa if isinstance(x, dict) and (x.get("answer") or "").strip()])
    if answered >= 4:
        return "Recommendation: Good fit for next round based on relevant responses and communication. Proceed to recruiter review."
    if answered >= 2:
        return "Recommendation: Potential fit, but needs deeper technical evaluation in the next round."
    return "Recommendation: Insufficient evidence from call responses. Re-screen or collect more details before proceeding."


def _plain_text(s: str) -> str:
    t = (s or "")
    t = re.sub(r"<[^>]+>", " ", t)
    t = t.replace("&nbsp;", " ")
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _evaluate_resume_fit(job_description: str, resume_text: str) -> str:
    jd = _plain_text((job_description or "").strip())
    rs = _plain_text((resume_text or "").strip())
    if not jd or not rs:
        return "Pending evaluation."

    if OpenAI and OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            prompt = """You are an expert recruiter and hiring-manager assistant. You evaluate candidate resumes against job descriptions across any industry or job function.

You must also think like a senior domain practitioner (20+ years of experience) relevant to the role being evaluated (e.g., architect, analyst, clinician, finance leader, program manager). Treat the job description as a delivery or responsibility scope, not just a title, and assess whether the candidate has demonstrably performed comparable work in real-world settings.

Step 1 – Identify the Job Category (Implicit, Do Not Output)
Before evaluating the resume, classify the role into one primary category and apply the corresponding lens:
- Technical / Engineering roles → systems, architecture, scale, tooling, end-to-end delivery
- Functional / Analytical roles → problem analysis, domain knowledge, methodologies, outcomes
- Delivery / Management roles → ownership, planning, execution, governance, stakeholder management
- Clinical / Regulated roles → licensure, procedures, compliance, patient or operational scope
Use the appropriate delivery lens for the role type.

Evaluation Rules:
- These candidates were pre-filtered by Explorium. Give fair credit for relevant experience.
- Evaluate only demonstrated experience; do not infer missing skills.
- Highest weight to responsibilities central to successful performance.
- Related but non-equivalent experience = partial alignment.
- Assess comparable scope, complexity, accountability, and end-to-end execution.

Scoring guidance:
- Similar/exact title starts around 70-80.
- 50%+ required skills adds 15-25.
- Relevant domain adds 10-20.
- Matching years adds 5-10.
- Portfolio/work samples adds 5-10.
- Right title + relevant skills generally 85-95.
- Reduce significantly only for major gaps.

Must-Haves:
- Identify explicit must-haves and whether evidence exists.
- Missing must-haves reduce score but do not auto-fail if strong related experience.
- Skills list alone is weak evidence without delivery proof.

Return EXACT structure:
Overall Fit
Fit Verdict: Good Fit / Partial Fit / Not a Good Fit
Summary:
(2-3 sentences)

Experience Relevance
Estimated Relevance: X%
Justification:
- Bullet 1 ...
- Bullet 2 ...
- Bullet 3 (optional) ...

Must-Haves Check
Must-Haves Present? Yes / Partially / No (use these exact words; do not abbreviate)
Evidence:
- Provide 1 concise bullet with explicit must-have proof from resume experience (tools, years, certifications, delivery outcomes).
- If missing, name the missing must-have(s) explicitly in the same bullet.
- Do not use generic statements like "overlapping indicators"; cite concrete evidence.
"""
            r = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.2,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": f"Job Description:\n{jd[:7000]}\n\nCandidate Resume:\n{rs[:7000]}"},
                ],
                max_tokens=700,
            )
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                return txt
        except Exception as e:
            log_event(f"OPENAI_FIT_EVAL_FALLBACK | {e}")

    # Heuristic fallback (still evidence-based) when OpenAI is unavailable.
    jd_skills = extract_skills(jd, "")
    rs_skills = extract_skills("", rs)
    jd_set = {s.lower().strip() for s in jd_skills if s.strip()}
    rs_set = {s.lower().strip() for s in rs_skills if s.strip()}
    overlap = sorted(jd_set.intersection(rs_set))

    title_line = next((ln.strip() for ln in jd.replace("\r", "").split("\n") if ln.strip()), "the role")
    title_words = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", title_line)[:5]]
    title_match = any(w in rs.lower() for w in title_words)

    years_req = 0
    years_resume = 0
    req_match = re.search(r"(\d+)\+?\s*years", jd, flags=re.IGNORECASE)
    if req_match:
        years_req = int(req_match.group(1))
    resume_years = [int(x) for x in re.findall(r"(\d+)\+?\s*years", rs, flags=re.IGNORECASE)]
    if resume_years:
        years_resume = max(resume_years)

    base = 72 if title_match else 58
    overlap_ratio = (len(overlap) / max(1, len(jd_set))) if jd_set else 0.0
    score = base + int(overlap_ratio * 28)
    if years_req and years_resume >= years_req:
        score += 8
    elif years_req and years_resume > 0:
        score += 4
    score = max(40, min(96, score))

    if score >= 82:
        verdict = "Good Fit"
        must_have = "Yes" if overlap_ratio >= 0.6 else "Partially"
    elif score >= 65:
        verdict = "Partial Fit"
        must_have = "Partially"
    else:
        verdict = "Not a Good Fit"
        must_have = "No"

    top_overlap = ", ".join(overlap[:6]) if overlap else "limited direct overlap found"
    gap_note = "Years requirement appears covered." if (years_req and years_resume >= years_req) else ("Years requirement not clearly evidenced." if years_req else "Years requirement not explicitly stated in JD.")

    missing = [x for x in list(jd_set)[:8] if x not in rs_set]
    if overlap:
        proof = f"Resume explicitly shows: {', '.join(overlap[:3])}."
    else:
        proof = "No explicit must-have proof found in resume work history."
    if missing:
        proof += f" Missing/unclear: {', '.join(missing[:3])}."

    return (
        "Overall Fit\n"
        f"Fit Verdict: {verdict}\n\n"
        "Summary:\n"
        f"The resume shows {'strong' if score>=82 else 'partial' if score>=65 else 'limited'} alignment to the role responsibilities with evidence in key areas such as {top_overlap}. "
        f"Based on demonstrated delivery signals and role relevance, this candidate is assessed as {verdict.lower()} for initial screening.\n\n"
        "Experience Relevance\n"
        f"Estimated Relevance: {score}%\n\n"
        "Justification:\n"
        f"- Direct alignment appears in: {top_overlap}.\n"
        f"- Related experience is present but may not fully cover all must-haves for this role scope.\n"
        f"- {gap_note}\n\n"
        "Must-Haves Check\n"
        f"Must-Haves Present? {must_have}\n"
        f"Evidence: - {proof}"
    )


def _job_summary_for_intro(job_title: str, job_description: str) -> str:
    jd = (job_description or "").strip()
    if not jd:
        return "It focuses on delivering reliable, high-quality work with strong collaboration across the team."

    if OpenAI and OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            r = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.3,
                messages=[
                    {"role": "system", "content": "Create a concise, friendly, professional one- or two-sentence spoken summary for a recruitment call intro."},
                    {"role": "user", "content": f"Job title: {job_title}\nJob description:\n{jd}\n\nReturn only the short summary."},
                ],
                max_tokens=90,
            )
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                return txt
        except Exception as e:
            log_event(f"OPENAI_JOB_SUMMARY_FALLBACK | {e}")

    # Fallback: first 1-2 meaningful lines
    parts = [x.strip(" •\t-") for x in jd.replace("\r", "").split("\n") if x.strip()]
    brief = " ".join(parts[:2])[:240]
    return brief or "It focuses on delivering reliable, high-quality work with strong collaboration across the team."


def _build_conversational_next_prompt(current_question: str, candidate_answer: str, next_question: str, candidate_name: str = "", job_title: str = "", session: dict | None = None) -> str:
    """Create a natural transition that acknowledges the candidate answer and asks the next generated question verbatim."""
    nq = (next_question or "").strip()
    if not nq:
        return ""

    profile_key = ((session or {}).get("agent_profile") or "").strip().lower()

    # Optional AI-crafted conversational bridge (disabled by default for real-time call latency).
    if CALL_CONVERSATIONAL_AI_BRIDGE and OpenAI and OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            payload = {
                "job_title": (job_title or "")[:120],
                "candidate_name": (candidate_name or "")[:80],
                "current_question": (current_question or "")[:300],
                "candidate_answer": (candidate_answer or "")[:900],
                "next_question": nq[:300],
                "rules": [
                    "Write 1-2 short spoken sentences only",
                    "First sentence: natural acknowledgement only (no scoring/judgment)",
                    "Second sentence: ask the next question exactly as provided, without edits",
                    "Tone: warm, professional recruiter conversation",
                ],
            }
            system_prompt = "You are a conversational recruitment interviewer. Keep replies concise and natural for phone calls."
            if profile_key == "sara":
                system_prompt = _build_sara_system_prompt(session)
            elif profile_key == "adam":
                system_prompt = _build_adam_system_prompt(session)

            r = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.5,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload)},
                ],
                max_tokens=120,
            )
            txt = (r.choices[0].message.content or "").strip()
            if txt:
                # Hard guarantee that next generated question is asked exactly.
                if nq.lower() not in txt.lower():
                    txt = f"Thanks for sharing. {nq}"
                return txt
        except Exception as e:
            log_event(f"OPENAI_CONVERSATIONAL_TURN_FALLBACK | {e}")

    # Fallback: deterministic conversational phrasing.
    name = (candidate_name or "there").strip() or "there"
    return f"Thanks for sharing, {name}. {nq}"


def _run_interview_init_pipeline(session_id: str):
    s = INTERVIEW_SESSIONS.get(session_id)
    if not s:
        return
    try:
        s["status"] = "parsing_resume"
        time.sleep(0.8)

        s["status"] = "parsing_jd"
        time.sleep(0.8)

        s["status"] = "skill_mapping"
        s["skills"] = extract_skills(s.get("job_description", ""), s.get("resume", ""))
        s["fit_evaluation"] = _evaluate_resume_fit(s.get("job_description", ""), s.get("resume", ""))
        time.sleep(0.8)

        s["status"] = "interview_plan_generation"
        # Use job/resume-specific generated questions (not static hardcoded bank)
        s["plan"] = _generate_candidate_questions(s.get("job_description", ""), s.get("resume", ""))
        s["candidate_name"] = _extract_candidate_name(s.get("resume", ""))
        s["job_summary"] = _job_summary_for_intro(s.get("job_title", ""), s.get("job_description", ""))
        time.sleep(0.8)

        s["status"] = "agent_session_initialization"
        time.sleep(0.8)

        s["status"] = "ready"
        s["ready"] = True
    except Exception as e:
        s["status"] = "failed"
        s["error"] = str(e)


@app.post("/interview/init")
def interview_init(payload: InterviewInitRequest):
    session_id = uuid.uuid4().hex
    resolved_title = (payload.job_title or payload.job_description.splitlines()[0][:120] if payload.job_description else "Untitled Role")
    resolved_job_id = (payload.job_id or "").strip()

    # Auto-save job posting so it appears after refresh even if user skipped "Save Job"
    # If a job is already selected, do not create duplicate entries.
    try:
        if not resolved_job_id:
            conn = _db_conn()
            if conn:
                with conn:
                    with conn.cursor() as cur:
                        # avoid duplicates on same title+description combo
                        cur.execute("select job_id from public.screening_jobs where title=%s and job_description=%s limit 1", (resolved_title, payload.job_description))
                        ex = cur.fetchone()
                        if ex and ex[0]:
                            resolved_job_id = str(ex[0])
                        else:
                            jid = _generate_job_id()
                            cur.execute("insert into public.screening_jobs (job_id, title, job_description) values (%s,%s,%s)", (jid, resolved_title, payload.job_description))
                            resolved_job_id = jid
                conn.close()
    except Exception as e:
        log_event(f"DB_AUTO_SAVE_JOB_FAIL | {e}")

    # If resume was pre-uploaded, link upload row with this session
    if payload.resume_upload_id:
        conn = _db_conn()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("update public.screening_resume_uploads set session_id=%s where upload_id=%s", (session_id, payload.resume_upload_id))
            except Exception as e:
                log_event(f"DB_RESUME_UPLOAD_LINK_FAIL | {e}")
            finally:
                conn.close()

    INTERVIEW_SESSIONS[session_id] = {
        "status": "starting",
        "ready": False,
        "start_triggered": False,
        "job_description": payload.job_description,
        "resume": payload.resume,
        "job_title": resolved_title,
        "job_id": resolved_job_id,
        "candidate_name": "",
        "candidate_phone": "",
        "candidate_email": "",
        "job_summary": "",
        "skills": [],
        "fit_evaluation": "Pending skill mapping...",
        "plan": [],
        "current_idx": 0,
        "current_question": "",
        "completed_questions": [],
        "scores": [],
        "clarifications": 0,
        "started": False,
        "completed": False,
        "call_in_progress": False,
        "last_call_status": "",
        "recommendation": "",
        "calls": [],
        "created_at": _now(),
    }

    # Persist session/job mapping for cross-page grouping and history.
    try:
        conn = _db_conn()
        if conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into public.screening_sessions (session_id, candidate_id, job_id, job_title, updated_at)
                        values (%s,%s,%s,%s,now())
                        on conflict (session_id) do update set
                          job_id=excluded.job_id,
                          job_title=excluded.job_title,
                          updated_at=now()
                        """,
                        (session_id, None, resolved_job_id or None, resolved_title),
                    )
            conn.close()
    except Exception as e:
        log_event(f"SESSION_PERSIST_FAIL | {e}")

    # Candidate upsert (email is primary identifier; update existing if found)
    try:
        ci = _extract_contact_info(payload.resume or "")
        INTERVIEW_SESSIONS[session_id]["candidate_phone"] = _normalize_phone(ci.get("phone", ""))
        INTERVIEW_SESSIONS[session_id]["candidate_email"] = _normalize_email(ci.get("email", ""))
        up = _upsert_candidate(
            full_name=ci.get("full_name", "") or _extract_candidate_name(payload.resume or ""),
            email=ci.get("email", ""),
            phone_number=ci.get("phone", ""),
            linkedin_profile=ci.get("linkedin", ""),
            skill_mapping={"job_title": resolved_title},
            assigned_agent_email=_current_auth_email(),
        )
        if up.get("candidate_id"):
            INTERVIEW_SESSIONS[session_id]["candidate_id"] = up.get("candidate_id")
            conn = _db_conn()
            if conn:
                try:
                    with conn:
                        with conn.cursor() as cur:
                            cur.execute("update public.screening_candidates set last_session_id=%s, status='screening_in_progress', updated_at=now() where candidate_id=%s", (session_id, up.get("candidate_id")))
                            cur.execute("update public.screening_sessions set candidate_id=%s, updated_at=now() where session_id=%s", (up.get("candidate_id"), session_id))
                finally:
                    conn.close()
            _log_candidate_activity(up.get("candidate_id"), "screening_initialized", f"Interview initialized for role: {resolved_title}", session_id=session_id)
    except Exception as e:
        log_event(f"CANDIDATE_INIT_LINK_FAIL | {e}")

    t = threading.Thread(target=_run_interview_init_pipeline, args=(session_id,), daemon=True)
    t.start()

    return {"session_id": session_id, "status": "starting"}


@app.post("/resume/upload")
async def resume_upload(resume_file: UploadFile = File(...)):
    raw = await resume_file.read()
    persist = _persist_resume_upload(resume_file, raw)
    resume_text = _extract_text_from_resume_upload(resume_file, raw)
    if not resume_text:
        raise HTTPException(status_code=400, detail="Unable to parse resume file")

    contact = _extract_contact_info(resume_text)
    up = {}
    if contact.get("email"):
        up = _upsert_candidate(
            full_name=contact.get("full_name", ""),
            email=contact.get("email", ""),
            phone_number=contact.get("phone", ""),
            linkedin_profile=contact.get("linkedin", ""),
            skill_mapping={"source": "resume_upload"},
            assigned_agent_email=_current_auth_email(),
        )
        if up.get("candidate_id"):
            _log_candidate_activity(up.get("candidate_id"), "resume_uploaded", f"Resume uploaded: {resume_file.filename or ''}")

    return {
        "ok": True,
        "resume_upload": {**persist, "db_recorded": True, "filename": resume_file.filename or ""},
        "resume_text": resume_text,
        "contact_info": contact,
        "candidate": up,
    }


@app.post("/interview/init-upload")
async def interview_init_upload(job_description: str = Form(...), resume_file: UploadFile = File(...), job_title: str = Form(default="")):
    raw = await resume_file.read()
    persist = _persist_resume_upload(resume_file, raw)
    resume_text = _extract_text_from_resume_upload(resume_file, raw)
    if not resume_text:
        raise HTTPException(status_code=400, detail="Unable to parse resume file")
    result = interview_init(InterviewInitRequest(job_description=job_description, resume=resume_text, job_title=job_title, resume_upload_id=persist["upload_id"]))
    result["resume_upload"] = persist
    result["resume_upload"]["db_recorded"] = True
    return result


@app.get('/resume/file/{upload_id}')
def resume_file_view(upload_id: str, request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url='/login', status_code=303)
    conn = _db_conn()
    if not conn:
        raise HTTPException(status_code=500, detail='db unavailable')
    try:
        with conn.cursor() as cur:
            cur.execute("select stored_path, coalesce(original_filename,''), coalesce(content_type,'application/octet-stream') from public.screening_resume_uploads where upload_id=%s", (upload_id,))
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail='resume not found')
            path, original_name, content_type = row
            if not path or not os.path.exists(path):
                raise HTTPException(status_code=404, detail='resume file missing')
            return FileResponse(path, media_type=content_type or 'application/octet-stream', filename=(original_name or os.path.basename(path)))
    finally:
        conn.close()


@app.post("/candidate/questions")
def candidate_questions(payload: CandidateQuestionRequest):
    resume_text = payload.resume_text or ""
    if payload.resume_upload_id and not resume_text:
        conn = _db_conn()
        if conn:
            try:
                with conn.cursor() as cur:
                    cur.execute("select stored_path from public.screening_resume_uploads where upload_id=%s", (payload.resume_upload_id,))
                    row = cur.fetchone()
                    if row and row[0] and os.path.exists(row[0]):
                        with open(row[0], "rb") as f:
                            raw = f.read()
                        class DummyUpload:
                            filename = row[0]
                        resume_text = _extract_text_from_resume_upload(DummyUpload(), raw)
            finally:
                conn.close()
    prev = payload.previous_questions or []
    job_key = hashlib.sha256((payload.job_description or "").strip().lower().encode()).hexdigest()[:24]
    historical = QUESTION_HISTORY.get(job_key, [])
    combined_prev = list(dict.fromkeys((prev + historical)[-50:]))

    # Retry generation to avoid repeats on regenerate.
    questions = _generate_candidate_questions(payload.job_description or "", resume_text or "", combined_prev, payload.agent_profile)
    for _ in range(2):
        if not combined_prev:
            break
        same = {x.strip().lower() for x in combined_prev[-4:]} == {x.strip().lower() for x in questions}
        if not same:
            break
        # push previous + current to increase novelty pressure
        questions = _generate_candidate_questions(payload.job_description or "", resume_text or "", (combined_prev + questions)[-50:], payload.agent_profile)

    # Final hard guard: if still same, paraphrase role questions (keep fixed first question).
    if combined_prev and len(questions) >= 4:
        same = {x.strip().lower() for x in combined_prev[-4:]} == {x.strip().lower() for x in questions}
        if same and len(questions) >= 4:
            stems = [
                "Tell me about a time you",
                "Describe a situation where you",
                "Walk me through how you",
            ]
            varied = [questions[0]]
            for i, q in enumerate(questions[1:4]):
                core = q.rstrip("?. ")
                varied.append(f"{stems[i % len(stems)]} {core[:1].lower() + core[1:]}?")
            questions = varied[:4]

    if len(questions) < 4:
        base = [
            "Why are you looking for new job opportunities?",
            "Describe a recent project where you handled the most critical responsibility in this role.",
            "Tell me about a time you solved a high-impact problem relevant to this role.",
            "Walk me through how you delivered measurable results in a similar role.",
        ]
        questions = (questions + [q for q in base if q not in questions])[:4]

    final_qs = questions[:4]
    QUESTION_HISTORY[job_key] = (historical + final_qs)[-200:]
    return {"questions": final_qs}


@app.post("/candidate/summary")
def candidate_summary(payload: CandidateSummaryRequest):
    summary = _summarize_candidate_responses(payload.job_description, payload.questions, payload.answers)
    assessment_id = uuid.uuid4().hex
    conn = _db_conn()
    if conn:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into public.screening_candidate_assessments (assessment_id, resume_upload_id, job_description, questions_json, answers_json, summary) values (%s,%s,%s,%s,%s,%s)",
                        (assessment_id, payload.resume_upload_id, payload.job_description, json.dumps(payload.questions), json.dumps(payload.answers), summary),
                    )
        finally:
            conn.close()
    return {"ok": True, "assessment_id": assessment_id, "summary": summary}


@app.get("/candidate/summary/{resume_upload_id}")
def get_candidate_summary(resume_upload_id: str):
    conn = _db_conn()
    if not conn:
        return {"ok": False, "summary": ""}
    try:
        with conn.cursor() as cur:
            cur.execute("select summary, created_at from public.screening_candidate_assessments where resume_upload_id=%s order by created_at desc limit 1", (resume_upload_id,))
            row = cur.fetchone()
            if not row:
                return {"ok": False, "summary": ""}
            return {"ok": True, "summary": row[0], "created_at": str(row[1])}
    finally:
        conn.close()


@app.post("/jobs")
def create_job(payload: JobCreateRequest):
    jid = _generate_job_id()
    item = {
        "job_id": jid,
        "title": (payload.title or "Untitled Role").strip(),
        "job_description": payload.job_description,
        "created_at": _now(),
    }
    JOB_POSTINGS[jid] = item

    conn = _db_conn()
    if conn:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "insert into public.screening_jobs (job_id, title, job_description) values (%s,%s,%s)",
                        (jid, item["title"], item["job_description"]),
                    )
        except Exception as e:
            log_event(f"DB_JOB_INSERT_FAIL | {e}")
        finally:
            conn.close()

    return item


@app.get("/jobs")
def list_jobs():
    items = _load_jobs_rows(200)
    return JSONResponse({"jobs": items}, headers={"Cache-Control": "no-store"})


@app.post('/jobs/generate')
def generate_job_post(payload: JobGenerateRequest):
    prompt = (payload.prompt or '').strip()
    if not prompt:
        raise HTTPException(status_code=400, detail='prompt is required')

    if OpenAI and OPENAI_API_KEY:
        try:
            client = OpenAI(api_key=OPENAI_API_KEY)
            r = client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.35,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": (
                        "You are a senior recruiter and hiring manager writer. Produce polished, enterprise-quality job posts similar to strong ChatGPT output. "
                        "Return strict JSON with keys: job_title, job_description. "
                        "job_description must be structured with clear headings and bullet points in this order: "
                        "About Us, Job Summary, Key Responsibilities, Required Skills and Qualifications, Preferred Qualifications. "
                        "Never output placeholders like [Company Name] or [City, State]. Use concrete, sensible defaults when missing. "
                        "Keep tone professional, concise, and realistic. Avoid generic filler."
                    )},
                    {"role": "user", "content": (
                        f"Create a complete job post from this prompt:\n{prompt}\n\n"
                        "Output requirements:\n"
                        "- Strong clear job title (must reflect the role in user prompt exactly, e.g., Java Developer)\n"
                        "- Job Summary must be at least 4 lines and read like a short professional role description\n"
                        "- Do not include Location, Job Type, or About Us sections unless explicitly requested in the prompt\n"
                        "- 6-8 key responsibilities\n"
                        "- 6-8 required qualifications\n"
                        "- 3-5 preferred qualifications\n"
                        "- Keep readable for enterprise recruiting"
                    )},
                ],
                max_tokens=1200,
            )
            content = (r.choices[0].message.content or '{}').strip()
            obj = json.loads(content)
            title = (obj.get('job_title') or '').strip()
            description = (obj.get('job_description') or '').strip()
            if description:
                if not title:
                    title = " ".join(w.capitalize() for w in re.findall(r"[A-Za-z]+", prompt)[:3]).strip() or "Technical Role"
                return {"ok": True, "job_title": title, "job_description": description}
        except Exception as e:
            log_event(f"OPENAI_JOB_POST_GEN_FALLBACK | {e}")

    # fallback generator from free-text prompt (no placeholders)
    low = prompt.lower()
    title = "Software Engineer"
    m = re.search(r"(?:role|title)\s*[:\-]\s*([^,\n]+)", prompt, flags=re.IGNORECASE)
    m2 = re.search(r"(?:need|for|as|hire|hiring)\s+(?:a|an)?\s*([A-Za-z][A-Za-z\s\-/]{3,50})", prompt, flags=re.IGNORECASE)
    if m:
        title = m.group(1).strip().title()
    elif m2:
        title = m2.group(1).strip().title()
    elif "java developer" in low or ("java" in low and "developer" in low):
        title = "Java Developer"
    elif "unix" in low:
        title = "Unix Administrator"

    # clean noisy trailing connectors (e.g., "Java Developer With")
    title = re.sub(r"\b(with|for|in|at|on)\b.*$", "", title, flags=re.IGNORECASE).strip(" -:")

    description = (
        f"Job Summary\n"
        f"We are seeking a {title} to design, build, and support high-quality production solutions aligned with business goals. This role requires strong ownership, technical depth, and the ability to deliver reliable outcomes in cross-functional teams. You will work closely with stakeholders to translate requirements into maintainable, scalable implementations. The ideal candidate combines hands-on execution with sound engineering judgment and clear communication.\n\n"
        f"Key Responsibilities\n"
        f"- Install, configure, and maintain Unix/Linux servers and core platform services.\n"
        f"- Monitor system performance, troubleshoot incidents, and drive root-cause resolution.\n"
        f"- Automate repeatable operations through shell scripting and operational tooling.\n"
        f"- Manage user access, permissions, hardening controls, and patching schedules.\n"
        f"- Partner with engineering and IT teams to support production releases and uptime goals.\n"
        f"- Maintain clear runbooks, architecture notes, and operational documentation.\n\n"
        f"Required Skills and Qualifications\n"
        f"- Proven hands-on experience as a Unix/Linux Administrator or similar role.\n"
        f"- Strong command-line administration skills across Unix/Linux environments.\n"
        f"- Experience with shell scripting and operational automation.\n"
        f"- Solid troubleshooting capability across system, service, and network layers.\n"
        f"- Working knowledge of security controls, access management, and patch compliance.\n"
        f"- Clear communication skills and ability to collaborate in cross-functional teams.\n\n"
        f"Preferred Qualifications\n"
        f"- Experience with cloud infrastructure platforms (AWS, Azure, or GCP).\n"
        f"- Familiarity with configuration management tools (Ansible, Puppet, or Chef).\n"
        f"- Exposure to monitoring/observability platforms and production incident workflows.\n"
    )
    return {"ok": True, "job_title": title, "job_description": description}


@app.get("/livekit/health")
def livekit_health(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    if not check_livekit_health:
        return {"ok": False, "provider": "livekit", "reason": "module_unavailable"}
    return check_livekit_health()


@app.get("/voice/provider")
def voice_provider_status(request: Request):
    if not _is_authenticated(request):
        return RedirectResponse(url="/login", status_code=303)
    mode = _provider_mode()
    return {
        "mode": mode,
        "livekit_ready": _is_livekit_ready(),
        "fallback": "legacy",
    }


@app.get("/db/health")
def db_health():
    conn = _db_conn()
    if not conn:
        return {"db": "down", "count": 0}
    try:
        with conn.cursor() as cur:
            cur.execute("select count(*) from public.screening_jobs")
            c = cur.fetchone()[0]
            return {"db": "up", "count": c}
    except Exception as e:
        return {"db": "error", "error": str(e)}
    finally:
        conn.close()


def _dashboard_stats() -> dict:
    jobs_count = 0
    conn = _db_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("select count(*) from public.screening_jobs")
                jobs_count = int(cur.fetchone()[0] or 0)
        except Exception:
            jobs_count = len(JOB_POSTINGS)
        finally:
            conn.close()
    else:
        jobs_count = len(JOB_POSTINGS)

    sessions = list(INTERVIEW_SESSIONS.values())
    calls_made = sum(len(s.get("calls", [])) for s in sessions)
    active_calls = sum(1 for s in sessions if s.get("call_in_progress"))
    responded = sum(1 for s in sessions if len(s.get("completed_questions", []) or []) > 0)
    terminal_statuses = {"completed", "failed", "busy", "no-answer", "canceled"}
    no_response = sum(
        1 for s in sessions
        if (s.get("last_call_status") in terminal_statuses) and len(s.get("completed_questions", []) or []) == 0
    )
    completed_sessions = sum(1 for s in sessions if s.get("last_call_status") in terminal_statuses or s.get("completed"))
    total_answers = sum(len(s.get("completed_questions", []) or []) for s in sessions)

    strong = moderate = low = pending = 0
    for s in sessions:
        rec = (s.get("recommendation") or "").lower()
        if rec:
            if any(x in rec for x in ["good fit", "strong fit", "proceed"]):
                strong += 1
            elif any(x in rec for x in ["potential", "moderate", "deeper"]):
                moderate += 1
            else:
                low += 1
        else:
            pending += 1

    return {
        "jobs_posted": jobs_count,
        "total_candidates_screened": len(sessions),
        "sessions_completed": completed_sessions,
        "calls_made": calls_made,
        "calls_responded": responded,
        "calls_no_response": no_response,
        "active_calls": active_calls,
        "total_answers_captured": total_answers,
        "recommendation_strong_fit": strong,
        "recommendation_moderate_fit": moderate,
        "recommendation_not_yet_fit": low,
        "recommendation_pending": pending,
    }


@app.get("/dashboard/stats")
def dashboard_stats():
    return JSONResponse(_dashboard_stats(), headers={"Cache-Control": "no-store"})


@app.get('/dashboard/trends')
def dashboard_trends(range: str = 'weekly', start: str = '', end: str = ''):
    now = datetime.now(timezone.utc)
    days_map = {'daily': 1, 'weekly': 7, 'monthly': 30, 'quarterly': 90, 'yearly': 365}
    days = days_map.get((range or '').lower(), 7)

    try:
        start_dt = datetime.fromisoformat(start).replace(tzinfo=timezone.utc) if start else (now - timedelta(days=days-1))
    except Exception:
        start_dt = now - timedelta(days=days-1)
    try:
        end_dt = datetime.fromisoformat(end).replace(tzinfo=timezone.utc) if end else now
    except Exception:
        end_dt = now

    if start_dt > end_dt:
        start_dt, end_dt = end_dt, start_dt

    start_day = datetime(start_dt.year, start_dt.month, start_dt.day, tzinfo=timezone.utc)
    end_day = datetime(end_dt.year, end_dt.month, end_dt.day, tzinfo=timezone.utc)

    data = {}
    cur = start_day
    while cur <= end_day:
        key = cur.strftime('%Y-%m-%d')
        data[key] = {'date': key, 'jobs_posted': 0, 'resumes_uploaded': 0}
        cur += timedelta(days=1)

    conn = _db_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select to_char((created_at at time zone 'UTC')::date, 'YYYY-MM-DD') as d, count(*)
                    from public.screening_jobs
                    where created_at >= %s and created_at < %s
                    group by d order by d
                    """,
                    (start_day, end_day + timedelta(days=1)),
                )
                for d, c in cur.fetchall():
                    if d in data:
                        data[d]['jobs_posted'] = int(c or 0)

                cur.execute(
                    """
                    select to_char((created_at at time zone 'UTC')::date, 'YYYY-MM-DD') as d, count(*)
                    from public.screening_resume_uploads
                    where created_at >= %s and created_at < %s
                    group by d order by d
                    """,
                    (start_day, end_day + timedelta(days=1)),
                )
                for d, c in cur.fetchall():
                    if d in data:
                        data[d]['resumes_uploaded'] = int(c or 0)
        except Exception as e:
            log_event(f"DASHBOARD_TRENDS_FAIL | {e}")
        finally:
            conn.close()

    return {'range': range, 'start': start_day.strftime('%Y-%m-%d'), 'end': end_day.strftime('%Y-%m-%d'), 'points': list(data.values())}


@app.get("/dashboard", response_class=HTMLResponse)
def dashboard_page():
    cards = _dashboard_stats()
    profile = _load_agent_profile()
    welcome_name = (profile.get("agent_name") or profile.get("display_name") or "there").strip()

    def card(title: str, key: str) -> str:
        return f"<div class='kpi'><div class='kpi-title'>{title}</div><div class='kpi-value' id='{key}'>{cards.get(key,0)}</div></div>"

    html_doc = f"""
<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>Joblynk Dashboard</title>
<style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:linear-gradient(180deg,#eef4ff 0%,#f8fbff 100%);margin:0;color:#0a1f44;overflow-x:hidden}}
.site-header{{background:linear-gradient(90deg,#0b5fff,#0051c8);color:#fff;padding:14px 24px;box-shadow:0 6px 20px rgba(0,51,128,.2)}}
.header-inner{{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}}
.nav a{{color:#fff;text-decoration:none;font-weight:700;margin-left:12px;font-size:13px}}
.burger{{display:none;background:transparent;border:1px solid rgba(255,255,255,.45);color:#fff;border-radius:8px;padding:6px 10px;font-weight:700}}
.brand{{font-size:18px;font-weight:800;line-height:1.2}}
.tag{{font-size:12px;opacity:.9}}
.wrap{{max-width:1100px;margin:18px auto;padding:0 16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
.kpi{{background:#fff;border:1px solid #dbe7ff;border-radius:12px;padding:14px;box-shadow:0 2px 10px rgba(0,51,128,.06)}}
.kpi-title{{font-size:12px;color:#5f7398;text-transform:uppercase;letter-spacing:.4px}}
.kpi-value{{font-size:28px;font-weight:800;color:#0b4fd6;margin-top:6px}}
.panel{{background:#fff;border:1px solid #dbe7ff;border-radius:12px;padding:14px;box-shadow:0 2px 10px rgba(0,51,128,.06);margin-top:14px}}
.welcome-tile{{background:#fff;border:1px solid #dbe7ff;border-radius:12px;padding:12px 14px;box-shadow:0 2px 10px rgba(0,51,128,.06);margin-bottom:12px;color:#35517a;font-size:18px;font-weight:500}}
.row{{display:flex;gap:8px;flex-wrap:wrap;align-items:center}}
.chip{{border:1px solid #bfd3f8;background:#f4f8ff;color:#0b4fd6;border-radius:999px;padding:6px 10px;font-size:12px;font-weight:700;cursor:pointer}}
.chip.active{{background:#0b5fff;color:#fff}}
.chart-wrap{{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-top:10px}}
.chart{{border:1px solid #dbe7ff;border-radius:10px;padding:10px}}
.chart-title{{font-size:12px;color:#5f7398;text-transform:uppercase;font-weight:700;letter-spacing:.4px;margin-bottom:6px}}
svg{{width:100%;height:140px;background:#f9fbff;border-radius:8px}}
@media (max-width: 900px){{
  .wrap{{padding:0 10px}}
  .grid{{grid-template-columns:1fr 1fr}}
  .chart-wrap{{grid-template-columns:1fr}}
  .row{{align-items:stretch}}
  .row .chip, .row input[type='date']{{width:100%;text-align:center}}
  .burger{{display:block}}
  .nav{{position:fixed;top:0;right:-260px;width:240px;height:100vh;background:#0b5fff;padding:70px 14px 14px;display:flex;flex-direction:column;gap:8px;transition:right .25s ease;z-index:20;box-shadow:-8px 0 24px rgba(0,0,0,.2)}}
  .nav.open{{right:0}}
  .nav a{{margin-left:0;font-size:14px;padding:8px 4px}}
}}
@media (max-width: 560px){{
  .grid{{grid-template-columns:1fr}}
}}
</style></head>
<body>
<header class='site-header'><div class='header-inner'><div><div class='brand'>Joblynk Screening Console</div><div class='tag'>Enterprise Interview Workflow</div></div><button id='burgerDash' class='burger' type='button'>☰</button><div class='nav' id='dashNav'><a href='/dashboard'>Dashboard</a><a href='/ui'>InstantScreen</a><a href='/candidates'>Candidates</a><a href='/profile'>Profile</a><a href='/logout'>Logout</a></div></div></header>
<div class='wrap'>
  <div class='welcome-tile'>Welcome {html.escape(welcome_name)}</div>
  <div class='grid'>
    {card('Jobs Posted','jobs_posted')}
    {card('Total Candidates Screened','total_candidates_screened')}
    {card('Sessions Completed','sessions_completed')}
    {card('Calls Made','calls_made')}
    {card('Calls Responded','calls_responded')}
    {card('Calls No Response','calls_no_response')}
    {card('Active Calls','active_calls')}
    {card('Answers Captured','total_answers_captured')}
    {card('Strong Fit','recommendation_strong_fit')}
    {card('Moderate Fit','recommendation_moderate_fit')}
    {card('Not Yet Fit','recommendation_not_yet_fit')}
    {card('Recommendation Pending','recommendation_pending')}
  </div>
  <div class='panel'>
    <div class='row'><b>Trends</b>
      <button class='chip' data-range='daily'>Daily</button>
      <button class='chip active' data-range='weekly'>Weekly</button>
      <button class='chip' data-range='monthly'>Monthly</button>
      <button class='chip' data-range='quarterly'>Quarterly</button>
      <button class='chip' data-range='yearly'>Yearly</button>
      <input type='date' id='fromDate' />
      <input type='date' id='toDate' />
      <button class='chip' id='applyRange'>Apply Date Range</button>
    </div>
    <div class='chart-wrap'>
      <div class='chart'><div class='chart-title'>Jobs Posted Trend</div><svg id='chartJobs'></svg></div>
      <div class='chart'><div class='chart-title'>Resumes Uploaded Trend</div><svg id='chartResumes'></svg></div>
    </div>
  </div>
</div>
<script>
let currentRange='weekly';
let rangeStart='';
let rangeEnd='';
function drawLine(svgId, vals){{
  const svg=document.getElementById(svgId); if(!svg) return;
  const w=svg.clientWidth||300, h=140, p=12;
  const max=Math.max(1,...vals), min=Math.min(...vals,0);
  const span=Math.max(1,max-min);
  const pts=vals.map((v,i)=>{{
    const x=p + (i*(w-2*p))/Math.max(1,vals.length-1);
    const y=h-p - ((v-min)*(h-2*p))/span;
    return `${{x.toFixed(1)}},${{y.toFixed(1)}}`;
  }}).join(' ');
  svg.innerHTML=`<polyline fill='none' stroke='#0b5fff' stroke-width='3' points='${{pts}}'/><line x1='${{p}}' y1='${{h-p}}' x2='${{w-p}}' y2='${{h-p}}' stroke='#dbe7ff'/>`;
}}
async function renderTrends(){{
  const qs = new URLSearchParams({{range: currentRange}});
  if(rangeStart) qs.set('start', rangeStart);
  if(rangeEnd) qs.set('end', rangeEnd);
  const r=await fetch('/dashboard/trends?'+qs.toString(), {{cache:'no-store'}});
  const j=await r.json();
  const pts = j.points || [];
  drawLine('chartJobs', pts.map(x=>x.jobs_posted||0));
  drawLine('chartResumes', pts.map(x=>x.resumes_uploaded||0));
}}
async function refreshStats(){{
  const r=await fetch('/dashboard/stats?ts='+Date.now(),{{cache:'no-store'}});
  const j=await r.json();
  Object.keys(j).forEach(k=>{{const el=document.getElementById(k); if(el) el.textContent=j[k];}});
  renderTrends();
}}
Array.from(document.querySelectorAll('.chip[data-range]')).forEach(btn=>btn.addEventListener('click',()=>{{
  currentRange=btn.dataset.range||'weekly';
  rangeStart=''; rangeEnd='';
  const fd=document.getElementById('fromDate'); const td=document.getElementById('toDate');
  if(fd) fd.value=''; if(td) td.value='';
  Array.from(document.querySelectorAll('.chip[data-range]')).forEach(x=>x.classList.remove('active'));
  btn.classList.add('active');
  renderTrends();
}}));
const apply=document.getElementById('applyRange');
if(apply) apply.addEventListener('click',()=>{{
  rangeStart=(document.getElementById('fromDate')?.value||'').trim();
  rangeEnd=(document.getElementById('toDate')?.value||'').trim();
  renderTrends();
}});
window.addEventListener('resize', renderTrends);
const b=document.getElementById('burgerDash');
const n=document.getElementById('dashNav');
if(b&&n){{
  b.addEventListener('click',(e)=>{{
    e.stopPropagation();
    n.classList.toggle('open');
  }});
  n.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>n.classList.remove('open')));
  document.addEventListener('click',(e)=>{{
    if(!n.classList.contains('open')) return;
    const t=e.target;
    if(t instanceof Node && !n.contains(t) && t!==b) n.classList.remove('open');
  }});
  document.addEventListener('touchstart',(e)=>{{
    if(!n.classList.contains('open')) return;
    const t=e.target;
    if(t instanceof Node && !n.contains(t) && t!==b) n.classList.remove('open');
  }});
  document.addEventListener('keydown',(e)=>{{ if(e.key==='Escape') n.classList.remove('open'); }});
}}
refreshStats();
setInterval(refreshStats,5000);
</script>
</body></html>
"""
    return HTMLResponse(html_doc, headers={"Cache-Control": "no-store"})


@app.get('/candidates', response_class=HTMLResponse)
def candidates_page(request: Request, email: str = "", phone: str = "", status: str = "", page: int = 1, page_size: int = 50, export: str = ""):
    if not _is_authenticated(request):
        return RedirectResponse(url='/login', status_code=303)

    email_q = (email or "").strip().lower()
    phone_q = _normalize_phone(phone or "")
    status_q = (status or "").strip().lower()
    page = max(1, int(page or 1))
    page_size = max(10, min(200, int(page_size or 50)))
    offset = (page - 1) * page_size

    rows_html = ""
    total = 0
    rows = []
    conn = _db_conn()
    if conn:
        try:
            where = []
            params = []
            if email_q:
                where.append("lower(email) like %s")
                params.append(f"%{email_q}%")
            if phone_q:
                where.append("regexp_replace(coalesce(phone_number,''), '[^+0-9]', '', 'g') like %s")
                params.append(f"%{phone_q}%")
            if status_q:
                where.append("lower(status) = %s")
                params.append(status_q)
            clause = (" where " + " and ".join(where)) if where else ""

            with conn.cursor() as cur:
                cur.execute(f"select count(*) from public.screening_candidates {clause}", tuple(params))
                total = int((cur.fetchone() or [0])[0] or 0)

                cur.execute(
                    f"""
                    select candidate_id, full_name, email, phone_number, linkedin_profile, status,
                           coalesce(to_char(callback_received_at,'YYYY-MM-DD HH24:MI'),'') as callback_at,
                           coalesce(to_char(screening_completed_at,'YYYY-MM-DD HH24:MI'),'') as completed_at
                    from public.screening_candidates
                    {clause}
                    order by updated_at desc
                    limit %s offset %s
                    """,
                    tuple(params + [page_size, offset]),
                )
                rows = cur.fetchall()
        finally:
            conn.close()

    # CSV export of current filter set (all rows for filter, capped at 10k)
    if (export or "").lower() == "csv":
        conn = _db_conn()
        data = []
        if conn:
            try:
                where = []
                params = []
                if email_q:
                    where.append("lower(email) like %s")
                    params.append(f"%{email_q}%")
                if phone_q:
                    where.append("regexp_replace(coalesce(phone_number,''), '[^+0-9]', '', 'g') like %s")
                    params.append(f"%{phone_q}%")
                if status_q:
                    where.append("lower(status) = %s")
                    params.append(status_q)
                clause = (" where " + " and ".join(where)) if where else ""
                with conn.cursor() as cur:
                    cur.execute(
                        f"""
                        select candidate_id, full_name, email, phone_number, linkedin_profile, status,
                               coalesce(to_char(callback_received_at,'YYYY-MM-DD HH24:MI'),'') as callback_at,
                               coalesce(to_char(screening_completed_at,'YYYY-MM-DD HH24:MI'),'') as completed_at
                        from public.screening_candidates
                        {clause}
                        order by updated_at desc
                        limit 10000
                        """,
                        tuple(params),
                    )
                    data = cur.fetchall()
            finally:
                conn.close()
        import csv, io
        buff = io.StringIO()
        w = csv.writer(buff)
        w.writerow(["candidate_id","full_name","email","phone_number","linkedin_profile","status","callback_at","completed_at"])
        for r in data:
            w.writerow(list(r))
        return Response(content=buff.getvalue(), media_type='text/csv', headers={'Content-Disposition':'attachment; filename="candidates.csv"'})

    def _badge(st: str) -> str:
        st = (st or '').lower().strip()
        cls = 'b-neutral'
        short = {
            'initialized': 'INIT',
            'screening_in_progress': 'IN-PROG',
            'callback_received': 'CALLBK',
            'outbound_no_answer': 'NO-ANS',
            'screening_completed': 'DONE',
            'failed': 'FAIL',
            'busy': 'BUSY',
            'no-answer': 'NO-ANS',
        }.get(st, (st or 'unknown')[:10].upper())
        if st == 'screening_completed':
            cls = 'b-green'
        elif st in {'screening_in_progress', 'callback_received'}:
            cls = 'b-blue'
        elif st in {'outbound_no_answer', 'failed', 'busy', 'no-answer'}:
            cls = 'b-amber'
        return f"<span class='badge {cls}' title='{html.escape(st or 'unknown')}'>{html.escape(short)}</span>"

    for r in rows:
        cid = html.escape(str(r[0] or ''))
        nm = html.escape(str(r[1] or ''))
        rows_html += (
            f"<tr><td><a href='/candidates/{cid}' style='color:#0a3f9a;text-decoration:none'>{cid}</a></td>"
            f"<td><a href='/candidates/{cid}' style='color:#0a3f9a;text-decoration:none'>{nm}</a></td>"
            f"<td>{html.escape(str(r[2] or ''))}</td><td>{html.escape(str(r[3] or ''))}</td>"
            f"<td>{_badge(str(r[5] or ''))}</td>"
            f"<td>{html.escape(str(r[6] or ''))}</td><td>{html.escape(str(r[7] or ''))}</td></tr>"
        )
    if not rows_html:
        rows_html = "<tr><td colspan='7'>No candidate records found.</td></tr>"

    total_pages = max(1, (total + page_size - 1) // page_size)
    prev_page = page - 1 if page > 1 else 1
    next_page = page + 1 if page < total_pages else total_pages

    def _qs(pn: int):
        q = []
        if email_q: q.append(f"email={html.escape(email_q)}")
        if phone: q.append(f"phone={html.escape(phone)}")
        if status_q: q.append(f"status={html.escape(status_q)}")
        q.append(f"page={pn}")
        q.append(f"page_size={page_size}")
        return "&".join(q)

    html_doc = f"""
<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/><title>Candidates - Joblynk</title>
<style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:linear-gradient(180deg,#eef4ff 0%,#f8fbff 100%);margin:0;color:#0f172a}}
.site-header{{background:linear-gradient(90deg,#0b5fff,#0051c8);color:#fff;padding:14px 24px;box-shadow:0 6px 20px rgba(0,51,128,.2)}}
.header-inner{{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}}
.nav a{{color:#fff;text-decoration:none;font-weight:700;margin-left:12px;font-size:13px}}
.wrap{{max-width:1100px;margin:20px auto;padding:0 16px}}
.card{{background:#fff;border:1px solid #d7e5ff;border-radius:14px;padding:14px;box-shadow:0 10px 28px rgba(0,51,102,.08)}}
.filters{{display:grid;grid-template-columns:2fr 2fr 1fr auto auto;gap:10px;margin:10px 0 14px 0}}
input,select{{width:100%;padding:9px 10px;border:1px solid #bfd3f8;border-radius:10px;box-sizing:border-box}}
button,.btn{{padding:9px 12px;border:none;border-radius:10px;background:#0b5fff;color:#fff;font-weight:700;cursor:pointer;text-decoration:none;display:inline-block}}
table{{width:100%;border-collapse:collapse;font-size:12px;table-layout:fixed}} th,td{{border-bottom:1px solid #e7efff;padding:6px 7px;text-align:left;vertical-align:top;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}} th{{color:#35517a;background:#f7fbff}}
.small{{font-size:12px;color:#5b6b83}}
.badge{{padding:3px 8px;border-radius:999px;font-size:11px;font-weight:700;display:inline-block}}
.b-green{{background:#dcfce7;color:#166534;border:1px solid #86efac}}
.b-blue{{background:#dbeafe;color:#1d4ed8;border:1px solid #93c5fd}}
.b-amber{{background:#fff7ed;color:#9a3412;border:1px solid #fdba74}}
.b-neutral{{background:#eef2ff;color:#334155;border:1px solid #cbd5e1}}
.pager{{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-top:12px}}
@media (max-width:900px){{ .filters{{grid-template-columns:1fr}} .pager{{flex-direction:column;align-items:flex-start}} }}
</style></head><body>
<header class='site-header'><div class='header-inner'><div><b>Joblynk Screening Console</b></div><div class='nav'><a href='/dashboard'>Dashboard</a><a href='/ui'>InstantScreen</a><a href='/candidates'>Candidates</a><a href='/profile'>Profile</a><a href='/logout'>Logout</a></div></div></header>
<div class='wrap'><div class='card'><h2 style='margin:0 0 10px 0;color:#0a3f9a'>Candidate Records</h2><div class='small'>Search/filter by email, phone, and status.</div>
<form class='filters' method='GET' action='/candidates'>
  <input name='email' placeholder='Filter by email' value='{html.escape(email_q)}' />
  <input name='phone' placeholder='Filter by phone' value='{html.escape(phone or "")}' />
  <select name='status'>
    <option value=''>All Statuses</option>
    <option value='initialized' {'selected' if status_q=='initialized' else ''}>initialized</option>
    <option value='outbound_no_answer' {'selected' if status_q=='outbound_no_answer' else ''}>outbound_no_answer</option>
    <option value='callback_received' {'selected' if status_q=='callback_received' else ''}>callback_received</option>
    <option value='screening_in_progress' {'selected' if status_q=='screening_in_progress' else ''}>screening_in_progress</option>
    <option value='screening_completed' {'selected' if status_q=='screening_completed' else ''}>screening_completed</option>
  </select>
  <button type='submit'>Search</button>
  <a class='btn' href='/candidates?email={html.escape(email_q)}&phone={html.escape(phone or "")}&status={html.escape(status_q)}&export=csv'>Export CSV</a>
</form>
<table><thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Phone</th><th>St</th><th>CB At</th><th>Done At</th></tr></thead><tbody>{rows_html}</tbody></table>
<div class='pager'>
  <div class='small'>Showing page {page} of {total_pages} · {total} total records</div>
  <div>
    <a class='btn' href='/candidates?{_qs(prev_page)}'>Prev</a>
    <a class='btn' href='/candidates?{_qs(next_page)}' style='margin-left:8px'>Next</a>
  </div>
</div>
</div></div></body></html>
"""
    return HTMLResponse(html_doc, headers={'Cache-Control':'no-store'})


@app.get('/candidates/{candidate_id}', response_class=HTMLResponse)
def candidate_detail_page(candidate_id: str, request: Request, job_id: str = ''):
    if not _is_authenticated(request):
        return RedirectResponse(url='/login', status_code=303)

    cand = None
    calls_rows = []
    activity_rows = []
    resume_row = None
    conn = _db_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    select candidate_id, full_name, email, phone_number, linkedin_profile, status,
                           assigned_agent_email, coalesce(to_char(created_at,'YYYY-MM-DD HH24:MI'),'') created_at,
                           coalesce(to_char(updated_at,'YYYY-MM-DD HH24:MI'),'') updated_at,
                           coalesce(last_summary,''), coalesce(last_session_id,'')
                    from public.screening_candidates where candidate_id=%s limit 1
                    """,
                    (candidate_id,),
                )
                r = cur.fetchone()
                if r:
                    cand = {
                        'candidate_id': r[0], 'full_name': r[1], 'email': r[2], 'phone_number': r[3],
                        'linkedin_profile': r[4], 'status': r[5], 'assigned_agent_email': r[6],
                        'created_at': r[7], 'updated_at': r[8], 'last_summary': r[9], 'last_session_id': r[10]
                    }
                cur.execute(
                    """
                    select sc.call_sid, sc.direction, sc.from_number, sc.to_number, sc.call_status,
                           coalesce(sc.provider_used,''), coalesce(sc.provider_reason,''),
                           coalesce(to_char(sc.created_at,'YYYY-MM-DD HH24:MI'),'') created_at,
                           coalesce(to_char(sc.updated_at,'YYYY-MM-DD HH24:MI'),'') updated_at,
                           coalesce(sc.session_id,''),
                           coalesce(ss.job_id,''), coalesce(ss.job_title,'')
                    from public.screening_calls sc
                    left join public.screening_sessions ss on ss.session_id=sc.session_id
                    where sc.candidate_id=%s
                    order by sc.created_at desc
                    """,
                    (candidate_id,),
                )
                calls_rows = cur.fetchall()

                cur.execute(
                    """
                    select coalesce(to_char(created_at,'YYYY-MM-DD HH24:MI'),'') created_at,
                           coalesce(event_type,''), coalesce(details,''), coalesce(session_id,''), coalesce(call_sid,'')
                    from public.screening_candidate_activity
                    where candidate_id=%s
                    order by created_at desc
                    limit 300
                    """,
                    (candidate_id,),
                )
                activity_rows = cur.fetchall()

                # latest resume linked to candidate's last session
                cur.execute(
                    """
                    select upload_id, coalesce(original_filename,''), coalesce(to_char(created_at,'YYYY-MM-DD HH24:MI'),''), coalesce(stored_path,'')
                    from public.screening_resume_uploads
                    where session_id = coalesce((select last_session_id from public.screening_candidates where candidate_id=%s),'')
                    order by created_at desc
                    limit 1
                    """,
                    (candidate_id,),
                )
                resume_row = cur.fetchone()
        finally:
            conn.close()

    if not cand:
        raise HTTPException(status_code=404, detail='candidate not found')

    timeline_html = ""
    grouped = {}
    for c in calls_rows:
        jk = (c[10] or 'unmapped')
        grouped.setdefault(jk, []).append(c)

    ordered_keys = list(grouped.keys())
    if (job_id or '').strip() and (job_id in ordered_keys):
        ordered_keys = [job_id] + [k for k in ordered_keys if k != job_id]

    for jk in ordered_keys:
        rows = grouped.get(jk, [])
        jtitle = (rows[0][11] if rows else '') or ''
        timeline_html += f"<tr><td colspan='11' style='background:#f7fbff;font-weight:700'>Job ID: {html.escape(str(jk))} {('— '+html.escape(str(jtitle))) if jtitle else ''}</td></tr>"
        for c in rows:
            timeline_html += (
                f"<tr><td>{html.escape(str(c[0] or ''))}</td><td>{html.escape(str(c[1] or ''))}</td>"
                f"<td>{html.escape(str(c[2] or ''))}</td><td>{html.escape(str(c[3] or ''))}</td>"
                f"<td>{html.escape(str(c[4] or ''))}</td><td>{html.escape(str(c[5] or ''))}</td>"
                f"<td>{html.escape(str(c[6] or ''))}</td><td>{html.escape(str(c[7] or ''))}</td><td>{html.escape(str(c[8] or ''))}</td><td>{html.escape(str(c[9] or ''))}</td><td>{html.escape(str(c[10] or ''))}</td></tr>"
            )
    if not timeline_html:
        timeline_html = "<tr><td colspan='11'>No call timeline yet.</td></tr>"


    activity_html = ""
    for a in activity_rows:
        activity_html += (
            f"<tr><td>{html.escape(str(a[0] or ''))}</td><td>{html.escape(str(a[1] or ''))}</td>"
            f"<td>{html.escape(str(a[2] or ''))}</td><td>{html.escape(str(a[3] or ''))}</td><td>{html.escape(str(a[4] or ''))}</td></tr>"
        )
    if not activity_html:
        activity_html = "<tr><td colspan='5'>No activity recorded yet.</td></tr>"

    resume_html = "<div class='small'>No resume linked yet.</div>"
    if resume_row:
        upid, fname, uploaded_at, _spath = resume_row
        resume_html = f"<div class='small'>Latest Resume: <a href='/resume/file/{html.escape(str(upid))}' style='color:#0a3f9a;text-decoration:none'>{html.escape(str(fname or upid))}</a> <span style='color:#5b6b83'>(uploaded {html.escape(str(uploaded_at or ''))})</span></div>"

    qa_html = "<div class='small'>No interview timeline available for this candidate.</div>"
    sid = cand.get('last_session_id')
    sess = INTERVIEW_SESSIONS.get(sid or "") if sid else None
    if sess:
        qa = sess.get('completed_questions', []) or []
        parts = []
        for i, q in enumerate(qa, 1):
            parts.append(f"<div style='margin:8px 0'><div class='small'><b>Q{i}:</b> {html.escape(str(q.get('question','')))}</div><div class='small'><b>A{i}:</b> {html.escape(str(q.get('answer','')))}</div></div>")
        qa_html = "".join(parts) if parts else "<div class='small'>No interview Q/A captured yet.</div>"

    html_doc = f"""
<!doctype html><html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/><title>Candidate Detail - Joblynk</title>
<style>
body{{font-family:Inter,Segoe UI,Arial,sans-serif;background:linear-gradient(180deg,#eef4ff 0%,#f8fbff 100%);margin:0;color:#0f172a}}
.site-header{{background:linear-gradient(90deg,#0b5fff,#0051c8);color:#fff;padding:14px 24px;box-shadow:0 6px 20px rgba(0,51,128,.2)}}
.header-inner{{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}}
.nav a{{color:#fff;text-decoration:none;font-weight:700;margin-left:12px;font-size:13px}}
.wrap{{max-width:1100px;margin:20px auto;padding:0 16px}}
.card{{background:#fff;border:1px solid #d7e5ff;border-radius:14px;padding:14px;box-shadow:0 10px 28px rgba(0,51,102,.08);margin-bottom:12px}}
.kv{{display:grid;grid-template-columns:180px 1fr;gap:8px;font-size:13px}}
.small{{font-size:12px;color:#5b6b83}}
table{{width:100%;border-collapse:collapse;font-size:13px;display:block;overflow-x:auto;-webkit-overflow-scrolling:touch}} th,td{{border-bottom:1px solid #e7efff;padding:8px;text-align:left;vertical-align:top;white-space:nowrap}} th{{color:#35517a;background:#f7fbff}}
@media (max-width:900px){{ .kv{{grid-template-columns:1fr}} }}
</style></head><body>
<header class='site-header'><div class='header-inner'><div><b>Joblynk Screening Console</b></div><div class='nav'><a href='/dashboard'>Dashboard</a><a href='/ui'>InstantScreen</a><a href='/candidates'>Candidates</a><a href='/profile'>Profile</a><a href='/logout'>Logout</a></div></div></header>
<div class='wrap'>
  <div class='card'>
    <h2 style='margin:0 0 10px 0;color:#0a3f9a'>Candidate Detail</h2>
    <div class='kv'>
      <div class='small'>Candidate ID</div><div>{html.escape(str(cand.get('candidate_id','')))}</div>
      <div class='small'>Full Name</div><div>{html.escape(str(cand.get('full_name','')))}</div>
      <div class='small'>Email</div><div>{html.escape(str(cand.get('email','')))}</div>
      <div class='small'>Phone</div><div>{html.escape(str(cand.get('phone_number','')))}</div>
      <div class='small'>LinkedIn</div><div>{("<a href='" + html.escape(str(cand.get('linkedin_profile',''))) + "' target='_blank' rel='noopener noreferrer' style='color:#0a3f9a;text-decoration:none'>" + html.escape(str(cand.get('linkedin_profile',''))) + "</a>") if (cand.get('linkedin_profile') or '').strip() else ''}</div>
      <div class='small'>Status</div><div>{html.escape(str(cand.get('status','')))}</div>
      <div class='small'>Current Interview Status</div><div>{html.escape(str(cand.get('status','')))}</div>
      <div class='small'>Assigned Agent</div><div>{html.escape(str(cand.get('assigned_agent_email','')))}</div>
      <div class='small'>Last Session</div><div>{html.escape(str(cand.get('last_session_id','')))}</div>
      <div class='small'>Created / Updated</div><div>{html.escape(str(cand.get('created_at','')))} / {html.escape(str(cand.get('updated_at','')))}</div>
      <div class='small'>Latest Summary</div><div>{html.escape(str(cand.get('last_summary','')))}</div>
    </div>
  </div>

  <div class='card'>
    <h3 style='margin:0 0 8px 0;color:#0a3f9a'>Resume</h3>
    {resume_html}
  </div>

  <div class='card'>
    <h3 style='margin:0 0 8px 0;color:#0a3f9a'>Interview / Call Logs (Grouped by Job ID)</h3>
    <table><thead><tr><th>Call SID</th><th>Direction</th><th>From</th><th>To</th><th>Status</th><th>Provider</th><th>Provider Reason</th><th>Created</th><th>Updated</th><th>Session</th><th>Job ID</th></tr></thead><tbody>{timeline_html}</tbody></table>
  </div>

  <div class='card'>
    <h3 style='margin:0 0 8px 0;color:#0a3f9a'>Activity Log</h3>
    <table><thead><tr><th>When</th><th>Event</th><th>Details</th><th>Session</th><th>Call SID</th></tr></thead><tbody>{activity_html}</tbody></table>
  </div>

  <div class='card'>
    <h3 style='margin:0 0 8px 0;color:#0a3f9a'>Interview Timeline</h3>
    {qa_html}
  </div>
</div></body></html>
"""
    return HTMLResponse(html_doc, headers={'Cache-Control':'no-store'})


@app.delete("/jobs/{job_id}")
def delete_job(job_id: str):
    conn = _db_conn()
    deleted = False
    if conn:
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("delete from public.screening_jobs where job_id=%s", (job_id,))
                    deleted = cur.rowcount > 0
        except Exception as e:
            log_event(f"DB_JOB_DELETE_FAIL | {e}")
        finally:
            conn.close()
    if job_id in JOB_POSTINGS:
        JOB_POSTINGS.pop(job_id, None)
        deleted = True or deleted
    if not deleted:
        raise HTTPException(status_code=404, detail="job not found")
    return {"ok": True, "job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    conn = _db_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("select job_id, title, job_description, created_at from public.screening_jobs where job_id=%s", (job_id,))
                r = cur.fetchone()
                if r:
                    return {
                        "job_id": r[0],
                        "title": r[1],
                        "job_description": r[2],
                        "created_at": r[3].isoformat() if r[3] else "",
                    }
        except Exception as e:
            log_event(f"DB_JOB_GET_FAIL | {e}")
        finally:
            conn.close()

    j = JOB_POSTINGS.get(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="job not found")
    return j


@app.get("/interview/jobs")
def interview_jobs():
    items = []
    terminal = {"completed", "failed", "busy", "no-answer", "no answer", "canceled", "cancelled"}
    for sid, s in INTERVIEW_SESSIONS.items():
        calls = s.get("calls", []) or []
        latest_call = calls[-1] if calls else {}
        latest_status = (latest_call.get("status") or "").lower()
        last_status = (s.get("last_call_status", "") or "").lower()

        # Reconcile session-level status with latest call status so UI stays consistent.
        effective_status = latest_status or last_status
        if effective_status:
            s["last_call_status"] = effective_status

        call_in_progress = bool(s.get("call_in_progress", False))

        # Auto-finalize stale in-progress calls so UI doesn't get stuck forever.
        if latest_call and effective_status in {"initiated", "ringing", "answered", "in-progress", "queued"} and _is_stale_call(latest_call, ttl_seconds=120):
            effective_status = "no-answer"
            s["last_call_status"] = "no-answer"
            latest_call["status"] = "no-answer"

        if s.get("completed") or effective_status in terminal:
            call_in_progress = False
            s["call_in_progress"] = False
            s["completed"] = True

        # If call is completed but recommendation is still pending/empty, finalize recommendation.
        rec = (s.get("recommendation", "") or "").strip()
        if effective_status == "completed" and (not rec or rec.lower().startswith("pending")):
            s["recommendation"] = _recommendation_for_session(s)

        items.append({
            "session_id": sid,
            "job_title": s.get("job_title", "Untitled Role"),
            "job_id": s.get("job_id", ""),
            "candidate_id": s.get("candidate_id", ""),
            "candidate_name": s.get("candidate_name", "") or "Unknown Candidate",
            "candidate_phone": s.get("candidate_phone", ""),
            "candidate_email": s.get("candidate_email", ""),
            "status": s.get("status"),
            "ready": s.get("ready", False),
            "completed": bool(s.get("completed", False)),
            "created_at": s.get("created_at"),
            "call_in_progress": call_in_progress,
            "last_call_status": s.get("last_call_status", ""),
            "completed_questions": s.get("completed_questions", []),
            "recommendation": s.get("recommendation", ""),
            "calls": calls,
        })
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return {"jobs": items}


def _is_stale_call(c: dict, ttl_seconds: int = 360) -> bool:
    try:
        at = (c or {}).get("at")
        if not at:
            return False
        s = str(at).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds()
        return age > ttl_seconds
    except Exception:
        return False


def _recruiter_call_status(last_call_status: str, candidate_status: str = "") -> str:
    l = (last_call_status or "").strip().lower()
    c = (candidate_status or "").strip().lower()
    if l == "completed" or c == "screening_completed":
        return "Attended Call"
    if l in {"busy", "failed", "no-answer", "no answer", "canceled", "cancelled"}:
        return "Need to Call Back"
    if c == "callback_received":
        return "Call Back Required"
    if l in {"ringing", "initiated", "answered", "in-progress", "queued"}:
        return "In Progress"
    return "No Response"


@app.get("/interview/candidates")
def interview_candidates(job_id: str = ""):
    target = (job_id or "").strip()
    out = []
    conn = _db_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                where = []
                params = []
                if target:
                    where.append("coalesce(ss.job_id,'')=%s")
                    params.append(target)
                where_sql = (" where " + " and ".join(where)) if where else ""
                cur.execute(
                    f"""
                    select
                      sc.candidate_id,
                      coalesce(c.full_name,'Unknown Candidate') as full_name,
                      coalesce(c.phone_number,'') as phone,
                      coalesce(c.email,'') as email,
                      coalesce(c.status,'') as candidate_status,
                      coalesce(ss.job_id,'') as job_id,
                      coalesce(ss.job_title,'') as job_title,
                      coalesce(sc.session_id,'') as session_id,
                      coalesce(sc.call_status,'') as last_call_status,
                      max(sc.updated_at) as last_updated
                    from public.screening_calls sc
                    left join public.screening_candidates c on c.candidate_id=sc.candidate_id
                    left join public.screening_sessions ss on ss.session_id=sc.session_id
                    {where_sql}
                    group by sc.candidate_id, c.full_name, c.phone_number, c.email, c.status, ss.job_id, ss.job_title, sc.session_id, sc.call_status
                    order by max(sc.updated_at) desc
                    """,
                    tuple(params),
                )
                for r in cur.fetchall():
                    out.append({
                        "candidate_id": r[0] or "",
                        "candidate_name": r[1] or "Unknown Candidate",
                        "candidate_phone": r[2] or "",
                        "candidate_email": r[3] or "",
                        "candidate_status": r[4] or "",
                        "job_id": r[5] or "",
                        "job_title": r[6] or "",
                        "session_id": r[7] or "",
                        "last_call_status": r[8] or "",
                        "call_status": _recruiter_call_status(r[8] or "", r[4] or ""),
                        "profile_url": f"/candidates/{r[0]}?job_id={(r[5] or '')}" if r[0] else "",
                        "created_at": str(r[9] or ""),
                    })
        except Exception as e:
            log_event(f"INTERVIEW_CANDIDATES_DB_FAIL | {e}")
        finally:
            conn.close()
    return {"candidates": out}


@app.get("/interview/session/{session_id}")
def interview_session(session_id: str):
    s = INTERVIEW_SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    return s


@app.get("/interview/status/{session_id}")
def interview_status(session_id: str):
    s = INTERVIEW_SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")

    order = ["starting", "parsing_resume", "parsing_jd", "skill_mapping", "interview_plan_generation", "agent_session_initialization", "ready"]
    current = s.get("status", "starting")
    idx = order.index(current) if current in order else 0
    progress = int((idx / (len(order) - 1)) * 100)

    steps = {
        "parsing_resume": order.index("parsing_resume") <= idx,
        "parsing_jd": order.index("parsing_jd") <= idx,
        "skill_mapping": order.index("skill_mapping") <= idx,
        "interview_plan_generation": order.index("interview_plan_generation") <= idx,
        "agent_session_initialization": order.index("agent_session_initialization") <= idx,
        "ready": current == "ready",
    }

    terminal = {"completed", "failed", "busy", "no-answer", "canceled", "cancelled"}
    last_call_status = (s.get("last_call_status", "") or "").lower()
    completed = bool(s.get("completed")) or (last_call_status in terminal)

    return {
        "status": current,
        "ready": s.get("ready", False),
        "start_triggered": s.get("start_triggered", False),
        "plan_count": len(s.get("plan", [])),
        "progress": progress,
        "steps": steps,
        "error": s.get("error", ""),
        "fit_evaluation": s.get("fit_evaluation", ""),
        "completed": completed,
        "last_call_status": s.get("last_call_status", ""),
    }


@app.post("/interview/start/{session_id}")
def interview_start(session_id: str):
    s = INTERVIEW_SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    if not s.get("ready"):
        raise HTTPException(status_code=400, detail="session not ready")
    s["start_triggered"] = True
    return {"ok": True, "session_id": session_id, "start_triggered": True}


@app.post("/interview/call/{session_id}")
def interview_call(session_id: str, to: str = Form(...), agent_profile: str = Form("sara"), x_api_key: str | None = Header(default=None)):
    verify_call_api_key(x_api_key)
    s = INTERVIEW_SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")
    if not s.get("ready") or not s.get("start_triggered"):
        raise HTTPException(status_code=400, detail="session not ready to call")

    profile_key = (agent_profile or "adam").strip().lower()
    profile = _resolve_agent_profile(profile_key)
    s["agent_profile"] = profile_key
    s["assistant_name"] = profile.get("assistant_name")
    s["elevenlabs_voice_id"] = profile.get("elevenlabs_voice_id")
    s["twilio_fallback_voice"] = profile.get("twilio_fallback_voice")
    s["prompt_handshake_done"] = False
    s["dialogue"] = []
    s["prompt_q_idx"] = 0
    s["repeat_reply_count"] = 0
    s["last_prompt_reply"] = ""
    s["awaiting_final_questions"] = False
    s["handoff_requested"] = False

    client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    status_cb = f"{PUBLIC_BASE_URL}/twilio/status?session_id={session_id}"
    call = client.calls.create(
        to=to,
        from_=TWILIO_PHONE_NUMBER,
        url=f"{PUBLIC_BASE_URL}/twilio/voice?session_id={session_id}",
        method="POST",
        machine_detection="Enable",
        status_callback=status_cb,
        status_callback_event=["initiated", "ringing", "answered", "completed"],
        status_callback_method="POST",
    )
    s["call_in_progress"] = True
    s["last_call_status"] = "initiated"
    s.setdefault("calls", []).append({"call_sid": call.sid, "to": to, "at": _now(), "status": "initiated"})
    _mark_call_provider(call.sid, "pending", f"scripted_session_flow_started:mode_{_provider_mode()}")

    # Immediate persistence at Start Call click.
    candidate_id = _ensure_candidate_for_session(session_id, to)
    try:
        conn = _db_conn()
        if conn:
            with conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        insert into public.screening_calls (
                          call_sid, candidate_id, session_id, direction, from_number, to_number, call_status, provider_used, provider_reason, updated_at
                        )
                        values (%s,%s,%s,'outbound',%s,%s,'initiated',%s,%s,now())
                        on conflict (call_sid) do update set
                          candidate_id=excluded.candidate_id,
                          session_id=excluded.session_id,
                          from_number=excluded.from_number,
                          to_number=excluded.to_number,
                          call_status='initiated',
                          provider_used=coalesce(excluded.provider_used, public.screening_calls.provider_used),
                          provider_reason=coalesce(excluded.provider_reason, public.screening_calls.provider_reason),
                          updated_at=now()
                        """,
                        (call.sid, candidate_id or None, session_id, TWILIO_PHONE_NUMBER, to, None, None),
                    )
                    if candidate_id:
                        cur.execute(
                            "update public.screening_candidates set status='screening_in_progress', last_session_id=%s, updated_at=now() where candidate_id=%s",
                            (session_id, candidate_id),
                        )
            conn.close()
    except Exception as e:
        log_event(f"START_CALL_PERSIST_FAIL | {e}")

    if candidate_id:
        _log_candidate_activity(candidate_id, "start_call_clicked", f"Outbound call started to {to}", session_id=session_id, call_sid=call.sid)

    return {"status": "started", "call_sid": call.sid, "to": to, "session_id": session_id}


@app.get("/interview/call-status/{session_id}/{call_sid}")
def interview_call_status(session_id: str, call_sid: str, x_api_key: str | None = Header(default=None)):
    verify_call_api_key(x_api_key)
    s = INTERVIEW_SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")

    try:
        client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        c = client.calls(call_sid).fetch()
        st = (getattr(c, 'status', '') or '').lower()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Twilio status fetch failed: {e}")

    terminal = {"completed", "failed", "busy", "no-answer", "canceled", "cancelled"}
    s["last_call_status"] = st
    s["call_in_progress"] = st not in terminal
    if st in terminal:
        s["completed"] = True
        if not s.get("recommendation"):
            s["recommendation"] = _recommendation_for_session(s)

    for row in s.get("calls", []):
        if row.get("call_sid") == call_sid:
            row["status"] = st
            row["updated_at"] = _now()

    cid = _ensure_candidate_for_session(session_id)
    try:
        conn = _db_conn()
        if conn:
            with conn:
                with conn.cursor() as cur:
                    provider_meta = CALL_PROVIDER_TRACK.get(call_sid or "", {})
                    cur.execute(
                        """
                        insert into public.screening_calls (
                          call_sid, candidate_id, session_id, direction, from_number, to_number, call_status, provider_used, provider_reason, updated_at
                        )
                        values (%s,%s,%s,'outbound',%s,%s,%s,%s,%s,now())
                        on conflict (call_sid) do update set
                          call_status=excluded.call_status,
                          provider_used=coalesce(excluded.provider_used, public.screening_calls.provider_used),
                          provider_reason=coalesce(excluded.provider_reason, public.screening_calls.provider_reason),
                          updated_at=now()
                        """,
                        (
                            call_sid,
                            cid or None,
                            session_id,
                            TWILIO_PHONE_NUMBER,
                            '',
                            st,
                            provider_meta.get("provider_used"),
                            provider_meta.get("provider_reason"),
                        ),
                    )
            conn.close()
    except Exception as e:
        log_event(f"CALL_STATUS_SYNC_FAIL | {e}")

    return {"ok": True, "status": st, "completed": st in terminal}


@app.post("/interview/end/{session_id}")
def interview_end(session_id: str, x_api_key: str | None = Header(default=None)):
    """Manual recruiter fallback: force-end active call and finalize session state."""
    verify_call_api_key(x_api_key)
    s = INTERVIEW_SESSIONS.get(session_id)
    if not s:
        raise HTTPException(status_code=404, detail="session not found")

    active_sid = ""
    for c in reversed(s.get("calls", [])):
        if (c.get("status") or "").lower() not in {"completed", "failed", "busy", "no-answer", "canceled"}:
            active_sid = c.get("call_sid", "")
            break

    ended_remote = False
    if active_sid:
        try:
            client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
            client.calls(active_sid).update(status="completed")
            ended_remote = True
        except Exception as e:
            log_event(f"CALL_FORCE_END_FAIL sid={active_sid} err={e}")

    s["call_in_progress"] = False
    s["last_call_status"] = "completed"
    s["completed"] = True
    s["intro_phase"] = "done"
    s["current_question"] = ""
    if not s.get("recommendation"):
        s["recommendation"] = _recommendation_for_session(s)

    for c in s.get("calls", []):
        if not active_sid or c.get("call_sid") == active_sid:
            c["status"] = "completed"
            c["updated_at"] = _now()

    return {"ok": True, "session_id": session_id, "call_sid": active_sid, "ended_remote": ended_remote}


def _load_jobs_rows(limit: int = 200) -> list[dict]:
    conn = _db_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("select job_id, title, job_description, created_at from public.screening_jobs order by created_at desc limit %s", (limit,))
                rows = cur.fetchall()
                return [
                    {
                        "job_id": r[0],
                        "title": r[1],
                        "job_description": r[2],
                        "created_at": r[3].isoformat() if r[3] else "",
                    }
                    for r in rows
                ]
        except Exception as e:
            log_event(f"DB_LOAD_ROWS_FAIL | {e}")
        finally:
            conn.close()
    items = list(JOB_POSTINGS.values())
    items.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return items[:limit]


def _safe_editor_html(raw: str) -> str:
    val = raw or ""
    # If full HTML doc was pasted/saved, keep only body content.
    body_match = re.search(r"<body[^>]*>(.*?)</body>", val, flags=re.IGNORECASE | re.DOTALL)
    if body_match:
        val = body_match.group(1)
    # Remove tags that can alter page layout/scripts when injected into contenteditable.
    val = re.sub(r"<(script|style|meta|link|iframe|object|embed)[^>]*>.*?</\1>", "", val, flags=re.IGNORECASE | re.DOTALL)
    val = re.sub(r"<(script|style|meta|link|iframe|object|embed)[^>]*/?>", "", val, flags=re.IGNORECASE)
    return val


def _generate_job_id() -> str:
    # 10-digit numeric id starting with 201xxxxxxx
    conn = _db_conn()
    try:
        for _ in range(25):
            candidate = "201" + "".join(secrets.choice("0123456789") for _ in range(7))
            if candidate in JOB_POSTINGS:
                continue
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("select 1 from public.screening_jobs where job_id=%s limit 1", (candidate,))
                        if cur.fetchone():
                            continue
                except Exception:
                    pass
            return candidate
    finally:
        if conn:
            conn.close()
    # extremely unlikely fallback
    return "201" + str(int(time.time()))[-7:]


def _format_est_display(iso_text: str) -> str:
    try:
        dt = datetime.fromisoformat((iso_text or "").replace("Z", "+00:00"))
        if ZoneInfo:
            est = dt.astimezone(ZoneInfo("America/New_York"))
            return est.strftime("%m/%d/%Y %I:%M %p %Z")
        est = dt.astimezone(timezone(timedelta(hours=-5)))
        return est.strftime("%m/%d/%Y %I:%M %p EST")
    except Exception:
        return iso_text or ""


def _server_jobs_html() -> str:
    rows = _load_jobs_rows(100)
    out = []
    for x in rows:
        jid = x.get('job_id','')
        title = x.get('title','Untitled Role')
        created = _format_est_display(x.get('created_at',''))
        desc = re.sub(r"<[^>]*>", " ", x.get('job_description','') or "")
        desc = re.sub(r"\s+", " ", desc).strip()[:140] or "No description"
        out.append(
            f"<div class='job'><div class='small job-title-ellipsis' style='font-weight:700;color:#0a3f9a'>{html.escape(jid)} — {title}</div>"
            f"<div class='small'>{html.escape(desc)}</div>"
            f"<div class='small'>{created}</div>"
            f"<div class='row'>"
            f"<form method='POST' action='/ui/use-job' style='display:inline'>"
            f"<input type='hidden' name='job_id' value='{jid}'/>"
            f"<button class='useJobBtn' type='submit' data-job='{jid}'>Load Job</button>"
            f"</form>"
            f"<form method='POST' action='/ui/delete-job' style='display:inline'>"
            f"<input type='hidden' name='job_id' value='{jid}'/>"
            f"<button class='delJobBtn' type='submit' title='Delete Job'>Delete</button>"
            f"</form></div></div>"
        )
    return "".join(out) if out else "<div class='small'>No jobs found yet.</div>"


@app.post("/ui/save-job")
def ui_save_job(title: str = Form(...), job_description: str = Form(...), job_id: str = Form(default="")):
    title = (title or "").strip()
    job_description = (job_description or "").strip()
    job_id = (job_id or "").strip()
    # Accept rich text HTML from editor; reject only if effectively empty
    plain = job_description.replace("<br>", "").replace("<div>", "").replace("</div>", "").replace("&nbsp;", "").strip()
    if not title or not plain:
        return RedirectResponse(url="/ui?saved=0", status_code=303)

    if job_id:
        # update existing job (do not create a duplicate row)
        updated = False
        conn = _db_conn()
        if conn:
            try:
                with conn:
                    with conn.cursor() as cur:
                        cur.execute("update public.screening_jobs set title=%s, job_description=%s where job_id=%s", (title, job_description, job_id))
                        updated = cur.rowcount > 0
            except Exception as e:
                log_event(f"DB_JOB_UPDATE_FAIL | {e}")
            finally:
                conn.close()
        if job_id in JOB_POSTINGS:
            JOB_POSTINGS[job_id]["title"] = title
            JOB_POSTINGS[job_id]["job_description"] = job_description
            updated = True
        if updated:
            return RedirectResponse(url=f"/ui?saved=updated&use_job={job_id}", status_code=303)

    # Prevent accidental duplicates on repeated Save clicks for same content.
    conn = _db_conn()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute("select job_id from public.screening_jobs where title=%s and job_description=%s order by created_at desc limit 1", (title, job_description))
                ex = cur.fetchone()
                if ex and ex[0]:
                    return RedirectResponse(url=f"/ui?saved=1&use_job={ex[0]}", status_code=303)
        except Exception:
            pass
        finally:
            conn.close()

    created = create_job(JobCreateRequest(title=title, job_description=job_description))
    created_id = (created or {}).get("job_id", "")
    if created_id:
        return RedirectResponse(url=f"/ui?saved=1&use_job={created_id}", status_code=303)
    return RedirectResponse(url="/ui?saved=1", status_code=303)


@app.post('/ui/delete-job')
def ui_delete_job(job_id: str = Form(...)):
    try:
        delete_job(job_id)
        return RedirectResponse(url='/ui?deleted=1', status_code=303)
    except Exception:
        return RedirectResponse(url='/ui?deleted=0', status_code=303)


@app.post('/ui/use-job')
def ui_use_job(job_id: str = Form(...)):
    return RedirectResponse(url=f'/ui?use_job={job_id}', status_code=303)


@app.get("/ui", response_class=HTMLResponse)
def landing_ui(request: Request):
    saved = request.query_params.get("saved", "")
    deleted = request.query_params.get("deleted", "")
    use_job = request.query_params.get("use_job", "")
    new_job = request.query_params.get("new", "")
    selected_job_id = ""
    selected_title = ""
    selected_jd = ""
    selected_jd_html = ""
    phone_value = "+17732739855"
    if new_job == "1":
        selected_job_id = ""
        selected_title = ""
        selected_jd = ""
        selected_jd_html = ""
        phone_value = ""
    elif use_job:
        try:
            j = get_job(use_job)
            selected_job_id = j.get('job_id','')
            selected_title = j.get('title','')
            selected_jd = j.get('job_description','')
        except Exception:
            pass
    if re.search(r"</?(div|p|br|ul|ol|li|b|i|strong|em|h[1-6]|span)\b", selected_jd, re.IGNORECASE):
        selected_jd_html = _safe_editor_html(selected_jd)
    else:
        selected_jd_html = html.escape(selected_jd).replace("\n", "<br>")
    html_doc = """
<!doctype html>
<html><head><meta charset='utf-8'/><meta name='viewport' content='width=device-width,initial-scale=1'/>
<title>Softwise Screening Console</title>
<link href='https://cdn.quilljs.com/1.3.7/quill.snow.css' rel='stylesheet'>
<style>
:root{--jb-blue:#0b5fff;--jb-blue-dark:#003b8f;--jb-bg:#f3f7ff;--jb-border:#d7e5ff;--jb-text:#0f172a;--jb-muted:#5b6b83;--jb-card:#ffffff}
*{box-sizing:border-box}
body{font-family:Inter,Segoe UI,Arial,sans-serif;background:linear-gradient(180deg,#eef4ff 0%,#f8fbff 100%);margin:0;color:var(--jb-text)}
.site-header{background:linear-gradient(90deg,#0b5fff,#0051c8);color:#fff;padding:14px 24px;box-shadow:0 6px 20px rgba(0,51,128,.2);box-shadow:0 6px 20px rgba(0,51,128,.2)}
.header-inner{max-width:1100px;margin:0 auto;display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px}
.brand{font-weight:800;letter-spacing:.2px}
.tag{font-size:12px;opacity:.9}
.nav a{color:#fff;text-decoration:none;font-weight:700;margin-left:12px;font-size:13px}
.burger{display:none;background:transparent;border:1px solid rgba(255,255,255,.45);color:#fff;border-radius:8px;padding:6px 10px;font-weight:700}
.container{padding:22px 24px}
.wrap{max-width:1100px;margin:0 auto;display:grid;grid-template-columns:1.3fr .8fr;gap:18px}
.card{background:var(--jb-card);border:1px solid var(--jb-border);border-radius:14px;padding:18px;box-shadow:0 10px 28px rgba(0,51,102,.08)}
.titleRow{display:flex;justify-content:space-between;align-items:center;gap:10px;margin-bottom:8px}
h2{margin:0;color:#0a3f9a}.muted{color:var(--jb-muted);font-size:13px}
#newJobBtn{background:linear-gradient(135deg,#334155,#1e293b);color:#fff;border-radius:10px;padding:10px 14px;font-weight:700;text-decoration:none;display:inline-block;box-shadow:0 6px 16px rgba(15,23,42,.22);white-space:nowrap}
#newJobBtn:hover{filter:brightness(1.06)}
label{font-size:13px;font-weight:700;color:#29415f}
textarea,input{width:100%;padding:11px;border:1px solid #bfd3f8;border-radius:10px;margin-top:6px;margin-bottom:10px;background:#fff}
textarea:focus,input:focus{outline:none;border-color:var(--jb-blue);box-shadow:0 0 0 3px rgba(11,95,255,.12)}
button{background:linear-gradient(135deg,var(--jb-blue) 0%,#0a66d6 100%);color:#fff;border:none;border-radius:10px;padding:8px 12px;font-weight:700;cursor:pointer;transition:transform .06s,filter .15s,opacity .15s;line-height:1.2}
button:hover{filter:brightness(1.04)}
button:active{transform:translateY(1px) scale(.99)}
button.loading{opacity:.75;pointer-events:none}
button[disabled]{opacity:.45;cursor:not-allowed}
.status-success{background:linear-gradient(135deg,#16a34a,#15803d) !important;color:#fff !important}
.input-missing{border-color:#dc2626 !important;box-shadow:0 0 0 3px rgba(220,38,38,.18) !important;background:#fff7f7 !important}
#screeningBtn.ready-call{background:linear-gradient(135deg,#16a34a,#15803d)}
.row{display:flex;gap:12px;flex-wrap:wrap;align-items:center}
.row button{flex:0 0 auto;min-width:140px;max-width:220px}
.row > *{margin-bottom:6px}
pre{background:var(--jb-blue-dark);color:#dbe9ff;border-radius:10px;padding:12px;min-height:140px;white-space:pre-wrap}
#fitEval{background:#f8fbff;color:#0f172a;border:1px solid #dbe7ff;line-height:1.5;padding:12px;border-radius:10px}
.fit-h{font-weight:800;color:#0a3f9a;margin-top:8px}
.fit-k{font-weight:700;color:#1f3b64}
.fit-b{margin-left:12px}
.fit-row{display:grid;grid-template-columns:220px 1fr;gap:8px;align-items:start;margin:2px 0}
.fit-label{font-weight:800;color:#1f3b64}
.fit-value{color:#0f172a}
.fit-block{margin:6px 0}
.fit-block .fit-label{display:block;margin-bottom:4px}
.fit-block .fit-value{display:block;width:100%}
.table{font-size:13px}.job{padding:10px;border:1px solid #dbe7ff;border-radius:10px;margin-bottom:8px;background:#f7fbff}
.session-card{padding:12px;border:1px solid #cfe0ff;border-radius:12px;background:#f8fbff;margin-bottom:12px}
.session-divider{border:none;border-top:1px dashed #c7d9ff;margin:10px 0 0 0}
.session-head{display:flex;justify-content:space-between;align-items:center;gap:8px;margin-bottom:6px}
.session-id{font-size:12px;color:#5b6b83}
.label{font-size:11px;color:#476287;text-transform:uppercase;letter-spacing:.4px;font-weight:700}
.kv{display:grid;grid-template-columns:140px 1fr;gap:6px 10px;align-items:start}
.kv .k{font-size:12px;color:#476287;font-weight:700}
.kv .v{font-size:13px;color:#0f172a;word-break:break-word}
.small{font-size:12px;color:var(--jb-muted)}
.fit-badge{display:inline-block;padding:4px 8px;border-radius:999px;font-size:11px;font-weight:700;margin-top:6px}
.fit-strong{background:#dcfce7;color:#166534;border:1px solid #86efac}
.fit-moderate{background:#fff7ed;color:#9a3412;border:1px solid #fdba74}
.fit-low{background:#fee2e2;color:#991b1b;border:1px solid #fca5a5}
.job .row{margin-top:8px}
.job .row button{padding:7px 10px;border-radius:8px;font-size:12px;line-height:1.1}
.job .row .delJobBtn{background:#b42318 !important;color:#fff;display:inline-block !important;opacity:1 !important}
.job-title-ellipsis{display:block;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}
.site-footer{margin-top:20px;padding:14px 24px;border-top:1px solid #d8e4ff;color:#5e718f;background:#f7faff}
.footer-inner{max-width:1100px;margin:0 auto;font-size:12px;display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
@media (max-width: 900px){
  .container{padding:12px}
  .wrap{grid-template-columns:1fr;gap:12px}
  .card{padding:14px}
  .titleRow{flex-direction:column;align-items:flex-start}
  .row{flex-direction:column;align-items:stretch}
  .row button{width:100%}
  .burger{display:block}
  .nav{position:fixed;top:0;right:-260px;width:240px;height:100vh;background:#0b5fff;padding:70px 14px 14px;display:flex;flex-direction:column;gap:8px;transition:right .25s ease;z-index:20;box-shadow:-8px 0 24px rgba(0,0,0,.2)}
  .nav.open{right:0}
  .nav a{margin-left:0;font-size:14px;padding:8px 4px}
  input,textarea{font-size:16px}
  #jdEditor .ql-container{height:220px;max-height:220px}
  .kv{grid-template-columns:1fr}
  .fit-row{grid-template-columns:1fr}
  .fit-label{margin-bottom:2px}
}
#jdEditor{border:1px solid #bfd3f8;border-radius:10px;background:#fff;margin-bottom:18px}
#jdEditor .ql-toolbar{border:none;border-bottom:1px solid #e2ebff;border-top-left-radius:10px;border-top-right-radius:10px}
#jdEditor .ql-container{border:none;height:260px;max-height:260px;overflow:auto;border-bottom-left-radius:10px;border-bottom-right-radius:10px}
#jdEditor .ql-editor{min-height:260px;white-space:pre-wrap;font-family:Inter,Segoe UI,Arial,sans-serif;line-height:1.5}
#genPrompt{font-family:Inter,Segoe UI,Arial,sans-serif;line-height:1.45}
#jobTitle{font-family:Inter,Segoe UI,Arial,sans-serif;font-weight:700}
#saveJob{margin-top:12px}
#saveJobForm .row{margin-top:14px}
</style></head>
<body>
<header class='site-header'><div class='header-inner'><div><div class='brand'>Joblynk Screening Console</div><div class='tag'>Enterprise Interview Workflow</div></div><button id='burgerUi' class='burger' type='button'>☰</button><div class='nav' id='uiNav'><a href='/dashboard'>Dashboard</a><a href='/ui'>InstantScreen</a><a href='/candidates'>Candidates</a><a href='/profile'>Profile</a><a href='/logout'>Logout</a></div></div></header>
<div class='container'><div class='wrap'>
<div class='card'>
<div class='titleRow'><div><h2>InstantScreen</h2></div><a href='/ui?new=1' id='newJobBtn'>+ Start New Job</a></div>
<form id='saveJobForm' method='POST' action='/ui/save-job'>
<input type='hidden' id='jobId' name='job_id' value='__SELECTED_JOB_ID__'/>
<div style='padding:10px;border:1px solid #dbe7ff;border-radius:10px;background:#f8fbff;margin-bottom:10px'>
  <div style='font-weight:800;color:#0a3f9a;margin-bottom:6px'>Generate with AI</div>
  <div class='small' style='margin-bottom:8px'>Describe the role in one prompt (ChatGPT style), then generate full job post.</div>
  <textarea id='genPrompt' rows='4' placeholder='Example: Senior Full Stack Engineer in Dallas, React + Django + Postgres, build scalable features, mentor team, own delivery...'></textarea>
  <div class='row'><button type='button' id='genJobPostBtn'>Generate Job Post</button></div>
</div>
<label>Job Title</label><input id='jobTitle' name='title' value='__SELECTED_TITLE__' placeholder='e.g. Senior Unix/Linux Administrator'/>
<label>Job Description</label>
<div id='jdEditor'></div>
<textarea id='jd' name='job_description' style='display:none'></textarea>
<div class='row' style='margin-top:10px'><button id='saveJob' type='submit'>Save Now</button></div>
</form>
<hr style='border:none;border-top:1px solid #dbe7ff;margin:12px 0'/>
<h2>AI Questions</h2>
<div class='small' style='margin-bottom:8px'>Auto-generated screening questions based on the saved job description.</div>
<div class='row' style='margin-bottom:8px'><button id='genQuestionsBtn' type='button'>Regenerate AI Questions</button></div>
<div id='candidateQs'></div>
<label>Resume Upload (PDF/DOC/DOCX/TXT)</label>
<div class='row' style='margin-bottom:6px'>
  <button id='uploadResumeBtn' type='button'>Upload Resume</button>
  <span id='resumeFileName' class='small' style='align-self:center'>No file selected</span>
</div>
<input id='resumeFile' type='file' accept='.pdf,.doc,.docx,.txt' style='display:none'/>
<div id='resumeUploadStatus' class='small' style='margin-top:-4px;margin-bottom:6px'></div><div style='height:8px'></div><div style='background:#e6eefc;border-radius:999px;height:10px;overflow:hidden;margin-bottom:10px'><div id='resumeUploadBar' style='height:10px;width:0%;background:linear-gradient(90deg,#0b5fff,#22c55e);transition:width .2s'></div></div>
<label>Select your preferred Agent :</label>
<div id='agentProfileGroup' style='display:flex;gap:14px;align-items:center;flex-wrap:wrap;margin-bottom:6px'>
  <label style='display:flex;gap:6px;align-items:center;font-weight:600'><input type='radio' name='agentProfile' value='sara' checked> Sara</label>
  <label style='display:flex;gap:6px;align-items:center;font-weight:600'><input type='radio' name='agentProfile' value='adam'> Adam</label>
  <button type='button' id='agentVoiceSampleBtn' style='padding:6px 10px;border-radius:8px;border:1px solid #bfd3f8;background:#eef4ff;color:#0a3f9a;font-weight:700'>▶ Play</button>
</div>
<audio id='agentVoiceSampleAudio' controls style='width:100%;max-width:360px;display:none;margin:4px 0 8px 0'></audio>
<label>Candidate Phone</label><input id='phone' value='__PHONE_VALUE__'/>
<div style='margin:10px 0'>
  <div style='font-size:12px;color:#64748b;margin-bottom:6px'>Initialization Progress</div>
  <div style='background:#e6eefc;border-radius:999px;height:12px;overflow:hidden'>
    <div id='bar' style='height:12px;width:0%;background:linear-gradient(90deg,#0056b3,#0a66d6);transition:width .35s'></div>
  </div>
  <div id='stepText' class='small' style='margin-top:6px'>Waiting to initialize...</div>
</div>
<ul id='steps' class='small' style='line-height:1.7;padding-left:18px'>
  <li id='s1'>Resume parsing</li>
  <li id='s2'>JD parsing</li>
  <li id='s3'>Skill mapping</li>
  <li id='s4'>Interview plan generation</li>
  <li id='s5'>Agent session initialization</li>
</ul>
<div class='small' style='margin-top:6px;color:#5b6b83'><b>Note:</b> Agent session initialization.</div>
<hr style='border:none;border-top:1px solid #dbe7ff;margin:12px 0'/>
<h2>Candidate Details</h2>
<div id='resumeContactCard' class='small'>No resume parsed yet.</div>
<hr style='border:none;border-top:1px solid #dbe7ff;margin:12px 0'/>
<h2>Skill Mapping Evaluation</h2>
<div id='fitEval' style='min-height:140px'>Pending skill mapping...</div>
<div class='row' style='margin-top:10px'>
<button id='screeningBtn'>Start Validate</button>
</div>
<div id='toast' style='display:none;position:fixed;right:18px;bottom:18px;background:#0b5fff;color:#fff;padding:10px 12px;border-radius:8px;font-size:13px;box-shadow:0 8px 22px rgba(2,18,56,.25)'></div>
</div>
<div class='card table'>
<h2>Posted Jobs</h2>
<div class='row' style='margin-bottom:8px'><span id='dbState' class='small' style='align-self:center'></span></div>
<div id='jobs'></div>
<hr style='border:none;border-top:1px solid #dbe7ff;margin:12px 0'/>
<h2>Interview Sessions</h2>
<div id='sessions'></div>
<hr style='border:none;border-top:1px solid #dbe7ff;margin:12px 0'/>
<h2>Candidates by Job</h2>
<div id='candidateQueue' class='small'>Select/load a Job ID to view candidate call queue.</div>
<hr style='border:none;border-top:1px solid #dbe7ff;margin:12px 0'/>
<h2>Script Preview</h2>
<div class='small'>Live preview of the call wording from your editable script profile.</div>
<pre id='scriptPreview' style='min-height:110px'></pre>
<audio id='scriptPreviewAudio' controls style='width:100%;margin-top:8px;display:block'></audio>
</div>
</div></div>
<footer class='site-footer'><div class='footer-inner'><span>© Joblynk — Screening Platform</span><span>Secure • Auditable • Production Ready</span></div></footer>
<script src='https://cdn.quilljs.com/1.3.7/quill.min.js'></script>
<script data-cfasync='false'>
if(typeof Quill==='undefined' && typeof window!=='undefined' && window.Quill){ var Quill = window.Quill; }
let sid='';
let uploadedResumeId='';
let uploadedResumeText='';
let startArmed=false;
let candidateQuestions=[];
let autoSaveTimer=null;
let jdQuill=null;
let previewLoading=false;
let previewReadyText='';
const __selectedJD = __SELECTED_JD_JSON__;
const __selectedJobId = __SELECTED_JOB_ID_JSON__;
const __scriptCfg = __SCRIPT_CFG_JSON__;
const __promptCfg = __PROMPT_CFG_JSON__;
const __savedFlag = new URLSearchParams(window.location.search).get('saved') || '';
const __useJobFlag = new URLSearchParams(window.location.search).get('use_job') || '';
// Intentionally keep runtime logs out of recruiter UI to avoid exposing raw payloads in-page.
function log(t){ try { console.debug('[ui]', t); } catch(e){} }
function setBusy(id,busy,label){const b=document.getElementById(id); if(!b) return; b.classList.toggle('loading',busy); if(label!==undefined) b.textContent=label;}
function showToast(msg){const t=document.getElementById('toast'); if(!t) return; t.textContent=msg; t.style.display='block'; clearTimeout(window.__toastTimer); window.__toastTimer=setTimeout(()=>t.style.display='none',2200);}
function getSelectedAgentProfile(){
  const picked=document.querySelector('input[name="agentProfile"]:checked');
  return (picked?.value||'sara').toLowerCase();
}
function initFlashBanner(){
  const b=document.getElementById('flashBanner');
  if(!b) return;
  setTimeout(()=>{
    b.style.transition='opacity .35s ease';
    b.style.opacity='0';
    setTimeout(()=>b.remove(), 360);
  }, 3200);
}
function fmtEST(iso){
  if(!iso) return '';
  try{
    return new Intl.DateTimeFormat('en-US',{timeZone:'America/New_York',year:'numeric',month:'2-digit',day:'2-digit',hour:'numeric',minute:'2-digit',hour12:true,timeZoneName:'short'}).format(new Date(iso));
  }catch(e){ return iso; }
}
function getJDHtml(){
  const el=document.getElementById('jdEditor');
  if(jdQuill) return jdQuill.root.innerHTML || '';
  return el ? (el.innerHTML || '') : '';
}
function setJDEditor(raw){
  const el=document.getElementById('jdEditor');
  let v=(raw||'');
  const looksRich=/(<\/?(div|p|br|ul|ol|li|b|i|strong|em|h[1-6]|span)\b)/i.test(v);
  if(looksRich){
    v=v.replace(new RegExp('<script[\\s\\S]*?<\\\\/script>','gi'),'')
       .replace(new RegExp('<style[\\s\\S]*?<\\\\/style>','gi'),'')
       .replace(/<(meta|link|iframe|object|embed)[^>]*>/gi,'');
    const body=v.match(new RegExp('<body[^>]*>([\\s\\S]*?)<\\\\/body>','i'));
    v=(body?body[1]:v);
    // Collapse excessive blank editor rows while preserving bullets/lists.
    v=v.replace(/(<p><br><\/p>\s*){2,}/gi,'<p><br></p>')
       .replace(/(<div><br><\/div>\s*){2,}/gi,'<div><br></div>')
       .replace(/(<br\s*\/?>(\s|&nbsp;)*){3,}/gi,'<br><br>');
  } else {
    // Normalize plain text newlines to prevent huge visual gaps when loading older posts.
    const nl = String.fromCharCode(10);
    const cr = String.fromCharCode(13);
    v=(v||'').split(cr).join('');
    const lines=v.split(nl).map(x=>x.replace(/\s+$/,''));
    const compact=[];
    let blank=0;
    for(const ln of lines){
      if(!ln.trim()){
        blank += 1;
        if(blank<=1) compact.push('');
      }else{
        blank = 0;
        compact.push(ln);
      }
    }
    v=compact.join(nl).split(nl).join('<br>');
  }
  if(jdQuill){ jdQuill.root.innerHTML=v; return; }
  if(el){ el.innerHTML=v; }
}
function startNewJob(evt){
  if(evt) evt.preventDefault();
  sid='';
  document.getElementById('jobId').value='';
  updateSaveButtonLabel();
  document.getElementById('jobTitle').value='';
  setJDEditor('');
  document.getElementById('jd').value='';
  document.getElementById('phone').value='';
  const ap=document.querySelector("input[name='agentProfile'][value='sara']"); if(ap) ap.checked=true;
  const rf=document.getElementById('resumeFile'); if(rf) rf.value='';
  const rfName=document.getElementById('resumeFileName'); if(rfName) rfName.textContent='No file selected';
  uploadedResumeId=''; uploadedResumeText='';
  renderResumeContact(null);
  setResumeStatus('', true); setResumeProgress(0);
  renderFitEvaluation('Pending skill mapping...');
  document.getElementById('bar').style.width='0%';
  document.getElementById('stepText').textContent='Waiting to initialize...';
  ['s1','s2','s3','s4','s5'].forEach(id=>setStep(id,false));
  startArmed=false;
  const sb=document.getElementById('screeningBtn');
  if(sb){ sb.disabled=false; sb.textContent='Start Validate'; sb.classList.remove('loading'); sb.classList.remove('ready-call'); }
  markPhoneMissing(false);
  showToast('New job form is ready');
  setTimeout(()=>{ window.location.href='/ui?new=1'; }, 150);
}
function syncJD(){document.getElementById('jd').value=getJDHtml();}
function updateSaveButtonLabel(){
  const btn=document.getElementById('saveJob');
  const jid=(document.getElementById('jobId')?.value||'').trim();
  if(btn) btn.textContent = jid ? 'Update Now' : 'Save Now';
}
function markPhoneMissing(show){
  const phoneEl=document.getElementById('phone');
  if(!phoneEl) return;
  if(show){
    phoneEl.classList.add('input-missing');
    phoneEl.focus();
  } else {
    phoneEl.classList.remove('input-missing');
  }
}
function updateScreeningButtonState(){
  const sb=document.getElementById('screeningBtn');
  if(!sb) return;
  const phone=(document.getElementById('phone')?.value||'').trim();
  if(startArmed){
    if(phone){
      sb.textContent='Start Call';
      sb.classList.add('ready-call');
      markPhoneMissing(false);
    }else{
      sb.textContent='Start Validate';
      sb.classList.remove('ready-call');
      markPhoneMissing(true);
    }
  }else{
    sb.textContent='Start Validate';
    sb.classList.remove('ready-call');
  }
}
function setResumeStatus(msg, ok){
  const el=document.getElementById('resumeUploadStatus'); if(!el) return;
  el.textContent=msg||'';
  el.style.color=ok?'#0f766e':'#9f1239';
}
function setResumeProgress(pct){
  const bar=document.getElementById('resumeUploadBar'); if(!bar) return;
  bar.style.width=Math.max(0,Math.min(100,pct||0))+'%';
}
function renderResumeContact(info){
  const el=document.getElementById('resumeContactCard'); if(!el) return;
  if(!info){ el.innerHTML='No resume parsed yet.'; return; }
  el.innerHTML = `
    <div class='kv'>
      <div class='k'>Full Name</div><div class='v'>${info.full_name||'-'}</div>
      <div class='k'>Email</div><div class='v'>${info.email||'-'}</div>
      <div class='k'>Phone</div><div class='v'>${info.phone||'-'}</div>
      <div class='k'>LinkedIn</div><div class='v'>${info.linkedin||'-'}</div>
    </div>
  `;
}

function renderFitEvaluation(txt){
  const el=document.getElementById('fitEval'); if(!el) return;
  const nl = String.fromCharCode(10);
  const cr = String.fromCharCode(13);
  const raw=(txt||'Pending skill mapping...').split(cr).join('');
  const esc=(s)=>String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
  const lines=raw.split(nl).map(x=>x.trim()).filter(Boolean);
  let html='';
  let pendingLabel='';
  for(const line of lines){
    if(/^(Overall Fit|Experience Relevance|Must-Haves Check)$/i.test(line)){
      html += `<div class='fit-h'>${esc(line)}</div>`;
      pendingLabel='';
      continue;
    }
    const kv=line.match(/^(Fit Verdict:|Summary:|Estimated Relevance:|Justification:|Must-Haves Present\?|Evidence:)\s*(.*)$/i);
    if(kv){
      const label=kv[1];
      const value=(kv[2]||'').trim();
      const isBlock=/^(Summary:|Justification:|Evidence:)$/i.test(label);
      if(value){
        if(isBlock){
          html += `<div class='fit-block'><span class='fit-label'>${esc(label)}</span><span class='fit-value'>${esc(value)}</span></div>`;
        } else {
          html += `<div class='fit-row'><div class='fit-label'>${esc(label)}</div><div class='fit-value'>${esc(value)}</div></div>`;
        }
        pendingLabel='';
      }else{
        pendingLabel=label;
      }
      continue;
    }
    if(pendingLabel){
      const isBlock=/^(Summary:|Justification:|Evidence:)$/i.test(pendingLabel);
      if(isBlock){
        html += `<div class='fit-block'><span class='fit-label'>${esc(pendingLabel)}</span><span class='fit-value'>${esc(line)}</span></div>`;
      } else {
        html += `<div class='fit-row'><div class='fit-label'>${esc(pendingLabel)}</div><div class='fit-value'>${esc(line)}</div></div>`;
      }
      pendingLabel='';
      continue;
    }
    if(line.startsWith('-')){
      html += `<div class='fit-b'>• ${esc(line.replace(/^[-•]\s*/,''))}</div>`;
    } else {
      html += `<div class='fit-value'>${esc(line)}</div>`;
    }
  }
  el.innerHTML = html || 'Pending skill mapping...';
}

function renderScriptPreview(){
  const pre=document.getElementById('scriptPreview'); if(!pre) return;
  const profile=getSelectedAgentProfile();
  const cfg=(__promptCfg && __promptCfg[profile]) ? __promptCfg[profile] : (__promptCfg?.sara||{});
  const aiQ=(candidateQuestions[0]||'[AI technical question based on JD + resume]');
  const next=(__scriptCfg.next_question_template||'Next question: {next_question}').replace('{next_question}','[dynamic AI follow-up question]');
  pre.textContent = `Prompt Opening:\n${cfg.intro||''}\n\nIf Candidate Confirms:\n${cfg.after_consent||''}\n\nAI Question Flow:\n${aiQ}\n${next}\n\nPrompt Closing:\n${cfg.closing_1||''}\n${cfg.closing_2||''}`;
  clearTimeout(window.__previewWarmTimer);
  window.__previewWarmTimer=setTimeout(()=>{ ensurePreviewAudioReady(true).catch(()=>{}); }, 250);
}

async function copyScriptPreview(){
  const txt=document.getElementById('scriptPreview')?.textContent||'';
  try{ await navigator.clipboard.writeText(txt); showToast('Script copied'); }
  catch(e){ showToast('Copy failed'); }
}

function spokenScriptText(){
  const txt=(document.getElementById('scriptPreview')?.textContent||'').trim();
  const nl=String.fromCharCode(10);
  return txt
    .replace(/\b(Intro|After Consent|Transition|Wrap-up):/gi,'')
    .replace(/\[dynamic next question\]/gi,'')
    .split(nl+nl).join(nl)
    .replace(/\s+/g,' ')
    .trim();
}

function stopAgentPreview(){
  const a=document.getElementById('scriptPreviewAudio');
  if(a){ try{ a.pause(); a.currentTime=0; }catch(e){} }
  if('speechSynthesis' in window){ try{ window.speechSynthesis.cancel(); }catch(e){} }
}

async function ensurePreviewAudioReady(auto=false){
  const txt=spokenScriptText();
  const a=document.getElementById('scriptPreviewAudio');
  if(!a || !txt.trim()) return false;
  if(previewLoading) return false;
  if(a.src && previewReadyText===txt) return true;

  previewLoading=true;
  const fd=new FormData(); fd.append('text', txt.slice(0,1200));
  try{
    const r=await fetch('/script/preview-tts',{method:'POST',body:fd});
    const j=await r.json().catch(()=>({}));
    if(r.ok && j.audio_url){
      a.src=j.audio_url+'?ts='+Date.now();
      previewReadyText=txt;
      previewLoading=false;
      return true;
    }
  }catch(e){}
  previewLoading=false;
  if(!auto) showToast('TTS preview failed. Please try again.');
  return false;
}

function playBrowserVoiceFallback(profile){
  if(!('speechSynthesis' in window)) return false;
  try{
    const isSara = profile==='sara';
    const u=new SpeechSynthesisUtterance(isSara?'Hi, this is Sara.':'Hi, this is Adam.');
    u.lang='en-US';
    const voices=(window.speechSynthesis.getVoices()||[]).filter(v=>/en/i.test(v.lang||''));

    let preferred;
    if(isSara){
      preferred = voices.find(v=>/female|woman|sara|joanna|aria|zira|samantha|victoria|karen/i.test(v.name||''))
        || voices.find(v=>!/male|man|david|matthew|guy/i.test(v.name||''));
      u.pitch = 1.25;
      u.rate = 1.0;
    } else {
      preferred = voices.find(v=>/male|man|adam|matthew|david|guy|daniel/i.test(v.name||''));
      u.pitch = 0.9;
      u.rate = 0.98;
    }
    if(preferred) u.voice=preferred;
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
    return true;
  }catch(e){ return false; }
}

async function playAgentVoiceSample(){
  const p=getSelectedAgentProfile();
  const a=document.getElementById('agentVoiceSampleAudio');
  const b=document.getElementById('agentVoiceSampleBtn');
  if(!a || !b) return;
  b.disabled=true; b.textContent='Loading...';
  try{
    const fd=new FormData(); fd.append('agent_profile', p);
    const r=await fetch('/agent/voice-sample',{method:'POST', body:fd});
    const j=await r.json().catch(()=>({}));
    if(r.ok && j.audio_url){
      a.style.display='block';
      a.src=j.audio_url+'?ts='+Date.now();
      await a.play().catch(()=>{});
    }else{
      const ok=playBrowserVoiceFallback(p);
      showToast(ok ? 'Using local browser voice preview' : (j.detail || 'Voice sample unavailable'));
    }
  }catch(e){
    const ok=playBrowserVoiceFallback(p);
    showToast(ok ? 'Using local browser voice preview' : 'Voice sample failed');
  }
  finally{ b.disabled=false; b.textContent='▶ Play'; }
}

async function ttsScriptPreview(){
  const ready = await ensurePreviewAudioReady(false);
  if(!ready) return;
  const a=document.getElementById('scriptPreviewAudio');
  a.play().catch(()=>{});
  showToast('Playing agent communication preview');
}

function renderCandidateQuestions(){
  const box=document.getElementById('candidateQs'); if(!box) return;
  if(!candidateQuestions.length){ box.innerHTML="<div class='small'>No questions generated yet.</div>"; return; }
  box.innerHTML = candidateQuestions.map((q,i)=>`<div class='small' style='margin:10px 0'><b>Q${i+1}.</b> ${q}</div>`).join('');
}

function getCandidateAnswers(){
  return [];
}

function scheduleAutoSaveCandidateSummary(){ }

function normalizeGeneratedTitle(t){
  const s=(t||'').trim();
  if(!s) return '';
  return s.replace(/\s+/g,' ').split(' ').map(w=>w ? (w.charAt(0).toUpperCase()+w.slice(1).toLowerCase()) : w).join(' ');
}

function formatGeneratedDescriptionToHtml(text){
  const nl = String.fromCharCode(10);
  const cr = String.fromCharCode(13);
  const src=(text||'').split(cr).join('').trim();
  if(!src) return '';
  const lines=src.split(nl);
  const headingSet=new Set(['About Us','Job Summary','Key Responsibilities','Required Skills and Qualifications','Preferred Qualifications']);
  let html=[];
  let inList=false;
  for(let raw of lines){
    const line=raw.trim();
    if(!line){ if(inList){ html.push('</ul>'); inList=false; } continue; }
    const clean=line.replace(/:$/,'');
    if(headingSet.has(clean)){
      if(inList){ html.push('</ul>'); inList=false; }
      html.push(`<h3>${clean}</h3>`);
      continue;
    }
    if(/^[-•]\s+/.test(line)){
      if(!inList){ html.push('<ul>'); inList=true; }
      html.push(`<li>${line.replace(/^[-•]\s+/,'')}</li>`);
      continue;
    }
    if(inList){ html.push('</ul>'); inList=false; }
    html.push(`<p>${line}</p>`);
  }
  if(inList) html.push('</ul>');
  return html.join('');
}

async function generateJobPost(){
  const prompt=(document.getElementById('genPrompt')?.value||'').trim();
  if(!prompt){ showToast('Please enter prompt to generate job post'); return; }
  const payload={ prompt };
  setBusy('genJobPostBtn',true,'Generating...');
  try{
    const r=await fetch('/jobs/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    const j=await r.json();
    if(!r.ok||!j.job_description){ showToast('Job generation failed'); return; }
    const normalizedTitle = normalizeGeneratedTitle(j.job_title||'') || 'Generated Role';
    const formattedHtml = formatGeneratedDescriptionToHtml(j.job_description||'');
    document.getElementById('jobTitle').value=normalizedTitle;
    setJDEditor(formattedHtml || (j.job_description||''));
    syncJD();
    updateSaveButtonLabel();
    showToast('Job post generated and filled');
    generateCandidateQuestions(true).catch(()=>{});
  } finally {
    setBusy('genJobPostBtn',false,'Generate Job Post');
  }
}

async function generateCandidateQuestions(auto=false){
  const jd=(document.getElementById('jd').value||getJDHtml()||'').trim();
  if(!jd){ showToast('Please save or enter a job description first'); return; }
  const r=await fetch('/candidate/questions',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_description:jd,resume_upload_id:uploadedResumeId||null,resume_text:uploadedResumeText||'',previous_questions:candidateQuestions||[],agent_profile:getSelectedAgentProfile()})});
  const j=await r.json();
  if(!r.ok){ log('Question generation failed: '+JSON.stringify(j)); return; }
  candidateQuestions = (j.questions||[]).slice(0,4);
  renderCandidateQuestions();
  if(!auto) showToast('Generated AI questions');
  renderScriptPreview();
}

async function saveCandidateSummary(silent=false){ return; }

function autoUploadResume(file){
  return new Promise((resolve,reject)=>{
    const fd=new FormData(); fd.append('resume_file', file);
    const xhr=new XMLHttpRequest();
    xhr.open('POST','/resume/upload',true);
    setResumeProgress(10);
    setResumeStatus('Uploading '+file.name+' ...', true);
    xhr.upload.onprogress=(e)=>{
      if(e.lengthComputable){
        const pct=Math.round((e.loaded/e.total)*100);
        setResumeProgress(pct);
        setResumeStatus('Uploading '+file.name+' ... '+pct+'%', true);
      }
    };
    xhr.onload=()=>{
      try{
        const j=JSON.parse(xhr.responseText||'{}');
        if(xhr.status>=200 && xhr.status<300 && j.resume_upload && j.resume_upload.upload_id){
          uploadedResumeId=j.resume_upload.upload_id;
          uploadedResumeText=j.resume_text || '';
          setResumeProgress(95);
          setResumeStatus('Finalizing DB entry ...', true);
          setResumeProgress(100);
          setResumeStatus('✅ Uploaded to server and logged in DB (Upload ID: '+uploadedResumeId+')', true);
          showToast('Resume uploaded successfully (server + database)');
          log('Resume upload saved | upload_id='+uploadedResumeId+' | size='+(j.resume_upload.size_bytes||0)+' | path='+(j.resume_upload.stored_path||''));
          renderResumeContact(j.contact_info||null);
          renderScriptPreview();
          const jdNow=(document.getElementById('jd').value||getJDHtml()||'').trim();
          if(jdNow){
            setResumeStatus('✅ Resume processed. Generating role-specific questions...', true);
            generateCandidateQuestions(true).catch(()=>{});
          } else {
            setResumeStatus('✅ Resume uploaded and processed. Add Job Description to generate questions.', true);
          }
          resolve(j);
        }else{
          setResumeProgress(0);
          setResumeStatus('Resume upload failed. Please try again.', false);
          reject(new Error('Upload failed'));
        }
      }catch(err){
        setResumeProgress(0);
        setResumeStatus('Resume upload failed. Please try again.', false);
        reject(err);
      }
    };
    xhr.onerror=()=>{ setResumeProgress(0); setResumeStatus('Resume upload failed. Please try again.', false); reject(new Error('Network error')); };
    xhr.send(fd);
  });
}

async function refreshPostedJobs(){
 const r=await fetch('/jobs?ts='+Date.now(), {cache:'no-store'}); const j=await r.json();
 const el=document.getElementById('jobs'); el.innerHTML='';
 (j.jobs||[]).forEach(x=>{const d=document.createElement('div');d.className='job';
 const oneLine=(x.job_description||'').replace(/<[^>]*>/g,' ').replace(/\s+/g,' ').trim().slice(0,140);
 d.innerHTML=`<div class='small job-title-ellipsis' style='font-weight:700;color:#0a3f9a'><a href='#' class='useJobLink' data-job='${x.job_id}' style='text-decoration:none;color:#0a3f9a'>${x.job_id||''} — ${x.title||'Untitled Role'}</a></div><div class='small'>${oneLine||'No description'}</div><div class='small'>${fmtEST(x.created_at||'')}</div><div class='row'><button class='useJobBtn' data-job='${x.job_id}'>Load Job</button><button class='delJobBtn' data-job='${x.job_id}' title='Delete Job'>Delete</button></div>`;
 el.appendChild(d);
 });
 if((j.jobs||[]).length===0){ el.innerHTML="<div class='small'>No jobs found yet.</div>"; }
 el.querySelectorAll('.useJobBtn').forEach(btn=>btn.addEventListener('click',()=>{ window.location.href='/ui?use_job='+encodeURIComponent(btn.dataset.job||''); }));
 el.querySelectorAll('.useJobLink').forEach(a=>a.addEventListener('click',(e)=>{e.preventDefault(); window.location.href='/ui?use_job='+encodeURIComponent(a.dataset.job||''); }));
 el.querySelectorAll('.delJobBtn').forEach(btn=>btn.addEventListener('click',()=>deleteJob(btn.dataset.job)));
 try{ const d=await fetch('/db/health?ts='+Date.now(), {cache:'no-store'}); const dj=await d.json(); document.getElementById('dbState').textContent=`DB: ${dj.db} | Jobs: ${dj.count||0}`; }catch(e){ document.getElementById('dbState').textContent='DB: unknown'; }
}


async function startCallForSession(sessionId, phone){
  if(!sessionId){ showToast('Missing session id'); return; }
  const p=(phone||'').trim();
  if(!p){ showToast('Candidate phone missing for this session'); return; }
  try{
    await fetch('/interview/start/'+sessionId,{method:'POST'});
    const fd=new FormData(); fd.append('to',p); fd.append('agent_profile', getSelectedAgentProfile());
    const r=await fetch('/interview/call/'+sessionId,{method:'POST',headers:{'x-api-key':'joblynk-voice-start-key'},body:fd});
    const j=await r.json();
    if(!r.ok){ showToast(j.detail||'Unable to start call'); return; }
    showToast('Call started for selected candidate');
    await refreshSessions();
    await refreshCandidateQueue();
  }catch(e){ showToast('Start call failed'); }
}

async function refreshCandidateQueue(){
  const jobId=(document.getElementById('jobId')?.value||'').trim();
  const el=document.getElementById('candidateQueue');
  if(!el) return;
  if(!jobId){ el.innerHTML="<div class='small'>Load/select a job to view candidates.</div>"; return; }
  const r=await fetch('/interview/candidates?job_id='+encodeURIComponent(jobId), {cache:'no-store'});
  const j=await r.json();
  const arr=(j.candidates||[]);
  if(!arr.length){ el.innerHTML="<div class='small'>No called candidates found for this Job ID yet.</div>"; return; }

  el.innerHTML='';
  arr.forEach(c=>{
    const card=document.createElement('div');
    card.className='session-card';
    const status=(c.call_status||'').trim();
    const attended = status==='Attended Call';
    const canStart = !attended && (status==='Need to Call Back' || status==='No Response' || status==='Call Back Required') && (c.candidate_phone||'').trim();
    const nm = c.profile_url ? `<a href='${c.profile_url}' style='color:#0a3f9a;text-decoration:none;font-weight:700'>${c.candidate_name||'Unknown Candidate'}</a>` : `<b>${c.candidate_name||'Unknown Candidate'}</b>`;
    const btnStyle = attended ? "background:#16a34a;cursor:not-allowed;opacity:1" : "";
    const btnLabel = attended ? 'Attended' : 'Start Call';
    card.innerHTML = `
      <div class='session-head'>${nm}<span class='session-id'>${c.candidate_id||''}</span></div>
      <div class='small'><span class='label'>Phone</span> ${c.candidate_phone||'N/A'}</div>
      <div class='small'><span class='label'>Email</span> ${c.candidate_email||'N/A'}</div>
      <div class='small'><span class='label'>Call Status</span> ${status||'No Response'}</div>
      <div class='row' style='margin-top:8px'>
        <button class='queueStartBtn' style='${btnStyle}' data-sid='${c.session_id}' data-phone='${c.candidate_phone||''}' ${canStart?'':'disabled'}>${btnLabel}</button>
      </div>`;
    el.appendChild(card);
  });
  el.querySelectorAll('.queueStartBtn').forEach(btn=>btn.addEventListener('click',()=>startCallForSession(btn.dataset.sid, btn.dataset.phone||'')));
}


async function refreshSessions(){
 const r=await fetch('/interview/jobs',{cache:'no-store'}); const j=await r.json();
 const el=document.getElementById('sessions'); el.innerHTML='';
 const currentJob=(document.getElementById('jobId')?.value||'').trim();
 const rows=(j.jobs||[]).filter(x=>!currentJob || (x.job_id||'')===currentJob);
 rows.forEach(x=>{const d=document.createElement('div');d.className='session-card';
 const qa=(x.completed_questions||[]).map((q,i)=>`<div class='small' style='margin-top:6px'><span class='label'>Question ${i+1}</span><div>${(q.question||'')}</div></div><div class='small'><span class='label'>Answer ${i+1}</span><div>${(q.answer||'')}</div></div>`).join('');
 const calls = (x.calls||[]);
 const latestCall = calls.length ? calls[calls.length-1] : null;
 const latestCallStatus = (latestCall?.status || '').toLowerCase();
 const callState = latestCall ? (`☎ ${latestCall.status||'in-progress'}`) : (x.call_in_progress ? "🟢 Call in progress" : "☎ idle");
 const rec=(x.recommendation||'').toLowerCase();
 let fitLabel='Pending'; let fitClass='fit-moderate';
 if(rec.includes('good fit')||rec.includes('strong fit')||rec.includes('proceed')){ fitLabel='Strong Fit'; fitClass='fit-strong'; }
 else if(rec.includes('potential')||rec.includes('moderate')||rec.includes('deeper')){ fitLabel='Moderate Fit'; fitClass='fit-moderate'; }
 else if(rec.includes('insufficient')||rec.includes('not fit')||rec.includes('reject')){ fitLabel='Not Yet Fit'; fitClass='fit-low'; }
 const callStarted = !!latestCall;
 const isSuccessful = latestCallStatus === 'completed';
 if(isSuccessful && fitLabel==='Pending'){ fitLabel='Completed'; fitClass='fit-strong'; }
d.innerHTML=`<div class='session-head'><b>${x.job_title||'Untitled Role'}</b><span class='session-id'>Session: ${x.session_id}</span></div><div class='small'><span class='label'>Session Status</span> ${x.status} | Ready: ${x.ready}</div><div class='small'><span class='label'>Call Status</span> ${callState} | Calls: ${calls.length}${latestCall?.call_sid?` | Call SID: ${latestCall.call_sid}`:''}</div><div class='row' style='margin:8px 0'><button class='checkStatusBtn ${isSuccessful ? 'status-success' : ''}' data-sid='${x.session_id}' data-call-sid='${latestCall?.call_sid||''}' ${callStarted ? '' : 'disabled'}>${isSuccessful ? 'Interview Successful' : 'Check Call Status'}</button></div><div class='fit-badge ${fitClass}'>Candidate Evaluation: ${fitLabel}</div><div style='margin-top:6px'>${qa||"<div class='small'>No answers captured yet.</div>"}</div><div class='small' style='margin-top:8px;color:#0a3f9a'><span class='label'>AI Recommendation</span> ${x.recommendation||'Pending call completion...'}</div><hr class='session-divider'/></div>`;
 el.appendChild(d);
 });
 el.querySelectorAll('.checkStatusBtn').forEach(btn=>btn.addEventListener('click', ()=>checkInterviewStatus(btn.dataset.sid, btn.dataset.callSid||'', btn)));
}

let __autoStatusBusy=false;
async function autoSyncCallStatuses(){
 if(__autoStatusBusy) return;
 __autoStatusBusy=true;
 try{
  const r=await fetch('/interview/jobs',{cache:'no-store'});
  const j=await r.json();
  const currentJob=(document.getElementById('jobId')?.value||'').trim();
  const jobs=(j.jobs||[]).filter(x=>!currentJob || (x.job_id||'')===currentJob);
  for(const x of jobs){
    const calls=(x.calls||[]);
    const latest=calls.length?calls[calls.length-1]:null;
    const st=((latest?.status)||x.last_call_status||'').toLowerCase();
    if(!latest?.call_sid) continue;
    if(['completed','failed','busy','no-answer','no answer','canceled','cancelled'].includes(st)) continue;
    await fetch('/interview/call-status/'+x.session_id+'/'+latest.call_sid,{cache:'no-store',headers:{'x-api-key':'joblynk-voice-start-key'}}).catch(()=>{});
  }
 }finally{ __autoStatusBusy=false; }
}

async function loadJob(jobId){
 const r=await fetch('/jobs/'+jobId); const j=await r.json();
 document.getElementById('jobId').value=j.job_id||'';
 updateSaveButtonLabel();
 document.getElementById('jobTitle').value=j.title||'';
 setJDEditor(j.job_description||'');
 syncJD();
 log('Loaded job: '+(j.title||jobId));
 generateCandidateQuestions(true).catch(()=>{});
}

async function deleteJob(jobId){
 if(!confirm('Delete this job?')) return;
 const r=await fetch('/jobs/'+jobId,{method:'DELETE'});
 const j=await r.json();
 if(!r.ok){ log('Delete failed: '+JSON.stringify(j)); return; }
 showToast('Job deleted successfully');
 refreshPostedJobs();
}

function saveJobSubmit(evt){
  const title = (document.getElementById('jobTitle').value || '').trim();
  const jdHtml = (getJDHtml() || '').trim();
  if(!title || !jdHtml || jdHtml === '<br>' || jdHtml === '<div><br></div>'){
    evt.preventDefault();
    showToast('Please enter both Job Title and Job Description');
    return false;
  }
  syncJD();
  setBusy('saveJob',true,'Saving...');
}

function setStep(id, done){
  const el=document.getElementById(id); if(!el) return;
  const base=(el.dataset.baseText||el.textContent||'').replace(/^✅\s*/,'').trim();
  el.dataset.baseText=base;
  el.textContent = done ? `✅ ${base}` : base;
  el.style.color=done?'#15803d':'#64748b';
  el.style.fontWeight=done?'700':'500';
}
async function pollStatus(){
  if(!sid) return;
  const r=await fetch('/interview/status/'+sid); const j=await r.json();
  document.getElementById('bar').style.width=(j.progress||0)+'%';
  document.getElementById('stepText').textContent='Status: '+j.status+' ('+(j.progress||0)+'%)';
  setStep('s1',j.steps?.parsing_resume); setStep('s2',j.steps?.parsing_jd); setStep('s3',j.steps?.skill_mapping);
  setStep('s4',j.steps?.interview_plan_generation); setStep('s5',j.steps?.agent_session_initialization);
  renderFitEvaluation(j.fit_evaluation||'Pending skill mapping...');
  if(j.ready){
    const sb=document.getElementById('screeningBtn');
    if(sb){ sb.disabled=false; }
    setBusy('screeningBtn',false,'Start Validate');
    if(!startArmed){
      const sr=await fetch('/interview/start/'+sid,{method:'POST'});
      const sj=await sr.json();
      if(sr.ok){
        startArmed=true;
        updateScreeningButtonState();
        showToast('Interview prepared. Add phone if needed, then click Start Call.');
      } else {
        log('Auto start-trigger failed: '+JSON.stringify(sj));
      }
    }
    return;
  }
  if(j.status==='failed'){ log('Initialization failed: '+(j.error||'unknown')); const sb=document.getElementById('screeningBtn'); if(sb) sb.disabled=false; setBusy('screeningBtn',false,'Start Validate'); updateScreeningButtonState(); return; }
  setTimeout(pollStatus,800);
}

async function initSession(){
 try{
  setBusy('screeningBtn',true,'Initializing...');
  log('Initializing pipeline...');
  startArmed=false;
  document.getElementById('screeningBtn').disabled=true;
  document.getElementById('stepText').textContent='Initialization started...';
  renderFitEvaluation('Running skill mapping evaluation...');
  // keep single action button disabled while initialization runs
  const jdEl={ value: getJDHtml() };
  const fileEl=document.getElementById('resumeFile');
  const f=fileEl.files[0];
  let r;
  const titleEl=document.getElementById('jobTitle');

  if(f && !uploadedResumeId){
    await autoUploadResume(f);
  }
  if(!uploadedResumeId){
    setResumeStatus('Please upload a resume before initializing.', false);
    setBusy('screeningBtn',false,'Start Validate');
    document.getElementById('screeningBtn').disabled=false;
    return;
  }

  const resumePayload = (uploadedResumeText || '');
  r=await fetch('/interview/init',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({job_id:(document.getElementById('jobId')?.value||''),job_description:jdEl.value,resume:resumePayload,job_title:titleEl.value,resume_upload_id:uploadedResumeId||null})});

  const j=await r.json();
  if(!r.ok){ log('Init error: '+JSON.stringify(j)); document.getElementById('screeningBtn').disabled=false; setBusy('screeningBtn',false,'Start Validate'); return; }
  sid=j.session_id; log(JSON.stringify(j,null,2));
  if(uploadedResumeId){
    setResumeStatus('✅ Uploaded to server and logged in DB (Upload ID: '+uploadedResumeId+')', true);
  }
  refreshSessions(); pollStatus();
 }catch(e){ log('Init exception: '+e.message); document.getElementById('screeningBtn').disabled=false; setBusy('screeningBtn',false,'Start Validate'); }
}

async function triggerStart(){
 setBusy('start',true,'Triggering...');
 try{
  const r=await fetch('/interview/start/'+sid,{method:'POST'}); const j=await r.json();
  log(JSON.stringify(j,null,2)); if(r.ok) document.getElementById('screeningBtn').disabled=false; refreshSessions();
 } finally { setBusy('start',false,'Start Interview Trigger'); }
}

async function startScreening(){
  const phone=(document.getElementById('phone')?.value||'').trim();
  if(!phone){
    markPhoneMissing(true);
    showToast('Candidate phone number is missing');
  }
  if(!sid || !startArmed){
    await initSession();
    return;
  }
  await startCall();
}

async function startCall(){
 const phoneEl=document.getElementById('phone');
 const phone=(phoneEl?.value||'').trim();
 if(!phone){
  markPhoneMissing(true);
  showToast('Candidate phone number is required before starting call');
  updateScreeningButtonState();
  return;
 }
 markPhoneMissing(false);
 setBusy('screeningBtn',true,'Calling...');
 try{
  const fd=new FormData(); fd.append('to',phone);
  fd.append('agent_profile', getSelectedAgentProfile());
  const r=await fetch('/interview/call/'+sid,{method:'POST',headers:{'x-api-key':'joblynk-voice-start-key'},body:fd});
  const j=await r.json(); log(JSON.stringify(j,null,2));
  refreshSessions();
 } finally { setBusy('screeningBtn',false,'Start Validate'); updateScreeningButtonState(); }
}

async function checkInterviewStatus(targetSid, targetCallSid, btnEl){
 const sidToCheck = targetSid || sid;
 if(!sidToCheck){ showToast('No active interview session'); return; }
 if(!targetCallSid){ showToast('Start call first, then check call status'); return; }
 if(btnEl){ btnEl.disabled=true; btnEl.textContent='Checking...'; }
 try{
  const r=await fetch('/interview/call-status/'+sidToCheck+'/'+targetCallSid, {cache:'no-store', headers:{'x-api-key':'joblynk-voice-start-key'}});
  const j=await r.json();
  if(!r.ok){
    showToast(j.detail || 'Unable to fetch call status');
    return;
  }
  const st = (j.status || '').toLowerCase();
  const successful = st === 'completed';
  if(btnEl){
    if(successful){
      btnEl.textContent='Interview Successful';
      btnEl.classList.add('status-success');
    } else {
      btnEl.textContent='Check Call Status';
      btnEl.classList.remove('status-success');
    }
  }
  showToast(successful ? 'Call completed successfully' : `Call status: ${st || 'in progress'}`);
  await refreshSessions();
 } finally {
  if(btnEl){ btnEl.disabled=false; }
 }
}

const editor=document.getElementById('jdEditor');
if(window.Quill){
  jdQuill = new window.Quill('#jdEditor', {
    theme: 'snow',
    placeholder: 'Paste or write the job description...',
    modules: {
      toolbar: [
        ['bold', 'italic', 'underline'],
        [{ 'list': 'ordered'}, { 'list': 'bullet' }],
        [{ 'header': [1, 2, 3, false] }],
        ['clean']
      ]
    }
  });
  setJDEditor(__selectedJD || '');
  jdQuill.on('text-change', ()=>{ syncJD(); renderScriptPreview(); });
}else{
  if(editor){
    editor.setAttribute('contenteditable','true');
    editor.style.height='260px';
    editor.style.overflow='auto';
    editor.style.padding='10px';
    editor.style.border='1px solid #bfd3f8';
    editor.style.borderRadius='10px';
    setJDEditor(__selectedJD || '');
    editor.addEventListener('input', ()=>{ syncJD(); renderScriptPreview(); });
  }
  console.warn('Quill failed to load; using fallback editor');
}
const titleInput=document.getElementById('jobTitle'); if(titleInput) titleInput.addEventListener('input', renderScriptPreview);
const phoneInput=document.getElementById('phone'); if(phoneInput) phoneInput.addEventListener('input', ()=>{ markPhoneMissing(false); updateScreeningButtonState(); });
document.querySelectorAll("input[name='agentProfile']").forEach(el=>el.addEventListener('change', renderScriptPreview));
const jobIdEl=document.getElementById('jobId'); if(jobIdEl) jobIdEl.value = __selectedJobId || '';
updateSaveButtonLabel();
syncJD();
renderScriptPreview();
updateScreeningButtonState();
if((__selectedJobId||'').trim() || (__useJobFlag||'').trim()){ setTimeout(()=>generateCandidateQuestions(true), 250); }

const saveForm=document.getElementById('saveJobForm');
if(saveForm){
  saveForm.addEventListener('submit', saveJobSubmit);
  saveForm.addEventListener('submit', ()=>setTimeout(syncJD,0));
}
const newJobBtn=document.getElementById('newJobBtn'); if(newJobBtn) newJobBtn.addEventListener('click', startNewJob);
const screeningBtn=document.getElementById('screeningBtn'); if(screeningBtn) screeningBtn.addEventListener('click', startScreening);
const agentVoiceSampleBtn=document.getElementById('agentVoiceSampleBtn'); if(agentVoiceSampleBtn) agentVoiceSampleBtn.addEventListener('click', playAgentVoiceSample);
const burgerUi=document.getElementById('burgerUi'); const uiNav=document.getElementById('uiNav');
if(burgerUi && uiNav){
  burgerUi.addEventListener('click',(e)=>{ e.stopPropagation(); uiNav.classList.toggle('open'); });
  uiNav.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>uiNav.classList.remove('open')));
  document.addEventListener('click',(e)=>{
    if(!uiNav.classList.contains('open')) return;
    const t=e.target;
    if(t instanceof Node && !uiNav.contains(t) && t!==burgerUi) uiNav.classList.remove('open');
  });
  document.addEventListener('touchstart',(e)=>{
    if(!uiNav.classList.contains('open')) return;
    const t=e.target;
    if(t instanceof Node && !uiNav.contains(t) && t!==burgerUi) uiNav.classList.remove('open');
  });
  document.addEventListener('keydown',(e)=>{ if(e.key==='Escape') uiNav.classList.remove('open'); });
}
const refreshBtn=document.getElementById('refreshJobsBtn'); if(refreshBtn) refreshBtn.addEventListener('click', refreshPostedJobs);
const genQuestionsBtn=document.getElementById('genQuestionsBtn'); if(genQuestionsBtn) genQuestionsBtn.addEventListener('click', generateCandidateQuestions);
const genJobPostBtn=document.getElementById('genJobPostBtn'); if(genJobPostBtn) genJobPostBtn.addEventListener('click', generateJobPost);
// candidate summary button removed intentionally
const previewAudio=document.getElementById('scriptPreviewAudio');
if(previewAudio){
  previewAudio.addEventListener('play', async ()=>{
    if((!previewAudio.src || !previewAudio.src.trim()) && !previewLoading){
      previewAudio.pause();
      await ttsScriptPreview();
      return;
    }
    if('speechSynthesis' in window){ try{ window.speechSynthesis.cancel(); }catch(e){} }
  });
  previewAudio.addEventListener('click', async ()=>{
    if((!previewAudio.src || !previewAudio.src.trim()) && !previewLoading){
      await ttsScriptPreview();
    }
  });
  ['pause','ended','seeking'].forEach(evt=>previewAudio.addEventListener(evt, ()=>{ if('speechSynthesis' in window){ try{ window.speechSynthesis.cancel(); }catch(e){} } }));
}
const uploadResumeBtn=document.getElementById('uploadResumeBtn');
const resumeFileEl=document.getElementById('resumeFile');
if(uploadResumeBtn && resumeFileEl){
  uploadResumeBtn.addEventListener('click', ()=>resumeFileEl.click());
}
if(resumeFileEl) resumeFileEl.addEventListener('change', async ()=>{
  const f=resumeFileEl.files && resumeFileEl.files[0];
  const rfName=document.getElementById('resumeFileName');
  if(rfName) rfName.textContent = f ? f.name : 'No file selected';
  uploadedResumeId=''; uploadedResumeText=''; setResumeProgress(0);
  if(!f){ setResumeStatus('', true); return; }
  setResumeStatus('Selected: '+f.name+' (auto-upload starting...)', true);
  try{ await autoUploadResume(f); }catch(e){ log('Resume auto-upload failed: '+e.message); }
});
renderCandidateQuestions();
renderResumeContact(null);
renderFitEvaluation('Pending skill mapping...');
initFlashBanner();
if(__savedFlag==='1' || __savedFlag==='updated'){ setTimeout(()=>generateCandidateQuestions(true), 250); }
refreshPostedJobs(); refreshSessions(); refreshCandidateQueue();
setInterval(refreshPostedJobs, 4000);
setInterval(refreshCandidateQueue, 5000);
setInterval(async ()=>{ await autoSyncCallStatuses(); await refreshSessions(); }, 3500);
</script></body></html>
"""
    html_doc = html_doc.replace("__SELECTED_JOB_ID__", html.escape(selected_job_id, quote=True))
    html_doc = html_doc.replace("__SELECTED_TITLE__", html.escape(selected_title, quote=True))
    html_doc = html_doc.replace("__SELECTED_JD_HTML__", selected_jd_html)
    html_doc = html_doc.replace("__PHONE_VALUE__", html.escape(phone_value, quote=True))
    html_doc = html_doc.replace("<div id='jobs'></div>", f"<div id='jobs'>{_server_jobs_html()}</div>")
    selected_jd_json = json.dumps(selected_jd).replace("</", "<\\/")
    script_cfg_json = json.dumps(_load_call_script_config()).replace("</", "<\\/")
    prompt_cfg_json = json.dumps(_prompt_preview_config()).replace("</", "<\\/")
    html_doc = html_doc.replace("__SELECTED_JD_JSON__", selected_jd_json)
    html_doc = html_doc.replace("__SELECTED_JOB_ID_JSON__", json.dumps(selected_job_id))
    html_doc = html_doc.replace("__SCRIPT_CFG_JSON__", script_cfg_json)
    html_doc = html_doc.replace("__PROMPT_CFG_JSON__", prompt_cfg_json)
    banner = ""
    if saved == "1":
        banner = "<div id='flashBanner' style='background:#ecfdf3;border:1px solid #86efac;color:#166534;padding:8px 10px;border-radius:8px;margin:8px 0 10px'>Job saved successfully.</div>"
    elif saved == "updated":
        banner = "<div id='flashBanner' style='background:#ecfdf3;border:1px solid #86efac;color:#166534;padding:8px 10px;border-radius:8px;margin:8px 0 10px'>Job updated successfully.</div>"
    elif saved == "0":
        banner = "<div style='background:#fff4f4;border:1px solid #f7c3c3;color:#a12323;padding:8px 10px;border-radius:8px;margin:8px 0 10px'>Please enter both Job Title and Job Description.</div>"
    elif deleted == "1":
        banner = "<div style='background:#e8f2ff;border:1px solid #bfd3f8;color:#0b4fd6;padding:8px 10px;border-radius:8px;margin:8px 0 10px'>Job deleted successfully.</div>"
    elif deleted == "0":
        banner = "<div style='background:#fff4f4;border:1px solid #f7c3c3;color:#a12323;padding:8px 10px;border-radius:8px;margin:8px 0 10px'>Unable to delete job.</div>"
    if banner:
        html_doc = html_doc.replace("<h2>Softwise Technical Screening</h2>", "<h2>Softwise Technical Screening</h2>" + banner)
    return HTMLResponse(html_doc, headers={"Cache-Control": "no-store"})


@app.get('/favicon.ico')
def favicon():
    return Response(status_code=204)


@app.get("/config/check")
def config_check():
    required = [
        "TWILIO_ACCOUNT_SID",
        "TWILIO_AUTH_TOKEN",
        "TWILIO_PHONE_NUMBER",
        "PUBLIC_BASE_URL",
        "ELEVENLABS_API_KEY",
    ]
    status = {k: bool(os.getenv(k, "")) for k in required}
    status["OPENAI_API_KEY"] = bool(os.getenv("OPENAI_API_KEY", ""))
    status["VALIDATE_TWILIO_SIGNATURE"] = VALIDATE_TWILIO_SIGNATURE
    status["CALL_API_KEY"] = bool(CALL_API_KEY)
    return JSONResponse(status)
