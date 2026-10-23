"""Kaki for Business - step 1: WhatsApp <-> Claude Haiku.

Receives WhatsApp messages through Meta's Cloud API webhook and replies
using Claude Haiku 5.5. English only. Knowledge, the sample stall profile
and photo reading are added in later steps.
"""
import hashlib
import hmac
import logging
import os
from collections import defaultdict, deque

import httpx
from anthropic import Anthropic
from dotenv import load_dotenv
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response

load_dotenv()

WHATSAPP_TOKEN = os.environ["WHATSAPP_TOKEN"]
PHONE_NUMBER_ID = os.environ["PHONE_NUMBER_ID"]
VERIFY_TOKEN = os.environ["VERIFY_TOKEN"]
APP_SECRET = os.environ.get("APP_SECRET", "")
GRAPH_VERSION = os.environ.get("GRAPH_VERSION", "v23.0")
MODEL = os.environ.get("MODEL", "claude-haiku-5-5")

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("kaki")

claude = Anthropic()  # reads ANTHROPIC_API_KEY from the environment
app = FastAPI()

SYSTEM_PROMPT = """You are Kaki, a WhatsApp assistant that helps hawker stall owners in Singapore
with government grants, licences and paperwork.

You are an independent prototype, not an official government service. Never claim to be
the government or any agency.

How to reply:
- English only. Plain, warm, short: 2 to 5 sentences. Hawkers read on their phone between orders.
- One question at a time if you need more information.
- Never invent scheme names, amounts, dates or eligibility rules. If you are not sure,
  say so plainly and say you would pass the question to an officer.
- Never ask for passwords, OTPs, NRIC numbers or bank details. If someone offers them,
  tell them not to share them in chat.
- If the owner forwards a suspicious message asking for payment or personal details,
  warn them it may be a scam and that official links end in .gov.sg.
"""

DISCLAIMER = (
    "Hi! I'm Kaki, an independent prototype that helps hawkers with grants and licences. "
    "I'm not an official government service.\n\n"
)

HISTORY: dict[str, deque] = defaultdict(lambda: deque(maxlen=12))
SEEN_USERS: set[str] = set()
SEEN_MESSAGE_IDS: deque = deque(maxlen=500)


def signature_ok(body: bytes, header: str | None) -> bool:
    """Check Meta's X-Hub-Signature-256 header when APP_SECRET is set."""
    if not APP_SECRET:
        return True
    if not header or not header.startswith("sha256="):
        return False
    expected = hmac.new(APP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header.removeprefix("sha256="))


async def send_text(to: str, body: str) -> None:
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{PHONE_NUMBER_ID}/messages"
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(url, json=payload, headers={"Authorization": f"Bearer {WHATSAPP_TOKEN}"})
    if r.status_code >= 300:
        log.error("WhatsApp send failed %s: %s", r.status_code, r.text)


def ask_claude(user: str, text: str) -> str:
    history = HISTORY[user]
    history.append({"role": "user", "content": text})
    resp = claude.messages.create(
        model=MODEL,
        max_tokens=600,
        system=SYSTEM_PROMPT,
        messages=list(history),
    )
    reply = "".join(b.text for b in resp.content if b.type == "text").strip()
    history.append({"role": "assistant", "content": reply})
    return reply


async def handle_message(msg: dict) -> None:
    user = msg["from"]
    kind = msg.get("type")
    try:
        if kind == "text":
            reply = ask_claude(user, msg["text"]["body"])
        else:
            reply = "For now I can only read text messages. Please type your question."
        if user not in SEEN_USERS:
            SEEN_USERS.add(user)
            reply = DISCLAIMER + reply
        await send_text(user, reply)
    except Exception:
        log.exception("Failed to handle message from %s", user)
        await send_text(user, "Sorry, something went wrong on my side. Please try again in a minute.")


@app.get("/webhook")
async def verify(request: Request) -> Response:
    """Meta calls this once when you register the webhook URL."""
    p = request.query_params
    if p.get("hub.mode") == "subscribe" and p.get("hub.verify_token") == VERIFY_TOKEN:
        return Response(content=p.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verify token does not match")


@app.post("/webhook")
async def receive(request: Request, tasks: BackgroundTasks) -> dict:
    body = await request.body()
    if not signature_ok(body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="Bad signature")
    data = await request.json()
    for entry in data.get("entry", []):
        for change in entry.get("changes", []):
            for msg in change.get("value", {}).get("messages", []):
                if msg["id"] in SEEN_MESSAGE_IDS:  # Meta retries deliveries; skip duplicates
                    continue
                SEEN_MESSAGE_IDS.append(msg["id"])
                log.info("Message from %s (%s)", msg["from"], msg.get("type"))
                tasks.add_task(handle_message, msg)
    return {"ok": True}  # reply fast so Meta does not retry


@app.get("/")
async def health() -> dict:
    return {"status": "Kaki is running", "model": MODEL}
