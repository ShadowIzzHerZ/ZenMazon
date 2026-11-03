"""Approval queue + audit log. A risky call executes only via approve(token)."""
import time, uuid

QUEUE = {}  # token -> record


def request(call, world, rule, reason, draft=None):
    t = uuid.uuid4().hex[:8]
    QUEUE[t] = dict(token=t, call=call, rule=rule, reason=reason, draft=draft, status="pending", ts=time.time(), decided=None, world=world)
    return t


def decide(token, ok, by="human"):
    r = QUEUE[token]
    if r["status"] != "pending":
        raise ValueError(f"already {r['status']}")
    r.update(status="approved" if ok else "rejected", decided=time.time(), by=by)
    return r


def audit():
    return [{k: v for k, v in r.items() if k not in ("world", "ctx")} for r in QUEUE.values()]
