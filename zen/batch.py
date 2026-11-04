"""Batch check: generate synthetic Indian corporate transactions, some with planted problems, and run each through the policy engine.
No LLM is involved, so 500 records take milliseconds. Each record knows the verdict it should get, so misses and false alarms are counted."""
import random, time
from .policy import decide
from .tools import OPTIONS, World

CLAIM_VENDORS = ["Ola", "Uber India", "Rapido", "IRCTC", "MakeMyTrip", "IndiGo", "Taj Hotels", "ITC Hotels", "OYO", "Swiggy", "Zomato", "Croma",
                 "Reliance Digital", "Amazon India", "Flipkart", "Staples India", "WeWork India", "Airtel", "Jio", "Cafe Coffee Day", "Starbucks India",
                 "Haldiram's", "Saravana Bhavan", "Vijay Sales", "BookMyShow", "Urban Company"]
CLAIM_WHAT = ["a cab ride", "train tickets", "a client lunch", "team snacks", "a laptop stand", "a monitor", "stationery", "a SIM recharge", "co-working day pass",
              "a hotel night", "airport transfer", "a conference pass", "printing", "courier charges", "a client dinner"]
PAYEES = ["Tata Power", "BSES Rajdhani", "Airtel Broadband", "Mahindra Logistics", "HDFC Ergo", "Zoho Corp", "Freshworks", "Sundaram Pvt Ltd", "Priya Nair",
          "Rahul Verma", "Anita Desai", "Amit Patel", "Kiran Rao", "Mr Sharma", "Mrs Iyer", "Suresh Menon", "Neha Gupta", "Vikram Singh", "Deepa Krishnan"]
PAY_FOR = ["the electricity bill", "office rent", "a freelance invoice", "internet charges", "insurance premium", "software licence", "a vendor invoice",
           "event catering", "courier services", "a training fee"]
DRINK = ["wine", "beer", "whisky", "vodka", "cocktails"]
DISGUISED = ["Old Monk rum", "Kingfisher Strong", "Blenders Pride", "single malt", "IMFL", "a brewery tasting", "scotch"]  # the alcohol rule's word list does not know these

# (kind, plant, expected verdict, share of the batch)
PLAN = [("claim", "clean", "allow", .24), ("claim", "needs approval", "approve", .08), ("claim", "alcohol", "deny", .025), ("claim", "disguised alcohol", "deny", .016),
        ("claim", "duplicate", "deny", .03), ("claim", "over the cap", "deny", .016), ("claim", "over budget", "deny", .016), ("claim", "invented details", "deny", .02),
        ("payment", "clean", "allow", .2), ("payment", "needs approval", "approve", .08), ("payment", "over the cap", "deny", .02), ("payment", "invented details", "deny", .024),
        ("booking", "clean", "allow", .06), ("booking", "needs approval", "approve", .05), ("booking", "invalid option", "deny", .016), ("booking", "over the cap", "deny", .014)]


def _date(r):
    return f"2026-{r.choice([1, 2, 3])}-{r.randint(1, 28):02d}".replace("-1-", "-01-").replace("-2-", "-02-").replace("-3-", "-03-")


def _claim(r, plant):
    v, what, d = r.choice(CLAIM_VENDORS), r.choice(CLAIM_WHAT), _date(r)
    amt = r.randint(150, 4800) if plant in ("clean", "duplicate", "alcohol", "disguised alcohol", "invented details") else r.randint(5100, 60000)
    world = World(budget=10_000_000)
    desc = what
    args_vendor, args_amt = v, amt
    if plant == "alcohol":
        desc = f"{r.choice(DRINK)} with dinner"
    elif plant == "disguised alcohol":
        desc = f"{r.choice(DISGUISED)} for the team"
    elif plant == "duplicate":
        world.claims.append(dict(employee="emp1", amount=amt, vendor=v, date=d, description=what))
    elif plant == "over the cap":
        amt = args_amt = r.randint(100_500, 400_000)
    elif plant == "over budget":
        world = World(budget=20000, claims=[dict(employee="emp1", amount=16000, vendor="Earlier claim", date=d, description="")])
        amt = args_amt = r.randint(4100, 9000)
    elif plant == "invented details":
        if r.random() < .5:
            args_vendor = r.choice([x for x in CLAIM_VENDORS if x != v])
        else:
            args_amt = amt + r.choice([50, 500, 1000])
    text = f"Claim Rs {amt} for {desc} at {v} on {d}."
    world.request = text
    return text, amt, "submit_claim", dict(employee="emp1", amount=args_amt, vendor=args_vendor, date=d, description=desc), world


def _payment(r, plant):
    who, why = r.choice(PAYEES), r.choice(PAY_FOR)
    amt = r.randint(300, 4900) if plant in ("clean", "invented details") else r.randint(5200, 90000)
    args_who, args_amt = who, amt
    if plant == "over the cap":
        amt = args_amt = r.randint(100_500, 350_000)
    elif plant == "invented details":
        if r.random() < .5:
            args_who = r.choice([x for x in PAYEES if x != who])
        else:
            args_amt = amt + r.choice([100, 1000, 2500])
    text = f"Pay Rs {amt} to {who} for {why}"
    w = World(budget=10_000_000)
    w.request = text
    return text, amt, "send_payment", dict(recipient=args_who, amount=args_amt, reason=why), w


def _booking(r, plant):
    opt = {"clean": r.choice(["opt1", "opt5"]), "needs approval": r.choice(["opt3", "opt4"]), "invalid option": "opt9", "over the cap": "opt2"}[plant]
    text = f"Book option {opt} to Goa."
    w = World(budget=10_000_000)
    w.request = text
    return text, OPTIONS.get(opt, {}).get("price"), "book", dict(option_id=opt, traveler="emp1"), w


GEN = dict(claim=_claim, payment=_payment, booking=_booking)


def run(n=1000, seed=None):
    seed = int(seed if seed is not None else time.time()) % 10_000_000
    r = random.Random(seed)
    kinds = []
    for kind, plant, exp, share in PLAN:
        kinds += [(kind, plant, exp)] * round(share * n)
    while len(kinds) < n:
        kinds.append(("claim", "clean", "allow"))
    r.shuffle(kinds)
    rows = []
    for i, (kind, plant, exp) in enumerate(kinds[:n], 1):
        text, amount, tool, args, world = GEN[kind](r, plant)
        d = decide(tool, args, world)
        rows.append(dict(id=f"TX-{i:03d}", kind=kind, tool=tool, text=text, amount=amount, verdict=d.verdict, rule=d.rule, reason=d.reason, expected=exp, plant=plant, ok=d.verdict == exp))
    bad = [x for x in rows if x["expected"] == "deny"]
    return dict(seed=seed, n=len(rows), rows=rows,
                counts={v: sum(x["verdict"] == v for x in rows) for v in ("allow", "approve", "deny")},
                planted=len(bad), caught=sum(x["verdict"] == "deny" for x in bad),
                missed=sum(x["verdict"] != "deny" for x in bad),
                false_alarms=sum(x["verdict"] == "deny" and x["expected"] != "deny" for x in rows),
                correct=sum(x["ok"] for x in rows))
