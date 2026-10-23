# Kaki

A WhatsApp agent prototype with two modes:

- **Hawker mode:** helps a hawker stall owner with NEA and SFA grants, licences and helpers. Answers cite official pages; forms are pre-filled and the owner reviews and submits.
- **Staff mode:** helps an employee of Northbridge Capital, a fictional firm, with leave, public holidays, expense claims and travel requests. Policies are illustrative; the 2026 Singapore public holidays are real.

Send `staff` or `hawker` on WhatsApp to switch modes.

## How it works

- WhatsApp messages arrive from Twilio at `/whatsapp`.
- Claude Haiku answers using a knowledge file and a profile for the current mode (full context with prompt caching).
- When a task is needed, it calls the `prepare_form` tool. Python code fills known fields, computes fees, leave days, limits and approvers, and returns a review link (`/f/<id>`).
- Only the person can submit, on the review page. Submissions appear at `/submissions`.

## Files

| File | What it is |
| --- | --- |
| `app.py` | Web server, WhatsApp handling, Claude calls, mode switching |
| `forms.py` | Forms, validation, calculations, review pages |
| `knowledge.md`, `profile.json` | Hawker mode knowledge and demo profile |
| `knowledge_staff.md`, `profile_staff.json` | Staff mode knowledge and demo profile |
| `run_tests.py` | 27 test questions with expected answers |
| `render.yaml` | Render hosting settings |

## Running on Render

Deployed as a Render Blueprint (`render.yaml`): Starter plan, Singapore region. Set `ANTHROPIC_API_KEY`, `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN` in Render; then point Twilio's sandbox "When a message comes in" to `https://<your-service>.onrender.com/whatsapp`.

## Running locally (Windows)

Double-click `setup.bat` once, then `start.bat`. Copy the tunnel address plus `/whatsapp` into Twilio.

Prototype only: not an official government service, and Northbridge Capital is fictional.
