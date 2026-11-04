"""stdlib server: python3 server.py -> http://localhost:8000"""
import base64, json, os, pickle, re, sys, time, urllib.error, urllib.parse, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from zen import agent, approvals, batch, llm, net, payments, records, store
from zen.policy import RULES
from zen.tools import TOOLS, World

PORT = int(os.environ.get("PORT", 8000))  # hosts such as Render and App Runner set PORT
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


def _jwt_exp(tok):
    try:
        return json.loads(base64.urlsafe_b64decode(tok.split(".")[1] + "==")).get("exp", 0)
    except Exception:
        return 0


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
        if hit and _jwt_exp(tok) > time.time():  # Supabase unreachable: keep a session we already verified until its token expires
            return hit[1]
        raise ConnectionError(f"Could not reach Supabase to check your session: {e}")
    _users[tok] = (time.time() + 300, u)
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


def policy_impact(u, me):
    """How often each rule has fired: in the 30 test cases, in the latest batch run, and in this user's own audit log."""
    def fires(d):
        return dict(blocked=d.get("deny", 0), asked=d.get("approve", 0))
    evals = {}
    ev = next((json.load(open(f)) for f in ("eval_results.json", "eval_results.groq.json") if os.path.exists(f)), None)
    for row in (ev or {}).get("rows", []):
        if row["policy"]:
            for s in row["trace"]:
                if s.get("rule") and s["verdict"] in ("deny", "approve"):
                    evals.setdefault(s["rule"], {}).setdefault(s["verdict"], 0)
                    evals[s["rule"]][s["verdict"]] += 1
    mine = {}
    for a in store.audit(u, 500):
        if a.get("rule"):
            k = dict(blocked="blocked", needs_approval="asked", human_approved="approved", human_rejected="rejected", ai_approved="approved", ai_rejected="rejected").get(a["kind"])
            if k:
                mine.setdefault(a["rule"], dict(blocked=0, asked=0, approved=0, rejected=0))[k] += 1
    rules = [dict(id=i, text=t, verdict=v) for i, t, _, v, _ in RULES] + [dict(id="G2", text="Calls with the wrong arguments are denied", verdict="deny")]
    for r in rules:
        r["tests"], r["batch"] = fires(evals.get(r["id"], {})), fires(me.get("batch_rules", {}).get(r["id"], {}))
        r["chats"] = mine.get(r["id"], dict(blocked=0, asked=0, approved=0, rejected=0))
    return dict(rules=rules, has_batch=bool(me.get("batch_rules")), has_tests=bool(ev))


def api(path, body, u):
    me = S.setdefault(u["id"], dict(W=World(), RUNS=[]))
    W, RUNS = me["W"], me["RUNS"]
    W.owner = u["id"]  # executed claims and payments are recorded under this user
    mine = lambda: {t: q for t, q in approvals.QUEUE.items() if q.get("uid") == u["id"]}
    if path == "/api/run":
        conv = body.get("conv_id") or "default"
        r = agent.run(body["request"], W, body.get("policy", True), history=body.get("history", [])[-12:], engine=body.get("engine") if body.get("engine") in ("device", "gemini", "groq") else "cloud")
        RUNS.append(r)
        if r.get("token") in approvals.QUEUE:
            approvals.QUEUE[r["token"]].update(conv=conv, uid=u["id"])
        store.log_run(u, conv, (body.get("title") or body["request"])[:60], r)
        log_steps(u, conv, r)
        return r
    if path == "/api/approve":
        if body["token"] not in mine():
            raise ValueError("This approval is no longer valid (server restarted or backends reset)")
        by = "ai" if body.get("by") == "ai" else "human"  # Ask AI can decide for the person
        run = agent.resume(body["token"], body["approve"], W, by)
        RUNS.append(run)
        rec, note = approvals.QUEUE[body["token"]], str(body.get("note", ""))[:300]
        rec["note"] = note
        conv = rec.get("conv")
        store.log_audit(u, f"{by}_approved" if body["approve"] else f"{by}_rejected", conv, rec["call"]["name"], rec["call"]["args"], rec["rule"], rec["reason"], note, body["token"])
        store.set_decision(u, body["token"], rec["status"])
        if run.get("token") in approvals.QUEUE:
            approvals.QUEUE[run["token"]].update(conv=conv, uid=u["id"])
        log_steps(u, conv, run, skip_first=True)
        return {"status": rec["status"], "run": run}
    if path == "/api/advise":
        prompt = (f"Action: {str(body.get('tool', ''))[:60]} {json.dumps(body.get('args', {}))[:400]}\nRequest: {str(body.get('text', ''))[:300]}\n"
                  f"Rule that flagged it: {str(body.get('rule', ''))[:20]} {str(body.get('reason', ''))[:200]}\nShould the human approve or reject this?")
        try:
            text = llm.advise(prompt, body.get("engine", "cloud")) or "No answer came back."
            m = re.match(r"\W*(approve|reject|unsure)", text, re.I)
            return dict(advice=text, decision=m.group(1).lower() if m else "unsure")
        except llm.LLMDown as e:
            return dict(error="The AI could not answer: " + str(e)[:120])
    if path == "/api/records":
        return dict(enabled=records.enabled(u["id"]), table=records.TABLE, items=records.recent(u["id"]))
    if path == "/api/me":
        return dict(email=u["email"])
    if path == "/api/batch/decide":
        store.log_audit(u, ("ai" if body.get("by") == "ai" else "human") + ("_approved" if body.get("approve") else "_rejected"), "batch", str(body.get("tool", "")), {"id": body.get("id"), "text": str(body.get("text", ""))[:200]},
                        str(body.get("rule", "")), str(body.get("reason", "")), "batch run")
        if body.get("approve"):  # an approved batch scenario counts as executed, so it is recorded like a real claim, payment or booking
            kind = dict(submit_claim="claim", send_payment="payment", book="booking").get(str(body.get("tool", "")))
            if kind:
                records.save(u["id"], kind, dict(by="ai" if body.get("by") == "ai" else "human", batch=True, amount=body.get("amount"), summary="Approved: " + str(body.get("text", ""))[:160]))
        return {}
    if path == "/api/batch":
        out = batch.run(max(1, min(int(body.get("n", 2000)), 2000)), body.get("seed"))
        me["batch_rules"] = {}
        for x in out["rows"]:
            if x["rule"]:
                me["batch_rules"].setdefault(x["rule"], {}).setdefault(x["verdict"], 0)
                me["batch_rules"][x["rule"]][x["verdict"]] += 1
        return out
    if path == "/api/down":
        llm.DOWN = body["down"]
        return {"down": llm.DOWN}
    if path == "/api/reset":
        me.update(W=World(), RUNS=[])
        for t in mine():
            del approvals.QUEUE[t]
        return {}
    if path == "/api/policy-impact":
        return policy_impact(u, me)
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
        return store.audit(u, 300)
    if path == "/api/state":
        return dict(down=llm.DOWN, storage=dict(supabase=store.configured(), error=store.STATUS["error"]), backends=dict(dynamodb=records.enabled(u["id"]), dynamodb_error=records.STATUS["error"], payments=payments.mode()), provider=llm.PROVIDER, cloud_model={"gemini": llm.MODEL, "groq": llm.GROQ_MODEL}.get(llm.PROVIDER, "offline demo model"), cloud=dict(gemini=dict(model=llm.MODEL, ready=bool(os.environ.get("GEMINI_API_KEY"))), groq=dict(model=llm.GROQ_MODEL, ready=bool(os.environ.get("GROQ_API_KEY")))), device=llm.device_status(), runs=RUNS[-10:], user=dict(email=u["email"]), approvals=[{k: v for k, v in q.items() if k not in ("world", "ctx", "uid")} for q in mine().values()],
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
        if self.path in ("/auth.js", "/theme.css", "/theme.js", "/batchrun.js"):
            return self._send(200, open(self.path[1:], "rb").read(), "text/css" if self.path.endswith("css") else "text/javascript")
        if self.path.split("?")[0] == "/batch":  # the batch run now lives on the dashboard
            self.send_response(302); self.send_header("Location", "/dashboard"); self.end_headers(); return
        page = {"/app": "chat.html", "/dashboard": "dashboard.html", "/policies": "policies.html"}.get(self.path.split("?")[0], "landing.html")
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
    print(f"Zen on http://localhost:{PORT} | llm:", llm.PROVIDER)
    ThreadingHTTPServer(("", PORT), H).serve_forever()
