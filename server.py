"""stdlib server: python3 server.py -> http://localhost:8000"""
import base64, json, os, pickle, sys, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zen import agent, approvals, batch, llm, net, store
from zen.policy import RULES
from zen.tools import TOOLS, World

STATE = ".state.pkl"  # worlds + approvals survive restarts, so open approval buttons stay valid
S = {}  # user id -> dict(W=World, RUNS=[...]); every signed-in user gets their own fake backends
if os.path.exists(STATE):
    try:
        S, _q = pickle.load(open(STATE, "rb"))
        approvals.QUEUE.update(_q)
    except Exception:
        S = {}


def save():
    pickle.dump((S, approvals.QUEUE), open(STATE, "wb"))


def public_config():
    """Only the anon key may leave the server; a service key in .env must never reach a browser."""
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY", "")
    try:
        role = json.loads(base64.urlsafe_b64decode(key.split(".")[1] + "==")).get("role")
    except Exception:
        role = "anon" if key.startswith("sb_publishable_") else None
    return dict(auth=True, url=url, key=key) if url and role == "anon" else dict(auth=False)


_users = {}  # token -> (expiry, user); Supabase is asked at most once a minute per token


def user_of(headers):
    """The signed-in user, verified by Supabase Auth. With no Supabase configured the app runs open as a single local user."""
    if not store.configured():
        return dict(id="local", email="local mode", jwt=None)
    tok = headers.get("Authorization", "")[7:]
    if not tok:
        return None
    hit = _users.get(tok)
    if hit and hit[0] > time.time():
        return hit[1]
    try:
        req = urllib.request.Request(os.environ["SUPABASE_URL"] + "/auth/v1/user", headers={"apikey": os.environ["SUPABASE_KEY"], "Authorization": "Bearer " + tok})
        d = json.loads(net.urlopen(req, timeout=10).read())
        u = dict(id=d["id"], email=d.get("email", ""), jwt=tok)
    except urllib.error.HTTPError as e:
        print(f"session rejected by Supabase: HTTP {e.code} {e.read()[:160]!r}", file=sys.stderr, flush=True)
        return None
    except Exception as e:
        raise ConnectionError(f"Could not reach Supabase to check your session: {e}")
    _users[tok] = (time.time() + 60, u)
    return u


def log_steps(u, conv, r, skip_first=False):
    """Policy blocks, approval requests and executed irreversible actions go to the audit log."""
    for s in r["trace"][1 if skip_first else 0:]:
        v, c = s["verdict"], s["call"]
        if v == "deny":
            store.log_audit(u, "blocked", conv, c["name"], c["args"], s["rule"], s["reason"])
        elif v == "approve":
            store.log_audit(u, "needs_approval", conv, c["name"], c["args"], s["rule"], s["reason"], token=s.get("token"))
        elif TOOLS.get(c["name"], {}).get("effect"):
            store.log_audit(u, "allowed", conv, c["name"], c["args"])


def api(path, body, u):
    me = S.setdefault(u["id"], dict(W=World(), RUNS=[]))
    W, RUNS = me["W"], me["RUNS"]
    mine = lambda: {t: q for t, q in approvals.QUEUE.items() if q.get("uid") == u["id"]}
    if path == "/api/run":
        conv = body.get("conv_id") or "default"
        r = agent.run(body["request"], W, body.get("policy", True), history=body.get("history", [])[-12:], engine="device" if body.get("engine") == "device" else "cloud")
        RUNS.append(r)
        if r.get("token") in approvals.QUEUE:
            approvals.QUEUE[r["token"]].update(conv=conv, uid=u["id"])
        store.log_run(u, conv, (body.get("title") or body["request"])[:60], r)
        log_steps(u, conv, r)
        return r
    if path == "/api/approve":
        if body["token"] not in mine():
            raise ValueError("This approval is no longer valid (server restarted or backends reset)")
        run = agent.resume(body["token"], body["approve"], W)
        RUNS.append(run)
        rec, note = approvals.QUEUE[body["token"]], str(body.get("note", ""))[:300]
        rec["note"] = note
        conv = rec.get("conv")
        store.log_audit(u, "human_approved" if body["approve"] else "human_rejected", conv, rec["call"]["name"], rec["call"]["args"], rec["rule"], rec["reason"], note, body["token"])
        store.set_decision(u, body["token"], rec["status"])
        if run.get("token") in approvals.QUEUE:
            approvals.QUEUE[run["token"]].update(conv=conv, uid=u["id"])
        log_steps(u, conv, run, skip_first=True)
        return {"status": rec["status"], "run": run}
    if path == "/api/me":
        return dict(email=u["email"])
    if path == "/api/batch":
        return batch.run(max(1, min(int(body.get("n", 500)), 1000)), body.get("seed"))
    if path == "/api/down":
        llm.DOWN = body["down"]
        return {"down": llm.DOWN}
    if path == "/api/reset":
        me.update(W=World(), RUNS=[])
        for t in mine():
            del approvals.QUEUE[t]
        return {}
    if path == "/api/policies":
        return [dict(id=i, text=e, tool=t, verdict=v) for i, e, t, v, _ in RULES]
    if path == "/api/conversations":
        return store.conversations(u)
    if path.startswith("/api/conversation?"):
        runs = store.conversation(u, urllib.parse.parse_qs(urllib.parse.urlparse(path).query)["id"][0])
        for r in runs:  # an approval button is only live if the server still knows the token
            tok = r["result"].get("token")
            if r["status"] == "pending_approval" and tok not in mine():
                r["status"] = "expired"
        return runs
    if path == "/api/audit":
        return store.audit(u)
    if path == "/api/state":
        return dict(down=llm.DOWN, storage=dict(supabase=store.configured(), error=store.STATUS["error"]), provider=llm.PROVIDER, cloud_model={"gemini": llm.MODEL, "groq": llm.GROQ_MODEL}.get(llm.PROVIDER, "offline demo model"), device=llm.device_status(), runs=RUNS[-10:], user=dict(email=u["email"]), approvals=[{k: v for k, v in q.items() if k not in ("world", "ctx", "uid")} for q in mine().values()],
                    world=dict(claims=W.claims, payments=W.payments, bookings=W.bookings, form=W.form, docs=W.docs, effects=W.effects),
                    eval=next((json.load(open(f)) for f in ("eval_results.json", "eval_results.groq.json") if os.path.exists(f)), None))


class H(BaseHTTPRequestHandler):
    def _send(self, code, data, ctype="application/json"):
        b = data if isinstance(data, bytes) else json.dumps(data, default=str).encode()
        self.send_response(code); self.send_header("Content-Type", ctype); self.end_headers(); self.wfile.write(b)

    def do_GET(self):
        if self.path == "/api/config":
            return self._send(200, public_config())
        if self.path.startswith("/api/"):
            try:
                u = user_of(self.headers)
            except ConnectionError as e:
                return self._send(503, {"error": str(e)})
            return self._send(200, api(self.path, {}, u)) if u else self._send(401, {"error": "Sign in required"})
        if self.path in ("/auth.js", "/theme.css", "/theme.js"):
            return self._send(200, open(self.path[1:], "rb").read(), "text/css" if self.path.endswith("css") else "text/javascript")
        page = {"/app": "chat.html", "/dashboard": "dashboard.html", "/batch": "batch.html"}.get(self.path.split("?")[0], "landing.html")
        self._send(200, open(page, "rb").read(), "text/html")

    def do_POST(self):
        try:
            u = user_of(self.headers)
        except ConnectionError as e:
            return self._send(503, {"error": str(e)})
        if not u:
            return self._send(401, {"error": "Sign in required"})
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        try:
            out = api(self.path, body, u)
            save()
            self._send(200, out)
        except Exception as e:
            self._send(400, {"error": str(e)})

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    print("Zen on http://localhost:8000 | llm:", llm.PROVIDER)
    ThreadingHTTPServer(("", 8000), H).serve_forever()
