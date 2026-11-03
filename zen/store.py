"""Audit log + conversation memory. Every write goes to a local file; when SUPABASE_URL and SUPABASE_KEY are set it is also
mirrored to Supabase (PostgREST), and reads then come from Supabase. A remote failure never breaks the app."""
import json, os, queue, threading, time, urllib.parse, urllib.request, uuid

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


def _remote(method, table, body=None, query=""):
    if not configured():
        return None
    key = os.environ["SUPABASE_KEY"]
    req = urllib.request.Request(f'{os.environ["SUPABASE_URL"]}/rest/v1/{table}{query}', json.dumps(body).encode() if body is not None else None,
                                 method=method, headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"})
    try:
        raw = urllib.request.urlopen(req, timeout=10).read()
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


def _mirror(*a, **k):  # one ordered worker: the UI never waits on the network, and a status update never overtakes its insert
    if configured():
        _q.put((a, k))


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S%z") or time.strftime("%Y-%m-%dT%H:%M:%S")


def log_run(conv_id, title, run):
    row = dict(id=str(uuid.uuid4()), conv_id=conv_id, title=title, request=run["request"], status=run["status"], mode=run.get("mode"),
               token=run.get("token"), result=run, created_at=_now())
    _db["runs"].append(row)
    _save()
    _mirror("POST", "zen_runs", row)


def log_audit(kind, conv_id, tool, args, rule="", rule_text="", note="", token=None):
    row = dict(id=str(uuid.uuid4()), conv_id=conv_id, kind=kind, tool=tool, args=args, rule=rule, rule_text=rule_text, note=note, token=token, created_at=_now())
    _db["audit"].append(row)
    _save()
    _mirror("POST", "zen_audit", row)


def set_decision(token, status):
    for r in _db["runs"]:
        if r.get("token") == token:
            r["status"] = status
    _save()
    _mirror("PATCH", "zen_runs", {"status": status}, f"?token=eq.{urllib.parse.quote(token)}")


def conversations():
    rows = _remote("GET", "zen_runs", query="?select=conv_id,title,created_at&order=created_at.desc&limit=300")
    if rows is None:
        rows = sorted(_db["runs"], key=lambda r: r["created_at"], reverse=True)
    seen, out = set(), []
    for r in rows:
        if r["conv_id"] not in seen:
            seen.add(r["conv_id"])
            out.append(dict(conv_id=r["conv_id"], title=r["title"], created_at=r["created_at"]))
    return out[:40]


def conversation(conv_id):
    rows = _remote("GET", "zen_runs", query=f"?conv_id=eq.{urllib.parse.quote(conv_id)}&order=created_at.asc")
    if rows is None:
        rows = [r for r in _db["runs"] if r["conv_id"] == conv_id]
    return [dict(request=r["request"], status=r["status"], result=r["result"]) for r in rows]


def audit(limit=60):
    rows = _remote("GET", "zen_audit", query=f"?order=created_at.desc&limit={limit}")
    return rows if rows is not None else sorted(_db["audit"], key=lambda r: r["created_at"], reverse=True)[:limit]
