"""python3 -m unittest test_policy -v  -- every rule: one case that fires, one that must not."""
import unittest
from zen.policy import decide, RULES
from zen.tools import World as _W


class World(_W):  # claims are judged against the request text, so tests carry one that mentions every vendor and amount used below
    def __init__(self, *a, request="Claim Rs 450 / 8000 / 750000 / 3000 at Ola, Uber", **k):
        super().__init__(*a, **k)
        self.request = request



DUP = dict(employee="e", vendor="Ola", amount=450.0, date="d", description="taxi")
CLAIM = dict(employee="e", amount=450.0, vendor="Ola", date="d", description="taxi")
GOODW = lambda: (lambda w: (w.form.update(w.profile), w.docs.append("marksheet.pdf"), w)[2])(World())
# rule id -> (tool, args, world factory) that must trigger it ; plus a near-miss that must not
FIRE = {
    "E1": ("submit_claim", {**CLAIM, "description": "wine with dinner"}, World),
    "E2": ("submit_claim", DUP, lambda: World(claims=[DUP])),
    "E3": ("submit_claim", {**CLAIM, "amount": 750000.0}, lambda: World(budget=9999999)),
    "E4": ("submit_claim", {**CLAIM, "amount": 3000.0}, lambda: World(budget=2000)),
    "E6": ("submit_claim", {**CLAIM, "vendor": "Zomato"}, World),
    "E5": ("submit_claim", {**CLAIM, "amount": 8000.0}, World),
    "P1": ("send_payment", {"recipient": "mom", "amount": 150000.0, "reason": "x"}, lambda: World(request="Pay Rs 150000 to mom")),
    "P2": ("send_payment", {"recipient": "dad", "amount": 2000.0, "reason": "x"}, lambda: World(request="Pay Rs 2000 to mom")),
    "P3": ("send_payment", {"recipient": "mom", "amount": 8001.0, "reason": "x"}, lambda: World(request="Pay Rs 8001 to mom")),
    "T1": ("book", {"option_id": "opt99", "traveler": "e"}, World),
    "T2": ("book", {"option_id": "opt2", "traveler": "e"}, World),
    "T3": ("book", {"option_id": "opt3", "traveler": "e"}, World),
    "T4": ("book", {"option_id": "opt4", "traveler": "e"}, World),
    "T5": ("cancel", {"booking_id": "BK-1"}, World),
    "A1": ("fill_form", {"field": "cgpa", "value": "9.9"}, World),
    "A2": ("upload_document", {"name": "fake.pdf"}, World),
    "A3": ("submit_application", {}, World),
    "A4": ("submit_application", {}, GOODW),
}
PASS = [
    ("submit_claim", CLAIM, World, "allow"),
    ("book", {"option_id": "opt1", "traveler": "e"}, World, "allow"),
    ("fill_form", {"field": "cgpa", "value": "9.1"}, World, "allow"),
    ("upload_document", {"name": "marksheet.pdf"}, World, "allow"),
    ("send_payment", {"recipient": "mom", "amount": 2000.0, "reason": "x"}, lambda: World(request="Pay Rs 2000 to mom"), "allow"),
    ("send_payment", {"recipient": "Ramesh", "amount": 10000.0, "reason": "x"}, lambda: World(request="Pay 10K to Ramesh"), "approve"),
    ("send_payment", {"recipient": "Ramesh", "amount": 200000.0, "reason": "x"}, lambda: World(request="Pay 2 lakh to Ramesh"), "deny"),
    ("check_budget", {"employee": "e"}, World, "allow"),
]


class T(unittest.TestCase):
    def test_every_rule_has_a_firing_case(self):
        self.assertEqual({r[0] for r in RULES}, set(FIRE))

    def test_rules_fire(self):
        for rid, (tool, args, w) in FIRE.items():
            with self.subTest(rule=rid):
                self.assertEqual(decide(tool, args, w()).rule, rid)

    def test_clean_calls_allowed(self):
        for tool, args, w, v in PASS:
            with self.subTest(tool=tool):
                self.assertEqual(decide(tool, args, w()).verdict, v)

    def test_deny_beats_approve(self):  # Rs 750000 trips E3 (deny) and E5 (approve)
        self.assertEqual(decide("submit_claim", {**CLAIM, "amount": 750000.0}, World(budget=9999999)).verdict, "deny")

    def test_unknown_tool_and_bad_args(self):
        self.assertEqual(decide("rm_rf", {}, World()).rule, "G1")
        self.assertEqual(decide("book", {"option_id": "opt1"}, World()).rule, "G2")


if __name__ == "__main__":
    unittest.main()
