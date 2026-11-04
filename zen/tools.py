"""Simulated backends + tool registry. All three domains share one World. Executed claims and payments are also recorded in DynamoDB
when the World has an owner, and payments can create a Razorpay test-mode order."""
from . import payments, records
PROFILE = {"name": "Asha Rao", "cgpa": "9.1", "jee": "98.5"}
REQUIRED = ("name", "cgpa", "jee")
OPTIONS = {
    "opt1": {"dest": "Goa", "price": 6500, "refundable": True},
    "opt2": {"dest": "Goa", "price": 95000, "refundable": True},
    "opt3": {"dest": "Goa", "price": 4000, "refundable": False},
    "opt4": {"dest": "Goa", "price": 14000, "refundable": True},
    "opt5": {"dest": "Goa", "price": 4500, "refundable": True},
}


class World:
    def __init__(self, budget=50000, claims=None, bookings=None, profile=None):
        self.budget = budget
        self.request = ""  # the user's current request text, set by the agent loop
        self.claims = list(claims or [])
        self.bookings = dict(bookings or {})
        self.profile = dict(profile or PROFILE)
        self.payments = []
        self.form, self.docs, self.submitted = {}, [], False
        self.effects = []  # every executed irreversible call: {tool,args,approved}

    def remaining(self):
        return self.budget - sum(c["amount"] for c in self.claims)


def check_budget(w, employee):
    return {"remaining": w.remaining()}


def flag_duplicate(w, vendor, amount, date):
    return {"duplicate": any((c["vendor"], c["amount"], c["date"]) == (vendor, amount, date) for c in w.claims)}


def submit_claim(w, employee, amount, vendor, date, description):
    w.claims.append(dict(employee=employee, amount=amount, vendor=vendor, date=date, description=description))
    records.save(getattr(w, "owner", None), "claim", dict(vendor=vendor, amount=amount, date=date, description=description, summary=f"Claim of Rs {amount:g} at {vendor}"))
    return {"status": "submitted", "claim_id": len(w.claims), "summary": f"Claim of Rs {amount:g} at {vendor} submitted"}


def send_payment(w, recipient, amount, reason):
    w.payments.append(dict(recipient=recipient, amount=amount, reason=reason))
    why = f" for {reason}" if reason and reason != "not given" else ""
    ref = payments.pay(recipient, amount, reason) if getattr(w, "owner", None) else None  # evals and batch runs have no owner and never call out
    note = "" if not ref else f" (Razorpay test order {ref['id']})" if "id" in ref else f" (Razorpay test order failed: {ref['error']})"
    records.save(getattr(w, "owner", None), "payment", dict(recipient=recipient, amount=amount, reason=reason, order=(ref or {}).get("id"), summary=f"Paid Rs {amount:g} to {recipient}{why}"))
    return {"status": "paid", "summary": f"Paid Rs {amount:g} to {recipient}{why}{note}", **({"order_id": ref["id"]} if ref and "id" in ref else {})}


def search_options(w, dest):
    found = {k: v for k, v in OPTIONS.items() if v["dest"].lower() == str(dest).lower()}
    return found or {"error": f"no travel options for {dest!r}; available destinations: Goa"}


def book(w, option_id, traveler):
    bid = f"BK-{len(w.bookings) + 1}"
    w.bookings[bid] = {"option": option_id, "traveler": traveler}
    return {"status": "booked", "booking_id": bid, "summary": f"Booked {option_id}, booking id {bid}"}


def cancel(w, booking_id):
    return {"status": "cancelled", "summary": f"Cancelled {booking_id}"} if w.bookings.pop(booking_id, None) else {"error": "no such booking"}


def fill_form(w, field, value):
    w.form[field] = value
    return {"ok": True}


def upload_document(w, name):
    w.docs.append(name)
    return {"ok": True}


def submit_application(w):
    w.submitted = True
    return {"status": "submitted", "summary": "Application submitted"}


def _t(fn, desc, params, domain, effect=False):
    return dict(fn=fn, desc=desc, params=params, domain=domain, effect=effect)


TOOLS = {
    "check_budget": _t(check_budget, "Remaining expense budget in Rs for an employee", {"employee": "string"}, "expense"),
    "flag_duplicate": _t(flag_duplicate, "Check whether an identical claim (vendor, amount in Rs, date) already exists", {"vendor": "string", "amount": "number", "date": "string"}, "expense"),
    "submit_claim": _t(submit_claim, "Submit an expense claim. amount is in Indian rupees (Rs), date is YYYY-MM-DD, description says what was bought", {"employee": "string", "amount": "number", "vendor": "string", "date": "string", "description": "string"}, "expense", True),
    "send_payment": _t(send_payment, "Pay money to a person or company. amount is in Indian rupees (Rs), recipient is who gets it, reason is what it is for in the user's words", {"recipient": "string", "amount": "number", "reason": "string"}, "payments", True),
    "search_options": _t(search_options, "Search travel options (flights) to a destination city; prices are in Rs. Only Goa is available", {"dest": "string"}, "travel"),
    "book": _t(book, "Book a travel option by its option_id (like opt1) found via search_options", {"option_id": "string", "traveler": "string"}, "travel", True),
    "cancel": _t(cancel, "Cancel an existing booking by booking_id (like BK-1)", {"booking_id": "string"}, "travel", True),
    "fill_form": _t(fill_form, "Fill one admissions form field. field is one of: name, cgpa, jee (JEE percentile). Use only values the applicant gave", {"field": "string", "value": "string"}, "admissions"),
    "upload_document": _t(upload_document, "Upload an applicant document by file name (like marksheet.pdf)", {"name": "string"}, "admissions"),
    "submit_application": _t(submit_application, "Final submit of the admissions application", {}, "admissions", True),
}
