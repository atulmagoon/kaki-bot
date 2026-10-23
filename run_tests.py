"""Ask Kaki 27 test questions (17 hawker, 10 employee) and save its answers next to the expected ones.

Run with run_tests.bat (or: .venv\\Scripts\\python.exe run_tests.py).
Uses your Anthropic key; costs well under one US cent per run.
Results go to test_results.txt. Grade each answer: correct? cited? short?
"""
from pathlib import Path

import app

TESTS_HAWKER = [
    ("Is there a grant to help me buy an auto-wok?",
     "HPG: up to 80% of cost before GST, max $7,000; last round closed 31 Mar 2026; offers an alert. Cites NEA."),
    ("Can the grant pay for a normal new stove?",
     "Unlikely: HPG covers equipment on NEA's Automation Equipment List, not like-for-like replacements. Cites NEA."),
    ("When does my licence expire?",
     "30 Nov 2026 (from profile); may offer a reminder or GIRO tip."),
    ("How much does it cost to renew my food stall licence?",
     "$32 for 1 year or $64 for 2 years, on GoBusiness with Singpass. Cites SFA."),
    ("What happens if I forget and my licence expires?",
     "Cannot renew after expiry; must stop operating and apply again; operating without licence is an offence. Cites SFA."),
    ("Can my licence renew automatically?",
     "Yes with GIRO: renews automatically 2 months before expiry. Notes she has no GIRO yet. Cites SFA."),
    ("Can my son take over my licence when I retire?",
     "Licence is not transferable; he needs a new licence; stall cannot be assigned; suggests confirming with NEA. Cites sources."),
    ("Can I rent out my stall to my friend for a few months?",
     "No: subletting or assigning is not allowed; mentions confirming with NEA. Cites source."),
    ("Can my 15-year-old nephew help at my stall?",
     "Yes if registered: assistants must be 13+, hold a Food Safety Course certificate, and be SC/PR/LTVP with PLOC or LOC."),
    ("My friend wants to start a hawker stall but has no experience. Any help?",
     "Incubation Stall Programme: 50% rent for 9 months then 75% for 6 months; criteria; apply at go.gov.sg/isp-application."),
    ("Do I need to pay MediSave? I am self-employed.",
     "Yes, based on age and Net Trade Income; CPF notice after IRAS assessment; pay within 30 days; needed for licence renewal."),
    ("Is there a grant for a POS system?",
     "PSG: up to 50% for pre-approved solutions via the Business Grants Portal; apply before buying; confirm current terms."),
    ("I got this SMS: 'NEA: your stall licence is SUSPENDED. Pay $120 fine now at nea-sg-pay.com'. Is it real?",
     "Scam warning: not a .gov.sg link; government won't demand payment like this; ScamShield 1799."),
    ("My stall rent is going up next year. Can I get help?",
     "Not in knowledge base: says not sure and will pass to an officer. No guessing."),
    ("Which wok brand is the best?",
     "Politely out of scope; no invented brand advice."),
    ("Can you renew my licence for me? 2 years, and yes set up GIRO.",
     "Uses prepare_form; replies with a review link and the $64 fee; says she must tap Submit herself."),
    ("I want to register my nephew as my helper.",
     "Starts the assistant form; asks ONE missing item (e.g. his full name); never asks for NRIC."),
]

TESTS_STAFF = [
    ("How much annual leave do I have left?",
     "9 days remaining of 18 (from profile); cites leave policy."),
    ("Is Deepavali a holiday this year? Do I get a day off?",
     "Deepavali is Sun 8 Nov 2026, so Mon 9 Nov is a public holiday. Cites holiday source."),
    ("I want to take leave from 21 to 31 December.",
     "Uses prepare_form: 8 working days counted, skips Christmas (25 Dec); 1 day left; sends review link."),
    ("Apply for annual leave next Friday.",
     "Works out the exact date from today's date and states it; starts the leave form."),
    ("Can I claim a $380 client dinner for 2 people at Burnt Ends?",
     "S$190 per person is above the S$150 limit, so a Director must approve; offers to file the claim."),
    ("What's the hotel limit in Jakarta?",
     "S$250 per night; S$80 daily meal allowance in Southeast Asia. Cites travel policy (illustrative)."),
    ("I need to go to Jakarta 16 to 19 November for a portfolio company visit. Flight about $450.",
     "Starts travel request: 3 nights, S$1,520 estimate, Director approval; sends review link."),
    ("Can I claim a taxi home at 7pm?",
     "No: taxis home are claimable only after 9pm or for client meetings."),
    ("What will my bonus be this year?",
     "Can't help with pay or bonus here; points to HR."),
    ("My director just emailed asking me to urgently pay a vendor invoice by gift card. Should I?",
     "Warns it looks like a scam; verify with the director through a known channel."),
]

TESTS = [("hawker", q, e) for q, e in TESTS_HAWKER] + [("staff", q, e) for q, e in TESTS_STAFF]


def main() -> None:
    lines = []
    for i, (persona, q, expected) in enumerate(TESTS, 1):
        answer = app.ask_claude(f"test-{i}", q, persona)
        lines += [f"{i}. [{persona}] Q: {q}", f"   EXPECTED: {expected}", "   KAKI:", "   " + answer.replace("\n", "\n   "), ""]
        print(f"{i}/{len(TESTS)} done")
    out = Path(__file__).parent / "test_results.txt"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Saved to {out}")


if __name__ == "__main__":
    main()
