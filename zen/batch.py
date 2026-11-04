"""Batch check: generate synthetic Indian corporate transactions, some with planted problems, and run each through the policy engine.
No LLM is involved, so 500 records take milliseconds. Each record knows the verdict it should get, so misses and false alarms are counted."""
import random, time
from .policy import decide
from .tools import OPTIONS, World

# (what was bought, vendors that really sell it, usual amount range in Rs). Each pairing is something a company would actually expense.
SMALL = [("a cab ride", ["Ola", "Uber India", "Rapido", "Meru Cabs"], (120, 1800)), ("an airport transfer", ["Ola", "Uber India", "Meru Cabs"], (400, 2500)),
         ("train tickets", ["IRCTC"], (350, 4200)), ("a client lunch", ["Barbeque Nation", "Haldiram's", "Saravana Bhavan", "Social", "Burger King India"], (600, 3800)),
         ("team snacks", ["Swiggy", "Zomato", "Haldiram's", "Starbucks India", "Cafe Coffee Day"], (250, 2200)), ("a laptop accessory", ["Croma", "Reliance Digital", "Vijay Sales", "Amazon India"], (500, 4500)),
         ("office stationery", ["Staples India", "Amazon India", "Flipkart"], (200, 2800)), ("a mobile recharge", ["Airtel", "Jio", "Vi"], (199, 1500)),
         ("a co-working day pass", ["WeWork India", "Awfis", "91springboard"], (500, 2200)), ("courier charges", ["Blue Dart", "DTDC", "Delhivery"], (90, 1400)),
         ("client gifts", ["Ferns N Petals", "Archies", "Titan"], (800, 4500)), ("a software subscription", ["Zoho", "Freshworks", "Atlassian", "Notion"], (500, 4800)),
         ("a printing job", ["Staples India", "Kinko's", "Xerox India"], (150, 3200)), ("a parking fee", ["Mumbai Airport", "Select Citywalk", "Phoenix Mall"], (60, 900))]
BIG = [("flight tickets", ["IndiGo", "Air India", "Vistara", "Akasa Air"], (5200, 28000)), ("a hotel stay", ["Taj Hotels", "ITC Hotels", "Lemon Tree Hotels", "The Leela"], (5500, 18000)),
       ("a conference pass", ["Nasscom", "TiE Mumbai", "HeadStart"], (5200, 40000)), ("a laptop", ["Croma", "Reliance Digital", "Apple Store India", "Amazon India"], (30000, 95000)),
       ("office chairs", ["Godrej Interio", "Featherlite", "Urban Ladder"], (6000, 45000)), ("a team offsite", ["Taj Hotels", "Club Mahindra", "Zostel"], (15000, 80000)),
       ("client event catering", ["Bikanervala", "ITC Hotels", "Taj Hotels"], (12000, 70000)), ("an annual software licence", ["Zoho", "Freshworks", "Atlassian", "Microsoft India"], (8000, 90000))]
HUGE = [("a team offsite", ["Taj Hotels", "Club Mahindra", "The Leela"], (100500, 300000)), ("an annual software licence", ["Zoho", "Atlassian", "Microsoft India"], (105000, 350000)),
        ("a laptop fleet purchase", ["Dell India", "HP World", "Lenovo India"], (110000, 400000)), ("a client conference sponsorship", ["Nasscom", "TiE Mumbai"], (120000, 380000))]
DRINK = ["wine with a client dinner", "beer at the team outing", "whisky for the partner dinner", "cocktails at the awards night", "a bar tab at the offsite", "vodka for the launch party"]
DISGUISED = ["Old Monk rum for the Diwali party", "Kingfisher Strong at the team outing", "Blenders Pride for the client dinner", "a single malt for the partner gift", "IMFL for the offsite", "a brewery tasting for the team", "scotch for the board dinner"]  # the alcohol rule's word list does not know these
RESTAURANTS = ["Barbeque Nation", "Social", "Taj Hotels", "ITC Hotels", "The Leela", "Hard Rock Cafe"]
# (payees, what the payment is for, usual amount range in Rs)
PAY = [(["Tata Power", "BSES Rajdhani", "Adani Electricity", "MSEDCL"], ["the electricity bill"], (2400, 4800)),
       (["Airtel Broadband", "ACT Fibernet", "Jio Fiber"], ["the office internet bill"], (800, 4200)),
       (["Mr Sharma", "Mrs Iyer", "Mr Kulkarni"], ["office rent", "guest house rent"], (3000, 4900)),
       (["HDFC Ergo", "ICICI Lombard", "Star Health"], ["the group insurance premium"], (1500, 4900)),
       (["Priya Nair", "Rahul Verma", "Anita Desai", "Amit Patel", "Kiran Rao", "Neha Gupta", "Vikram Singh"], ["a freelance invoice", "a referral bonus", "a reimbursement", "a training fee"], (500, 4800)),
       (["Sundaram Pvt Ltd", "Mahindra Logistics", "Infosys BPM", "Zoho Corp", "Freshworks", "Wipro Facilities"], ["a vendor invoice", "logistics charges", "a software licence", "event catering"], (900, 4900))]
PAY_BIG = [(["Mr Sharma", "Mrs Iyer", "Mr Kulkarni"], ["office rent", "guest house rent"], (25000, 90000)), (["HDFC Ergo", "ICICI Lombard", "Star Health"], ["the annual insurance premium"], (12000, 80000)),
           (["Sundaram Pvt Ltd", "Mahindra Logistics", "Infosys BPM", "Zoho Corp", "Wipro Facilities"], ["a vendor invoice", "logistics charges", "a software licence", "a facilities contract"], (6000, 95000)),
           (["Priya Nair", "Rahul Verma", "Anita Desai", "Amit Patel", "Kiran Rao"], ["a consulting invoice", "a quarterly bonus"], (8000, 60000))]
PAY_HUGE = [(["Sundaram Pvt Ltd", "Mahindra Logistics", "Infosys BPM", "Wipro Facilities"], ["a vendor invoice", "a facilities contract"], (100500, 350000))]
PURPOSE = ["the sales offsite", "a client meeting", "the quarterly review", "a vendor visit", "a team workshop", "a customer demo"]

# (kind, plant, expected verdict, share of the batch)
PLAN = [("claim", "clean", "allow", .24), ("claim", "needs approval", "approve", .08), ("claim", "alcohol", "deny", .025), ("claim", "disguised alcohol", "deny", .016),
        ("claim", "duplicate", "deny", .03), ("claim", "over the cap", "deny", .016), ("claim", "over budget", "deny", .016), ("claim", "invented details", "deny", .02),
        ("payment", "clean", "allow", .2), ("payment", "needs approval", "approve", .08), ("payment", "over the cap", "deny", .02), ("payment", "invented details", "deny", .024),
        ("booking", "clean", "allow", .06), ("booking", "needs approval", "approve", .05), ("booking", "invalid option", "deny", .016), ("booking", "over the cap", "deny", .014)]


def _date(r):
    return f"2026-{r.choice([1, 2, 3]):02d}-{r.randint(1, 28):02d}"


def _pick(r, table):
    what, vendors, (lo, hi) = r.choice(table)
    return what, r.choice(vendors), r.randint(lo, hi)


def _claim(r, plant):
    d = _date(r)
    if plant in ("needs approval", "over budget"):
        what, v, amt = _pick(r, BIG if plant == "needs approval" else SMALL)
    elif plant == "over the cap":
        what, v, amt = _pick(r, HUGE)
    else:
        what, v, amt = _pick(r, SMALL)
    world, desc, args_vendor, args_amt = World(budget=10_000_000), what, v, amt
    if plant == "alcohol":
        v, desc = args_vendor, r.choice(DRINK)
        v = args_vendor = r.choice(RESTAURANTS)
    elif plant == "disguised alcohol":
        v = args_vendor = r.choice(RESTAURANTS)
        desc = r.choice(DISGUISED)
    elif plant == "duplicate":
        world.claims.append(dict(employee="emp1", amount=amt, vendor=v, date=d, description=what))
    elif plant == "over budget":
        world = World(budget=20000, claims=[dict(employee="emp1", amount=16000, vendor="Earlier claim", date=d, description="")])
        amt = args_amt = r.randint(4100, 9000)
    elif plant == "invented details":
        if r.random() < .5:
            args_vendor = r.choice([x for x in {y for _, vs, _ in SMALL for y in vs} if x != v])
        else:
            args_amt = amt + r.choice([50, 500, 1000])
    text = f"Claim Rs {amt} for {desc} at {v} on {d}."
    world.request = text
    return text, amt, "submit_claim", dict(employee="emp1", amount=args_amt, vendor=args_vendor, date=d, description=desc), world


def _payment(r, plant):
    table = PAY_HUGE if plant == "over the cap" else PAY_BIG if plant == "needs approval" else PAY
    payees, reasons, (lo, hi) = r.choice(table)
    who, why, amt = r.choice(payees), r.choice(reasons), r.randint(lo, hi)
    args_who, args_amt = who, amt
    if plant == "invented details":
        if r.random() < .5:
            args_who = r.choice([x for x in {y for ps, _, _ in PAY for y in ps} if x != who])
        else:
            args_amt = amt + r.choice([100, 1000, 2500])
    text = f"Pay Rs {amt} to {who} for {why}"
    w = World(budget=10_000_000)
    w.request = text
    return text, amt, "send_payment", dict(recipient=args_who, amount=args_amt, reason=why), w


def _booking(r, plant):
    opt = {"clean": r.choice(["opt1", "opt5"]), "needs approval": r.choice(["opt3", "opt4"]), "invalid option": "opt9", "over the cap": "opt2"}[plant]
    text = f"Book option {opt} to Goa for {r.choice(PURPOSE)}."
    w = World(budget=10_000_000)
    w.request = text
    return text, OPTIONS.get(opt, {}).get("price"), "book", dict(option_id=opt, traveler="emp1"), w


GEN = dict(claim=_claim, payment=_payment, booking=_booking)


def run(n=2000, seed=None):
    seed = int(seed) % 10_000_000 if seed is not None else random.SystemRandom().randrange(10_000_000)  # a fresh shuffle every run and every restart
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
