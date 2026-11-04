"""Audit log + conversation memory, per user. Every write goes to a local file; when SUPABASE_URL and SUPABASE_KEY (the anon key) are set
it is also mirrored to Supabase (PostgREST) with the signed-in user's JWT, so row-level security decides what each user can read and write.
Reads then come from Supabase. A remote failure never breaks the app. `u` is the user dict from server.user_of: id, email, jwt."""
import json, os, queue, threading, time, urllib.parse, urllib.request, uuid
from . import net

FILE = ".zen_store.json"
STATUS = {"error": None}  # last Supabase error, shown on the dashboard
_lock = threading.Lock()
_db = {"runs": [], "audit": []}
if os.path.exists(FILE):
    try:
        _db = json.load(open(FILE))
    except Exception:
        pass


def configured():
    return bool(os.environ.get("SUPABASE_URL") and os.environ.get("SUPABASE_KEY"))


def _save():
    with _lock:
        json.dump(_db, open(FILE, "w"))


def _remote(method, table, body=None, query="", jwt=None):
    if not configured() or not jwt:
        return None
    req = urllib.request.Request(f'{os.environ["SUPABASE_URL"]}/rest/v1/{table}{query}', json.dumps(body).encode() if body is not None else None,
                                 method=method, headers={"apikey": os.environ["SUPABASE_KEY"], "Authorization": "Bearer " + jwt, "Content-Type": "application/json"})
    try:
        raw = net.urlopen(req, timeout=10).read()
        STATUS["error"] = None
        return json.loads(raw) if raw else []
    except Exception as e:
        STATUS["error"] = str(getattr(e, "read", lambda: e)())[:200] if hasattr(e, "read") else str(e)[:200]
        return None


_q = queue.Queue()


def _worker():
    while True:
        a, k = _q.get()
        _remote(*a, **k)


threading.Thread(target=_worker, daemon=True).start()


def _mirror(u, *a, **k):  # one ordered worker: the UI never waits on the network, and a status update never overtakes its insert
    if configured() and u.get("jwt"):
        _q.put((a, dict(k, jwt=u["jwt"])))


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")


def log_run(u, conv_id, title, run):
    row = dict(id=str(uuid.uuid4()), conv_id=conv_id, title=title, request=run["request"], status=run["status"], mode=run.get("mode"),
               token=run.get("token"), result=run, created_at=_now())
    _db["runs"].append(dict(row, user_id=u["id"]))
    _save()
    _mirror(u, "POST", "zen_runs", row)


def log_audit(u, kind, conv_id, tool, args, rule="", rule_text="", note="", token=None):
    row = dict(id=str(uuid.uuid4()), conv_id=conv_id, kind=kind, tool=tool, args=args, rule=rule, rule_text=rule_text, note=note, token=token, created_at=_now())
    _db["audit"].append(dict(row, user_id=u["id"]))
    _save()
    _mirror(u, "POST", "zen_audit", row)


def set_decision(u, token, status):
    for r in _db["runs"]:
        if r.get("token") == token and r.get("user_id") == u["id"]:
            r["status"] = status
    _save()
    _mirror(u, "PATCH", "zen_runs", {"status": status}, f"?token=eq.{urllib.parse.quote(token)}")


def conversations(u):
    rows = _remote("GET", "zen_runs", query="?select=conv_id,title,created_at&order=created_at.desc&limit=300", jwt=u.get("jwt"))
    if rows is None:
        rows = sorted((r for r in _db["runs"] if r.get("user_id") == u["id"]), key=lambda r: r["created_at"], reverse=True)
    seen, out = set(), []
    for r in rows:
        if r["conv_id"] not in seen:
            seen.add(r["conv_id"])
            out.append(dict(conv_id=r["conv_id"], title=r["title"], created_at=r["created_at"]))
    return out[:40]


def conversation(u, conv_id):
    rows = _remote("GET", "zen_runs", query=f"?conv_id=eq.{urllib.parse.quote(conv_id)}&order=created_at.asc", jwt=u.get("jwt"))
    if rows is None:
        rows = [r for r in _db["runs"] if r["conv_id"] == conv_id and r.get("user_id") == u["id"]]
    return [dict(request=r["request"], status=r["status"], result=r["result"]) for r in rows]


def audit(u, limit=60):
    rows = _remote("GET", "zen_audit", query=f"?order=created_at.desc&limit={limit}", jwt=u.get("jwt"))
    return rows if rows is not None else sorted((r for r in _db["audit"] if r.get("user_id") == u["id"]), key=lambda r: r["created_at"], reverse=True)[:limit]
