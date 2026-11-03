"""stdlib server: python3 server.py -> http://localhost:8000"""
import json, os, pickle
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.parse
from zen import agent, approvals, llm, store
from zen.policy import RULES
from zen.tools import TOOLS, World

STATE = ".state.pkl"  # world + approvals survive restarts, so open approval buttons stay valid
W = World()
RUNS = []
if os.path.exists(STATE):
    try:
        W, _q, RUNS = pickle.load(open(STATE, "rb"))
        approvals.QUEUE.update(_q)
    except Exception:
        W, RUNS = World(), []


def save():
    pickle.dump((W, approvals.QUEUE, RUNS), open(STATE, "wb"))


def log_steps(conv, r, skip_first=False):
    """Policy blocks, approval requests and executed irreversible actions go to the audit log."""
    for s in r["trace"][1 if skip_first else 0:]:
        v, c = s["verdict"], s["call"]
        if v == "deny":
            store.log_audit("blocked", conv, c["name"], c["args"], s["rule"], s["reason"])
        elif v == "approve":
            store.log_audit("needs_approval", conv, c["name"], c["args"], s["rule"], s["reason"], token=s.get("token"))
        elif TOOLS.get(c["name"], {}).get("effect"):
            store.log_audit("allowed", conv, c["name"], c["args"])


def api(path, body):
    global W
    if path == "/api/run":
        conv = body.get("conv_id") or "default"
        r = agent.run(body["request"], W, body.get("policy", True), history=body.get("history", [])[-12:])
        RUNS.append(r)
        if r.get("token") in approvals.QUEUE:
            approvals.QUEUE[r["token"]]["conv"] = conv
        store.log_run(conv, (body.get("title") or body["request"])[:60], r)
        log_steps(conv, r)
        return r
    if path == "/api/approve":
        if body["token"] not in approvals.QUEUE:
            raise ValueError("This approval is no longer valid (server restarted or backends reset)")
        run = agent.resume(body["token"], body["approve"], W)
        RUNS.append(run)
        rec, note = approvals.QUEUE[body["token"]], str(body.get("note", ""))[:300]
        rec["note"] = note
        conv = rec.get("conv")
        store.log_audit("human_approved" if body["approve"] else "human_rejected", conv, rec["call"]["name"], rec["call"]["args"], rec["rule"], rec["reason"], note, body["token"])
        store.set_decision(body["token"], rec["status"])
        if run.get("token") in approvals.QUEUE:
            approvals.QUEUE[run["token"]]["conv"] = conv
        log_steps(conv, run, skip_first=True)
        return {"status": rec["status"], "run": run}
    if path == "/api/down":
        llm.DOWN = body["down"]
        return {"down": llm.DOWN}
    if path == "/api/reset":
        W = World()
        RUNS.clear()
        approvals.QUEUE.clear()
        return {}
    if path == "/api/policies":
        return [dict(id=i, text=e, tool=t, verdict=v) for i, e, t, v, _ in RULES]
    if path == "/api/conversations":
        return store.conversations()
    if path.startswith("/api/conversation?"):
        runs = store.conversation(urllib.parse.parse_qs(urllib.parse.urlparse(path).query)["id"][0])
        for r in runs:  # an approval button is only live if the server still knows the token
            tok = r["result"].get("token")
            if r["status"] == "pending_approval" and tok not in approvals.QUEUE:
                r["status"] = "expired"
        return runs
    if path == "/api/audit":
        return store.audit()
    if path == "/api/state":
        return dict(down=llm.DOWN, storage=dict(supabase=store.configured(), error=store.STATUS["error"]), provider=llm.PROVIDER, runs=RUNS[-10:], approvals=approvals.audit(),
                    world=dict(claims=W.claims, payments=W.payments, bookings=W.bookings, form=W.form, docs=W.docs, effects=W.effects),
                    eval=next((json.load(open(f)) for f in ("eval_results.json", "eval_results.groq.json") if os.path.exists(f)), None))


class H(BaseHTTPRequestHandler):
    def _send(self, code, data, ctype="application/json"):
        b = data if isinstance(data, bytes) else json.dumps(data, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/api/state", "/api/policies", "/api/conversations", "/api/audit") or self.path.startswith("/api/conversation?"):
            return self._send(200, api(self.path, {}))
        page = "dashboard.html" if self.path.startswith("/dashboard") else "chat.html"
        self._send(200, open(page, "rb").read(), "text/html")

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            out = api(self.path, body)
            save()
            self._send(200, out)
        except Exception as e:
            self._send(400, {"error": str(e)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Zen on http://localhost:8000 | llm:", llm.PROVIDER)
    ThreadingHTTPServer(("", 8000), H).serve_forever()
