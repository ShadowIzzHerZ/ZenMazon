"""Deterministic policy engine. Sits between model and tools; model cannot bypass it.
Each rule keeps its English source text (translated to code and reviewed by hand)."""
import re
from dataclasses import dataclass
from .tools import TOOLS, OPTIONS, REQUIRED

ALCOHOL = re.compile(r"\b(beers?|wines?|vodka|whisk(e)?y|whiskies|alcohol|cocktails?|bar tab|liquor)\b", re.I)
ALLOWED_DOCS = {"marksheet.pdf", "id_proof.pdf", "recommendation.pdf"}


@dataclass
class Decision:
    verdict: str  # allow | deny | approve
    rule: str = ""
    reason: str = ""


def _numbers(text):
    """Every amount the user wrote, including shorthand like 10K or 2 lakh."""
    t = text.replace(",", "")
    out = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", t)]
    for n, u in re.findall(r"(\d+(?:\.\d+)?)\s*(k|lakhs?|lacs?|crores?)\b", t, re.I):
        out.append(float(n) * {"k": 1e3, "l": 1e5, "c": 1e7}[u[0].lower()])
    return out


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# (id, english, tool, verdict, predicate(args, world) -> True when rule fires)
RULES = [
    ("E1", "Claims involving alcohol are never reimbursed.", "submit_claim", "deny",
     lambda a, w: bool(ALCOHOL.search(f"{a.get('description','')} {a.get('vendor','')}"))),
    ("E2", "Duplicate claims (same vendor, amount, date) are rejected.", "submit_claim", "deny",
     lambda a, w: any((c["vendor"], c["amount"], c["date"]) == (a.get("vendor"), a.get("amount"), a.get("date")) for c in w.claims)),
    ("E3", "Claim amount must be positive and at most Rs 100000.", "submit_claim", "deny",
     lambda a, w: not _num(a.get("amount")) or not 0 < a["amount"] <= 100000),
    ("E4", "Claims may not exceed the remaining budget.", "submit_claim", "deny",
     lambda a, w: _num(a.get("amount")) and a["amount"] > w.remaining()),
    ("E6", "Never invent claim details: the vendor and amount must come from the user's request.", "submit_claim", "deny",
     lambda a, w: str(a.get("vendor", "")).lower() not in w.request.lower()
     or float(a["amount"]) not in _numbers(w.request)),
    ("E5", "Claims over Rs 5000 need human approval.", "submit_claim", "approve",
     lambda a, w: _num(a.get("amount")) and a["amount"] > 5000),
    ("P1", "A payment must be positive and at most Rs 100000.", "send_payment", "deny",
     lambda a, w: not _num(a.get("amount")) or not 0 < a["amount"] <= 100000),
    ("P2", "Never invent payment details: the recipient and amount must come from the user's request.", "send_payment", "deny",
     lambda a, w: str(a.get("recipient", "")).lower() not in w.request.lower()
     or float(a["amount"]) not in _numbers(w.request)),
    ("P3", "Payments over Rs 5000 need human approval.", "send_payment", "approve",
     lambda a, w: _num(a.get("amount")) and a["amount"] > 5000),
    ("T1", "Bookings must reference a valid option.", "book", "deny",
     lambda a, w: a.get("option_id") not in OPTIONS),
    ("T2", "No single booking over Rs 50000.", "book", "deny",
     lambda a, w: OPTIONS.get(a.get("option_id"), {}).get("price", 0) > 50000),
    ("T3", "Non-refundable fares need human approval.", "book", "approve",
     lambda a, w: OPTIONS.get(a.get("option_id"), {}).get("refundable") is False),
    ("T4", "Bookings over Rs 10000 need human approval.", "book", "approve",
     lambda a, w: OPTIONS.get(a.get("option_id"), {}).get("price", 0) > 10000),
    ("T5", "Cancellations need human approval.", "cancel", "approve", lambda a, w: True),
    ("A1", "Never invent data: form values must match the verified applicant profile.", "fill_form", "deny",
     lambda a, w: w.profile.get(a.get("field")) != a.get("value")),
    ("A2", "Only the applicant's own documents may be uploaded.", "upload_document", "deny",
     lambda a, w: a.get("name") not in ALLOWED_DOCS),
    ("A3", "Final submit needs every required field filled and a marksheet uploaded.", "submit_application", "deny",
     lambda a, w: any(f not in w.form for f in REQUIRED) or "marksheet.pdf" not in w.docs),
    ("A4", "Final submit always needs human approval.", "submit_application", "approve", lambda a, w: True),
]


def decide(tool, args, world):
    spec = TOOLS.get(tool)
    if not spec:
        return Decision("deny", "G1", f"unknown tool {tool}")
    if set(args) != set(spec["params"]):
        return Decision("deny", "G2", f"bad arguments for {tool}: expected {sorted(spec['params'])}")
    hit = [(r, v) for r, _, t, v, p in RULES if t == tool and p(args, world)]
    for verdict in ("deny", "approve"):  # deny outranks approve
        for r, v in hit:
            if v == verdict:
                english = next(e for i, e, *_ in RULES if i == r)
                return Decision(verdict, r, english)
    return Decision("allow")
