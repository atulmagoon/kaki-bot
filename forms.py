"""Demo application forms that Kaki can fill in, for two personas:

- "hawker": a hawker stall owner dealing with NEA and SFA (FormSG-style forms)
- "staff":  an employee at Northbridge Capital, a FICTIONAL firm (leave, expenses, travel)

Kaki pre-fills fields it already knows, the person reviews the form on a web page and
taps Submit (Kaki never submits on its own), and submissions are saved to submissions.json.
Nothing here is sent to any government agency or real company.
"""
import html
import json
import re
import secrets
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).parent
SUBMISSIONS_FILE = BASE_DIR / "submissions.json"


def _load(name: str) -> dict:
    return json.loads((BASE_DIR / name).read_text(encoding="utf-8"))


PROFILES = {"hawker": _load("profile.json"), "staff": _load("profile_staff.json")}

# Singapore public holidays 2026, including Mondays observed after Sunday holidays.
HOLIDAYS_2026 = {
    date(2026, 1, 1), date(2026, 2, 17), date(2026, 2, 18), date(2026, 3, 21), date(2026, 4, 3),
    date(2026, 5, 1), date(2026, 5, 27), date(2026, 6, 1), date(2026, 8, 10), date(2026, 11, 9),
    date(2026, 12, 25),
}

HOTEL_CAPS = {"jakarta": 250, "bangkok": 230, "kuala lumpur": 220, "ho chi minh": 220, "manila": 230,
              "hong kong": 400, "tokyo": 380, "sydney": 380, "london": 450, "new york": 500}
SEA_CITIES = {"jakarta", "bangkok", "kuala lumpur", "ho chi minh", "manila", "hanoi", "bali", "penang", "cebu"}


def _auto(persona: str) -> dict:
    p = PROFILES[persona]
    if persona == "hawker":
        return {
            "owner_name": ("Owner's name", p.get("name", "")),
            "stall": ("Stall", p.get("location", "")),
            "tenancy": ("Tenancy", p.get("tenancy", "")),
            "licence_expiry": ("Current licence expires", p.get("food_stall_licence_expiry", "")),
        }
    return {
        "employee": ("Employee", p.get("name", "")),
        "role": ("Role", p.get("role", "")),
        "manager": ("Approver (manager)", p.get("manager", "")),
        "cost_centre": ("Cost centre", p.get("cost_centre", "")),
        "leave_balance": ("Annual leave remaining (2026)", f"{p.get('annual_leave_remaining_2026', '')} days"),
    }


# (key, label, kind, required). kind is "text", "number", "date" or "choice:Option A|Option B".
FORMS = {
    "hawker": {
        "hpg_equipment": {
            "title": "Hawkers' Productivity Grant: equipment application (practice)",
            "owner": "NEA",
            "note": "The last HPG round closed on 31 Mar 2026. This practice application is saved so it is ready when the next round opens.",
            "auto": ["owner_name", "stall", "tenancy"],
            "fields": [
                ("equipment", "Equipment to buy", "text", True),
                ("supplier", "Supplier", "text", True),
                ("cost_before_gst", "Cost before GST (S$)", "number", True),
                ("quotation_date", "Quotation date", "text", False),
            ],
        },
        "licence_renewal": {
            "title": "Food stall licence renewal",
            "owner": "SFA",
            "note": "Fee: $32 for 1 year or $64 for 2 years. With GIRO, the licence renews automatically 2 months before expiry.",
            "auto": ["owner_name", "stall", "licence_expiry"],
            "fields": [
                ("period", "Renewal period", "choice:1 year|2 years", True),
                ("giro", "Set up GIRO for automatic renewal?", "choice:Yes|No", True),
            ],
        },
        "assistant_registration": {
            "title": "Register a hawker assistant",
            "owner": "NEA",
            "note": "In the real service, the assistant's NRIC is collected through Singpass, never in chat.",
            "auto": ["owner_name", "stall"],
            "fields": [
                ("assistant_name", "Assistant's full name", "text", True),
                ("assistant_age", "Assistant's age", "number", True),
                ("residency", "Residency status", "choice:Singapore Citizen|Permanent Resident|LTVP with PLOC or LOC", True),
                ("food_safety_cert", "Has a valid Food Safety Course certificate?", "choice:Yes|No", True),
            ],
        },
    },
    "staff": {
        "leave_application": {
            "title": "Leave application",
            "owner": "HR",
            "note": "Weekends and Singapore public holidays are not counted. Your manager approves in the HR system.",
            "auto": ["employee", "manager", "leave_balance"],
            "fields": [
                ("leave_type", "Leave type", "choice:Annual|Sick|Childcare|Unpaid", True),
                ("start_date", "First day (YYYY-MM-DD)", "date", True),
                ("end_date", "Last day (YYYY-MM-DD)", "date", True),
                ("half_day", "Half day?", "choice:No|AM|PM", False),
                ("cover", "Who covers your work", "text", False),
            ],
        },
        "expense_claim": {
            "title": "Expense claim",
            "owner": "Finance",
            "note": "Attach the itemised receipt. Claims submitted by the 20th are paid with this month's salary.",
            "auto": ["employee", "cost_centre"],
            "fields": [
                ("category", "Category", "choice:Client entertainment|Local transport|Travel meals|Travel hotel|Training|Other", True),
                ("amount", "Amount (S$)", "number", True),
                ("expense_date", "Date of expense (YYYY-MM-DD)", "date", True),
                ("merchant", "Merchant", "text", True),
                ("headcount", "Number of people (for entertainment)", "number", False),
                ("purpose", "Business purpose / clients", "text", True),
            ],
        },
        "travel_request": {
            "title": "Business travel request",
            "owner": "Finance",
            "note": "Travel insurance is arranged automatically once approved.",
            "auto": ["employee", "manager", "cost_centre"],
            "fields": [
                ("destination", "Destination city", "text", True),
                ("depart_date", "Departure date (YYYY-MM-DD)", "date", True),
                ("return_date", "Return date (YYYY-MM-DD)", "date", True),
                ("purpose", "Purpose", "text", True),
                ("est_flight_cost", "Estimated flight cost (S$)", "number", False),
            ],
        },
    },
}

DRAFTS: dict[str, dict] = {}


def form_catalogue(persona: str) -> str:
    lines = []
    for fid, f in FORMS[persona].items():
        keys = ", ".join(f"{k} ({'required' if req else 'optional'}{', YYYY-MM-DD' if kind == 'date' else ''})"
                         for k, _, kind, req in f["fields"])
        lines.append(f"- {fid}: {f['title']}. Fields: {keys}.")
    return "\n".join(lines)


def _number(value: str) -> float | None:
    m = re.search(r"\d[\d,]*(\.\d+)?", value or "")
    return float(m.group(0).replace(",", "")) if m else None


def _date(value: str) -> date | None:
    value = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", str(value or "").strip(), flags=re.I).replace(",", " ")
    value = re.sub(r"\s+", " ", value).strip()
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%b %d %Y", "%B %d %Y", "%d/%m/%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            pass
    # No year given ("dec 22", "22 December", "22/12"): use the next date on or after today.
    for fmt in ("%d %b", "%d %B", "%b %d", "%B %d", "%d/%m"):
        try:
            d = datetime.strptime(value, fmt).date()
        except ValueError:
            continue
        today = date.today()
        d = d.replace(year=today.year)
        return d if d >= today else d.replace(year=today.year + 1)
    return None


def _nice(d: date) -> str:
    return f"{d:%a} {d.day} {d:%b %Y}"


def working_days(start: date, end: date) -> int:
    n, d = 0, start
    while d <= end:
        if d.weekday() < 5 and d not in HOLIDAYS_2026:
            n += 1
        d += timedelta(days=1)
    return n


def _normalise(kind: str, value: str) -> str:
    value = (value or "").strip()
    if not value:
        return value
    if kind == "date":
        d = _date(value)
        return d.isoformat() if d else value
    if not kind.startswith("choice:"):
        return value
    options = kind.split(":", 1)[1].split("|")
    low = value.lower()
    for opt in options:
        if low == opt.lower() or low in opt.lower() or opt.lower() in low:
            return opt
    num = _number(value)
    if num is not None:
        for opt in options:
            if opt.startswith(str(int(num))):
                return opt
    return value


def _approver(amount: float) -> str:
    if amount <= 500:
        return "your manager"
    if amount <= 2000:
        return "a Director"
    return "a Managing Director plus Finance"


def _evaluate(draft: dict) -> None:
    """Work out missing fields, blocking warnings, non-blocking notes and computed values."""
    persona, fid = draft["persona"], draft["form_id"]
    form = FORMS[persona][fid]
    vals = draft["values"]
    draft["missing"] = [label for key, label, _, req in form["fields"] if req and not vals.get(key)]
    warnings, notes, computed = [], [], {}
    today = date.today()

    for key, label, kind, _ in form["fields"]:
        if kind == "date" and vals.get(key) and not _date(vals[key]):
            warnings.append(f"'{label}' should be a date like 2026-12-03.")

    if fid == "hpg_equipment" and vals.get("cost_before_gst"):
        cost = _number(vals["cost_before_gst"])
        if cost is None:
            warnings.append("The cost should be a number, for example 8600.")
        else:
            computed["Estimated grant"] = f"up to ${min(round(cost * 0.8), 7000):,} (80% of cost, max $7,000)"
    if fid == "licence_renewal" and vals.get("period"):
        computed["Fee"] = "$64" if vals["period"].startswith("2") else "$32"
    if fid == "assistant_registration":
        age = _number(vals.get("assistant_age", ""))
        if age is not None and age < 13:
            warnings.append("Hawker assistants must be 13 or older.")
        if vals.get("food_safety_cert") == "No":
            warnings.append("The assistant needs a valid Food Safety Course certificate before registering.")

    if fid == "leave_application":
        s, e = _date(vals.get("start_date", "")), _date(vals.get("end_date", ""))
        if s and e:
            if e < s:
                warnings.append("The last day is before the first day.")
            else:
                days = working_days(s, e)
                if vals.get("half_day") in ("AM", "PM"):
                    if s != e:
                        warnings.append("A half day can only be a single date.")
                    days = 0.5 if days else 0
                hols = sorted(h for h in HOLIDAYS_2026 if s <= h <= e)
                computed["Leave days counted"] = f"{days:g} working day{'s' if days != 1 else ''}"
                if hols:
                    computed["Public holidays skipped"] = ", ".join(_nice(h) for h in hols)
                if days == 0:
                    warnings.append("Those dates are all weekends or public holidays, so no leave is needed.")
                if vals.get("leave_type") == "Annual" and days:
                    remaining = PROFILES["staff"].get("annual_leave_remaining_2026", 0)
                    left = remaining - days
                    computed["Annual leave left after this"] = f"{left:g} day{'s' if left != 1 else ''}"
                    if days > remaining:
                        warnings.append(f"This needs {days:g} days but only {remaining} days of annual leave remain.")
                if s < today and vals.get("leave_type") != "Sick":
                    warnings.append("The first day is in the past. Check the dates.")
                if days > 2 and working_days(today + timedelta(days=1), s - timedelta(days=1)) < 5:
                    notes.append("Policy asks for 5 working days' notice for more than 2 days off. Your manager can still approve.")
                if vals.get("leave_type") == "Childcare" and not PROFILES["staff"].get("has_child_under_7"):
                    warnings.append("Childcare leave is for parents of a Singapore Citizen child under 7; HR has no such record for you.")
                if vals.get("leave_type") == "Unpaid":
                    notes.append("Unpaid leave also needs Director and HR approval.")

    if fid == "expense_claim":
        amt = _number(vals.get("amount", ""))
        d = _date(vals.get("expense_date", ""))
        if amt is not None:
            computed["Approver"] = _approver(amt)
            if vals.get("category") == "Client entertainment":
                heads = _number(vals.get("headcount", ""))
                if heads:
                    per_head = amt / heads
                    computed["Per person"] = f"S${per_head:,.2f} (limit S$150)"
                    if per_head > 150:
                        notes.append("Above S$150 per person, so a Director must approve.")
                        if amt <= 500:
                            computed["Approver"] = "a Director (over the per-person limit)"
                else:
                    warnings.append("For client entertainment, add the number of people, including staff.")
        if d:
            if d > today:
                warnings.append("The expense date is in the future.")
            elif (today - d).days > 60:
                warnings.append("Claims must be submitted within 60 days of the expense; this one is older.")
            else:
                computed["Submit by"] = _nice(d + timedelta(days=60))

    if fid == "travel_request":
        s, e = _date(vals.get("depart_date", "")), _date(vals.get("return_date", ""))
        city = (vals.get("destination") or "").lower()
        cap = next((v for k, v in HOTEL_CAPS.items() if k in city), 300) if city else None
        if cap:
            computed["Hotel cap"] = f"S${cap} per night"
        if s and e:
            if e < s:
                warnings.append("The return date is before the departure date.")
            else:
                nights = (e - s).days
                per_diem = 80 if any(c in city for c in SEA_CITIES) else 120
                computed["Nights"] = str(nights)
                computed["Meal allowance"] = f"S${per_diem} x {nights + 1} days = S${per_diem * (nights + 1):,}"
                flight = _number(vals.get("est_flight_cost", "")) or 0
                total = (cap or 300) * nights + per_diem * (nights + 1) + flight
                computed["Estimated total"] = f"S${total:,.0f}" + ("" if flight else " (excluding flight)")
                computed["Approver"] = _approver(total)
                if s < today:
                    warnings.append("The departure date is in the past.")
                elif working_days(today + timedelta(days=1), s - timedelta(days=1)) < 10:
                    notes.append("Policy asks for 10 working days' notice. Your manager can still approve.")

    draft["warnings"], draft["notes"], draft["computed"] = warnings, notes, computed


def prepare_draft(user: str, persona: str, form_id: str, fields: dict, draft_id: str | None, base_url: str) -> dict:
    forms = FORMS[persona]
    if form_id not in forms:
        return {"error": f"Unknown form. Choose one of: {', '.join(forms)}"}
    form = forms[form_id]
    draft = DRAFTS.get(draft_id) if draft_id else None
    if not draft or draft["form_id"] != form_id or draft["status"] != "draft" or draft["persona"] != persona:
        draft_id = secrets.token_urlsafe(6)
        draft = {"id": draft_id, "user": user, "persona": persona, "form_id": form_id, "values": {}, "status": "draft"}
        DRAFTS[draft_id] = draft
    kinds = {k: kind for k, _, kind, _ in form["fields"]}
    for key, value in (fields or {}).items():
        if key in kinds and str(value).strip():
            draft["values"][key] = _normalise(kinds[key], str(value))
    _evaluate(draft)
    auto = _auto(persona)
    complete = not draft["missing"] and not draft["warnings"]
    return {
        "draft_id": draft["id"],
        "form": form["title"],
        "filled_from_profile": {auto[a][0]: auto[a][1] for a in form["auto"]},
        "filled_from_chat": {label: draft["values"][k] for k, label, _, _ in form["fields"] if draft["values"].get(k)},
        "computed": draft["computed"],
        "missing": draft["missing"],
        "warnings": draft["warnings"],
        "notes": draft["notes"],
        "review_link": f"{base_url}/f/{draft['id']}" if complete and base_url else None,
        "next_step": "Send the review link; the person checks it and taps Submit."
        if complete else "Ask for the first missing item, or explain the warning.",
    }


def submit_draft(draft_id: str, form_data: dict) -> dict:
    draft = DRAFTS[draft_id]
    if draft["status"] == "submitted":
        return draft
    form = FORMS[draft["persona"]][draft["form_id"]]
    kinds = {k: kind for k, _, kind, _ in form["fields"]}
    for key in kinds:
        if key in form_data:
            draft["values"][key] = _normalise(kinds[key], str(form_data[key]))
    _evaluate(draft)
    if draft["missing"] or draft["warnings"]:
        return draft
    draft["status"] = "submitted"
    prefix = "KAKI" if draft["persona"] == "hawker" else "NB"
    draft["reference"] = f"{prefix}-{datetime.now():%y%m}-{secrets.randbelow(9000) + 1000}"
    draft["submitted_at"] = datetime.now().strftime("%d %b %Y, %H:%M")
    auto = _auto(draft["persona"])
    record = {
        "reference": draft["reference"], "persona": draft["persona"], "form": form["title"],
        "submitted_at": draft["submitted_at"],
        "profile": {auto[a][0]: auto[a][1] for a in form["auto"]},
        "values": draft["values"], "computed": draft["computed"],
    }
    try:
        existing = json.loads(SUBMISSIONS_FILE.read_text(encoding="utf-8")) if SUBMISSIONS_FILE.exists() else []
    except json.JSONDecodeError:
        existing = []
    existing.append(record)
    SUBMISSIONS_FILE.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    return draft


def after_submit_message(draft: dict) -> str:
    form = FORMS[draft["persona"]][draft["form_id"]]
    if draft["persona"] == "staff":
        approver = draft["computed"].get("Approver", "your manager")
        if draft["form_id"] == "leave_application":
            approver = PROFILES["staff"].get("manager", "your manager")
        return (f"Submitted! {form['title']} {draft['reference']} has gone to {approver} for approval. "
                "I'll tell you here when it's approved.")
    return f"Submitted! Your reference is {draft['reference']} for: {form['title']}. I'll keep you posted here."


# ---------- Web pages ----------

STYLE = """
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root { --bg:#F4F5F1; --card:#FFFFFF; --ink:#1C2420; --muted:#5E6A63; --line:#DADFD6; --accent:#1F6B4F; --warn:#95620A; --warn-bg:#F7EBCF; --note-bg:#E7EEF7; --note:#2A4E7A; }
* { box-sizing:border-box }
body { margin:0; background:var(--bg); color:var(--ink); font:16px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; padding:20px 16px 40px }
main { max-width:560px; margin:0 auto }
.demo { background:var(--warn-bg); color:var(--warn); font-size:13px; font-weight:600; border-radius:8px; padding:8px 12px; margin-bottom:14px }
.card { background:var(--card); border:1px solid var(--line); border-radius:12px; padding:18px }
h1 { font-size:21px; margin:0 0 4px } .sub { color:var(--muted); margin:0 0 14px; font-size:14px }
.row { padding:10px 0; border-top:1px solid var(--line) } .row:first-of-type { border-top:0 }
.lbl { font-size:13px; color:var(--muted); display:block; margin-bottom:4px }
.tag { font-size:11px; color:var(--accent); background:#DCEEE4; border-radius:6px; padding:1px 6px; margin-left:6px }
input, select { width:100%; font:inherit; padding:10px; border:1px solid var(--line); border-radius:8px; background:#fff; color:var(--ink) }
.note { font-size:14px; color:var(--muted); margin:14px 0 0 }
.warn { background:var(--warn-bg); color:var(--warn); border-radius:8px; padding:8px 12px; margin-top:12px; font-size:14px }
.info { background:var(--note-bg); color:var(--note); border-radius:8px; padding:8px 12px; margin-top:12px; font-size:14px }
.computed { font-weight:700 }
button { width:100%; margin-top:16px; background:var(--accent); color:#fff; border:0; border-radius:10px; padding:14px; font:600 16px system-ui, sans-serif; cursor:pointer }
.ref { font-size:24px; font-weight:700; letter-spacing:.02em }
table { width:100%; border-collapse:collapse; font-size:14px } td, th { text-align:left; border-top:1px solid var(--line); padding:8px 6px; vertical-align:top }
</style>
"""

BANNERS = {
    "hawker": "Kaki prototype demo. Nothing on this page is sent to any government agency.",
    "staff": "Kaki prototype demo. Northbridge Capital is a fictional firm and its policies are illustrative.",
}


def _e(s) -> str:
    return html.escape(str(s))


def _banner(persona: str) -> str:
    return f'<div class="demo">{_e(BANNERS[persona])}</div>'


def render_review(draft: dict, error: str = "") -> str:
    persona = draft["persona"]
    form = FORMS[persona][draft["form_id"]]
    auto = _auto(persona)
    rows = []
    for a in form["auto"]:
        label, value = auto[a]
        rows.append(f'<div class="row"><span class="lbl">{_e(label)}<span class="tag">from your profile</span></span>{_e(value)}</div>')
    for key, label, kind, req in form["fields"]:
        val = draft["values"].get(key, "")
        tag = '<span class="tag">from chat</span>' if val else ""
        if kind.startswith("choice:"):
            opts = "".join(f'<option{" selected" if o == val else ""}>{_e(o)}</option>' for o in kind.split(":", 1)[1].split("|"))
            control = f'<select id="{key}" name="{key}"><option value="">Choose…</option>{opts}</select>'
        else:
            itype = "date" if kind == "date" else "text"
            control = (f'<input id="{key}" name="{key}" type="{itype}" value="{_e(val)}" '
                       f'{"inputmode=decimal" if kind == "number" else ""} {"required" if req else ""}>')
        rows.append(f'<div class="row"><label class="lbl" for="{key}">{_e(label)}{tag}</label>{control}</div>')
    for k, v in draft.get("computed", {}).items():
        rows.append(f'<div class="row"><span class="lbl">{_e(k)}</span><span class="computed">{_e(v)}</span></div>')
    msgs = "".join(f'<div class="warn">{_e(w)}</div>' for w in draft.get("warnings", []))
    msgs += "".join(f'<div class="info">{_e(n)}</div>' for n in draft.get("notes", []))
    if error:
        msgs = f'<div class="warn">{_e(error)}</div>' + msgs
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Review: {_e(form['title'])}</title>{STYLE}</head>
<body><main>{_banner(persona)}<div class="card"><h1>{_e(form['title'])}</h1>
<p class="sub">Prepared by Kaki for {_e(form['owner'])}. Check each item, change anything that is wrong, then tap Submit.</p>
<form method="post" action="/f/{_e(draft['id'])}">{''.join(rows)}{msgs}
<p class="note">{_e(form['note'])}</p><button type="submit">Submit</button></form></div></main></body></html>"""


def render_done(draft: dict) -> str:
    form = FORMS[draft["persona"]][draft["form_id"]]
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Submitted</title>{STYLE}</head>
<body><main>{_banner(draft['persona'])}<div class="card"><h1>Submitted</h1><p class="sub">{_e(form['title'])}</p>
<div class="lbl">Reference</div><div class="ref">{_e(draft['reference'])}</div>
<p class="note">Submitted {_e(draft['submitted_at'])}. Kaki has sent the reference to your WhatsApp. You can close this page.</p>
</div></main></body></html>"""


def render_list() -> str:
    try:
        items = json.loads(SUBMISSIONS_FILE.read_text(encoding="utf-8")) if SUBMISSIONS_FILE.exists() else []
    except json.JSONDecodeError:
        items = []
    rows = "".join(
        f"<tr><td>{_e(s['reference'])}</td><td>{_e(s['form'])}</td><td>{_e(s['submitted_at'])}</td>"
        f"<td>{_e(', '.join(f'{k}: {v}' for k, v in s['values'].items()))}</td></tr>"
        for s in reversed(items)
    ) or '<tr><td colspan="4">No submissions yet.</td></tr>'
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>Kaki submissions</title>{STYLE}</head>
<body><main style="max-width:900px"><div class="demo">Kaki prototype demo. Hawker forms are not sent to any agency; Northbridge Capital is fictional.</div>
<div class="card"><h1>Submissions received</h1>
<p class="sub">What an approver or agency officer would see.</p>
<div style="overflow-x:auto"><table><tr><th>Reference</th><th>Form</th><th>Submitted</th><th>Details</th></tr>{rows}</table></div>
</div></main></body></html>"""
