"""Kaki - step 3: hawker and employee modes (Twilio WhatsApp Sandbox version).

Receives WhatsApp messages through Twilio's sandbox webhook and replies using
Claude Haiku 5.5, grounded in knowledge.md and a demo owner profile (profile.json).
Kaki can fill in demo application forms (forms.py) as an agent: it gathers the details
in chat, pre-fills what it already knows, and sends a review link. The owner taps
Submit on that page; Kaki never submits on its own. English only.
"""
import base64
import hashlib
import hmac
import json
import re
import logging
import os
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import httpx
from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import HTMLResponse

import forms

load_dotenv()

TWILIO_ACCOUNT_SID = os.environ["TWILIO_ACCOUNT_SID"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TWILIO_WHATSAPP_FROM = os.environ.get("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")
PUBLIC_URL = os.environ.get("PUBLIC_URL", "").rstrip("/")  # optional: enables Twilio signature checks
MODEL = os.environ.get("MODEL", "claude-haiku-5-5")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kaki")

claude = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
app = FastAPI()

BASE_DIR = Path(__file__).parent
DEFAULT_MODE = os.environ.get("DEFAULT_MODE", "hawker")
KNOWLEDGE = {
    "hawker": (BASE_DIR / "knowledge.md").read_text(encoding="utf-8"),
    "staff": (BASE_DIR / "knowledge_staff.md").read_text(encoding="utf-8"),
}

RULES_HAWKER = """You are Kaki, a WhatsApp assistant that helps hawker stall owners in Singapore
with government grants, licences and paperwork.

You are an independent prototype, not an official government service. Never claim to be
the government or any agency.

How to answer:
- The first sentence answers the question directly. Then add at most 2 or 3 short
  sentences with the key details: numbers, deadlines, what to do next.
- If the answer uses the knowledge base, end with the source on its own line:
  "Source: <url>". Use only URLs that appear in the knowledge base.
- After that, only if useful, one short offer or follow-up question
  (for example, offering to fill in the form for them).
- Under 90 words. English only. Plain text; *bold* for at most one key number.
  No headings. Lists of at most 3 items.
- Hawkers read between orders: warm, simple words, no jargon.

Facts:
- Every scheme name, amount, fee, date or rule must come from the KNOWLEDGE BASE below.
- If the knowledge base does not answer the question, say plainly that you are not sure,
  and that you will pass the question to an officer who will reply in this chat.
  Do not guess, and do not send them off to "ask management".
- If a knowledge-base item says to confirm with the agency, say so in a few words.
- Use the OWNER PROFILE to personalise the answer (their licence expiry, stall, landlord).
  Never ask for something already in the profile.

Filling in forms (use the prepare_form tool):
- When the owner wants to renew their licence, register an assistant, or prepare an
  equipment grant application, offer to fill in the form, then use prepare_form.
- Call prepare_form as soon as you know the form, with whatever fields you already have.
  It fills profile details automatically and tells you what is missing.
- Ask for missing items ONE at a time, in plain words, then call prepare_form again with
  the same draft_id and the new values.
- If prepare_form returns warnings, explain them simply and ask how to proceed.
- When it returns a review_link, send it and say: tap the link, check the details, and tap
  Submit. Mention any computed value (fee or estimated grant). You never submit forms
  yourself; only the owner can, on that page.
- For the equipment grant, remind the owner that the round is closed and this is saved
  for the next round.

Safety:
- Never ask for passwords, OTPs, NRIC numbers or bank details. If the owner offers them,
  tell them not to share them in chat.
- If the owner forwards a message asking for payment or personal details, check it against
  the scam facts in the knowledge base and warn them clearly if it looks like a scam.
"""

RULES_STAFF = """You are Kaki, an internal assistant for employees of Northbridge Capital, a FICTIONAL
investment firm used for this prototype. You help with leave, public holidays, expense claims,
business travel and everyday admin.

Say the firm and its policies are illustrative if anyone asks whether they are real.
Never claim to be a real company's system.

How to answer:
- The first sentence answers the question directly. Then add at most 2 or 3 short sentences
  with the key details: numbers, dates, limits, who approves.
- When you use a policy, end with the source on its own line, e.g. "Source: Leave policy,
  Employee Handbook s.4 (illustrative)". For public holidays, cite the holiday source URL.
- Under 90 words. English only. Plain text; *bold* for at most one key number. No headings.
- Professional, friendly, concise: the employee is busy.

Facts:
- Every policy, limit, date or holiday must come from the KNOWLEDGE BASE below.
- Use the EMPLOYEE PROFILE (leave balance, manager, cost centre, grade). Never ask for
  something already in the profile.
- Use TODAY'S DATE to work out relative dates ("next Friday", "the first week of December").
  Always state the exact dates you used.
- If the knowledge base does not cover it (pay, bonus, performance, another employee,
  investment or deal questions), say you can't help with that here and name the right team.

Doing tasks (use the prepare_form tool):
- For leave, expense claims or travel requests, offer to fill in the form, then use
  prepare_form as soon as you know which form, with whatever fields you already have.
- Dates go into the tool as YYYY-MM-DD.
- Ask for missing items ONE at a time, then call prepare_form again with the same draft_id.
- If prepare_form returns warnings, explain them simply. Mention notes (e.g. short notice)
  and computed values (leave days counted, holidays skipped, approver, caps).
- When it returns a review_link, send it: check the details and tap Submit. You never submit
  anything yourself.

Safety:
- Never ask for passwords, OTPs, NRIC numbers or bank details.
- If someone forwards a suspicious message (fake invoice, urgent payment request from a
  "director"), warn them it may be a scam and to verify through a known channel.
"""

PROFILES_JSON = {p: json.dumps(forms.PROFILES[p], indent=2) for p in forms.PROFILES}


def system_blocks(persona: str) -> list:
    if persona == "staff":
        rules, label = RULES_STAFF, "EMPLOYEE PROFILE (demo data)"
    else:
        rules, label = RULES_HAWKER, "OWNER PROFILE (demo data)"
    return [
        {"type": "text", "text": rules},
        {
            "type": "text",
            "text": f"{label}\n{PROFILES_JSON[persona]}\n\nKNOWLEDGE BASE\n{KNOWLEDGE[persona]}",
            "cache_control": {"type": "ephemeral"},  # cached, so repeat messages cost less
        },
        {"type": "text", "text": f"TODAY'S DATE: {datetime.now():%A %d %B %Y}"},
    ]


def tools_for(persona: str) -> list:
    return [
        {
            "name": "prepare_form",
            "description": (
                "Create or update a draft form for the person. Profile details are filled "
                "automatically. Returns what was filled, computed values, missing fields, warnings, "
                "notes, and (when complete) a review_link they open to check and submit. "
                "This never submits anything.\nAvailable forms:\n" + forms.form_catalogue(persona)
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "form_id": {"type": "string", "enum": list(forms.FORMS[persona])},
                    "draft_id": {"type": "string", "description": "draft_id from an earlier call, to update that draft"},
                    "fields": {
                        "type": "object",
                        "description": "Values collected so far, keyed by field key",
                        "additionalProperties": {"type": "string"},
                    },
                },
                "required": ["form_id", "fields"],
            },
        }
    ]


DISCLAIMERS = {
    "hawker": "Hi! I'm Kaki, an independent prototype that helps hawkers with grants and licences. "
              "I'm not an official government service.\n\n",
    "staff": "Hi Daniel! I'm Kaki, your workplace assistant at Northbridge Capital "
             "(a fictional firm for this demo). I can help with leave, holidays, expenses and travel.\n\n",
}
SWITCH_HINT = "\n\n(Demo tip: send #staff or #hawker to switch modes.)"

EMPTY_TWIML = '<?xml version="1.0" encoding="UTF-8"?><Response></Response>'
MAX_LEN = 1500  # Twilio's WhatsApp limit is 1600 characters per message
MAX_HISTORY = 24
MAX_TOOL_ROUNDS = 4

HISTORY: dict[str, list] = defaultdict(list)
SEEN_USERS: set[tuple] = set()
MODE: dict[str, str] = {}
SEEN_MESSAGE_IDS: list[str] = []
STATE = {"base_url": PUBLIC_URL}  # learnt from incoming requests if PUBLIC_URL is blank


def signature_ok(url: str, params: dict, header: str | None) -> bool:
    """Check Twilio's X-Twilio-Signature when PUBLIC_URL is set."""
    if not PUBLIC_URL:
        return True
    data = url + "".join(k + params[k] for k in sorted(params))
    digest = hmac.new(TWILIO_AUTH_TOKEN.encode(), data.encode(), hashlib.sha1).digest()
    return hmac.compare_digest(base64.b64encode(digest).decode(), header or "")


async def send_text(to: str, body: str) -> None:
    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    if len(body) > MAX_LEN:
        body = body[: MAX_LEN - 1] + "…"
    async with httpx.AsyncClient(timeout=20, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)) as client:
        r = await client.post(url, data={"From": TWILIO_WHATSAPP_FROM, "To": to, "Body": body})
    if r.status_code >= 300:
        log.error("Twilio send failed %s: %s", r.status_code, r.text)


def run_tool(user: str, persona: str, name: str, args: dict) -> dict:
    if name == "prepare_form":
        result = forms.prepare_draft(
            user, persona, args.get("form_id", ""), args.get("fields") or {}, args.get("draft_id"), STATE["base_url"]
        )
        log.info("prepare_form %s -> missing=%s link=%s", args.get("form_id"), result.get("missing"), bool(result.get("review_link")))
        return result
    return {"error": f"Unknown tool {name}"}


def trim(history: list) -> None:
    """Keep recent turns, always starting at a plain user message."""
    while len(history) > MAX_HISTORY:
        history.pop(0)
        while history and not (history[0]["role"] == "user" and isinstance(history[0]["content"], str)):
            history.pop(0)


def ask_claude(user: str, text: str, persona: str | None = None) -> str:
    persona = persona or MODE.get(user, DEFAULT_MODE)
    history = HISTORY[user]
    history.append({"role": "user", "content": text})
    resp = None
    for _ in range(MAX_TOOL_ROUNDS + 1):
        resp = claude.messages.create(
            model=MODEL, max_tokens=600, system=system_blocks(persona), tools=tools_for(persona), messages=history,
        )
        history.append({"role": "assistant", "content": [b.model_dump(exclude_none=True) for b in resp.content]})
        if resp.stop_reason != "tool_use":
            break
        results = [
            {"type": "tool_result", "tool_use_id": b.id, "content": json.dumps(run_tool(user, persona, b.name, b.input))}
            for b in resp.content if b.type == "tool_use"
        ]
        history.append({"role": "user", "content": results})
    reply = "".join(b.text for b in resp.content if b.type == "text").strip()
    if resp.stop_reason == "tool_use":
        # Ran out of tool rounds: close the open tool calls so the history stays valid.
        history.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": b.id, "content": "Stopped: too many steps."}
            for b in resp.content if b.type == "tool_use"
        ]})
        reply = "Sorry, I got stuck preparing that. Could you say it again?"
        history.append({"role": "assistant", "content": reply})
    elif not reply:
        reply = "Sorry, could you say that again?"
    trim(history)
    return reply


def switch_command(text: str) -> str | None:
    t = re.sub(r"[^a-z ]", "", text.lower()).strip()
    t = re.sub(r"^(switch|change|go)( to)? ", "", t).replace(" mode", "").strip()
    if t in ("staff", "employee", "work", "office", "temasek", "northbridge"):
        return "staff"
    if t in ("hawker", "business", "stall", "kaki"):
        return "hawker"
    return None


async def handle_message(user: str, text: str, num_media: int) -> None:
    try:
        new_mode = switch_command(text) if text else None
        if new_mode:
            MODE[user] = new_mode
            HISTORY.pop(user, None)
            SEEN_USERS.add((user, new_mode))
            intro = {
                "staff": "Switched to *employee mode*. " + DISCLAIMERS["staff"].strip()
                         + " Try: \"How much leave do I have left?\"",
                "hawker": "Switched to *hawker mode*. " + DISCLAIMERS["hawker"].strip()
                          + " Try: \"Can you renew my licence for me?\"",
            }[new_mode]
            await send_text(user, intro)
            return
        persona = MODE.get(user, DEFAULT_MODE)
        if text:
            reply = ask_claude(user, text, persona)
        elif num_media:
            reply = "For now I can only read text messages. Please type your question."
        else:
            return
        if (user, persona) not in SEEN_USERS:
            SEEN_USERS.add((user, persona))
            reply = DISCLAIMERS[persona] + reply + SWITCH_HINT
        await send_text(user, reply)
    except Exception:
        log.exception("Failed to handle message from %s", user[-4:])
        HISTORY.pop(user, None)  # start fresh rather than repeat a broken conversation
        await send_text(user, "Sorry, something went wrong on my side. Please try again in a minute.")


def learn_base_url(request: Request) -> None:
    if PUBLIC_URL:
        return
    host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
    if host and not host.startswith(("localhost", "127.0.0.1")):
        STATE["base_url"] = f"https://{host}"


@app.post("/whatsapp")
async def receive(request: Request, tasks: BackgroundTasks) -> Response:
    form = await request.form()
    params = {k: str(v) for k, v in form.items()}
    if not signature_ok(f"{PUBLIC_URL}/whatsapp", params, request.headers.get("X-Twilio-Signature")):
        raise HTTPException(status_code=403, detail="Bad Twilio signature")
    learn_base_url(request)

    sid = params.get("MessageSid", "")
    if sid and sid in SEEN_MESSAGE_IDS:  # skip duplicate deliveries
        return Response(content=EMPTY_TWIML, media_type="application/xml")
    SEEN_MESSAGE_IDS.append(sid)
    del SEEN_MESSAGE_IDS[:-500]

    user = params.get("From", "")  # looks like "whatsapp:+6591234567"
    text = params.get("Body", "").strip()
    num_media = int(params.get("NumMedia", "0") or 0)
    log.info("Message from ...%s: %d chars, %d media", user[-4:], len(text), num_media)
    tasks.add_task(handle_message, user, text, num_media)
    # Reply asynchronously so slow model calls never hit Twilio's timeout.
    return Response(content=EMPTY_TWIML, media_type="application/xml")


@app.get("/f/{draft_id}", response_class=HTMLResponse)
async def review_form(draft_id: str) -> HTMLResponse:
    draft = forms.DRAFTS.get(draft_id)
    if not draft:
        return HTMLResponse("<h1>This link has expired.</h1><p>Ask Kaki on WhatsApp to prepare the form again.</p>", 404)
    if draft["status"] == "submitted":
        return HTMLResponse(forms.render_done(draft))
    return HTMLResponse(forms.render_review(draft))


@app.post("/f/{draft_id}", response_class=HTMLResponse)
async def submit_form(draft_id: str, request: Request, tasks: BackgroundTasks) -> HTMLResponse:
    draft = forms.DRAFTS.get(draft_id)
    if not draft:
        return HTMLResponse("<h1>This link has expired.</h1>", 404)
    already = draft["status"] == "submitted"
    data = {k: str(v) for k, v in (await request.form()).items()}
    draft = forms.submit_draft(draft_id, data)
    if draft["status"] != "submitted":
        return HTMLResponse(forms.render_review(draft, "Please complete the items marked below."))
    if not already:
        msg = forms.after_submit_message(draft)
        HISTORY[draft["user"]].append({"role": "user", "content": f"[System note: the owner submitted the form. Reference {draft['reference']}.]"})
        HISTORY[draft["user"]].append({"role": "assistant", "content": msg})
        tasks.add_task(send_text, draft["user"], msg)
        log.info("Form submitted: %s", draft["reference"])
    return HTMLResponse(forms.render_done(draft))


@app.get("/submissions", response_class=HTMLResponse)
async def submissions() -> HTMLResponse:
    return HTMLResponse(forms.render_list())


@app.get("/")
async def health() -> dict:
    return {"status": "Kaki is running", "model": MODEL, "default_mode": DEFAULT_MODE,
            "forms": {p: list(f) for p, f in forms.FORMS.items()}}
