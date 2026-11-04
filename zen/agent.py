"""Agent loop. policy=False is the baseline: same model, same tools, nothing between them."""
import time
from . import llm, policy, approvals
from .tools import TOOLS

MAX_STEPS = 8


def execute(world, call, approved):
    spec = TOOLS[call["name"]]
    try:
        out = spec["fn"](world, **call["args"])
    except TypeError as e:
        return {"error": f"invalid args: {e}"}
    if spec["effect"]:
        world.effects.append(dict(tool=call["name"], args=call["args"], approved=approved))
    return out


def run(request, world, policy_on=True, approver=None, history=(), engine="cloud"):
    """approver(token)->True/False resolves approvals inline (evals); None pauses the run for a human."""
    past = [{"role": h["role"], **({"content": h["content"]} if h["role"] == "user" else {"text": h["content"]})}
            for h in history if h.get("role") in ("user", "assistant") and h.get("content")]
    # policy grounding checks (vendor, amount, recipient) look at everything the user said in this conversation
    world.request = "\n".join([m["content"] for m in past if m["role"] == "user"] + [request])
    res = dict(request=request, policy=policy_on, trace=[], status="done", mode="normal", engine=engine)
    return _drive(res, past + [{"role": "user", "content": request}], world, policy_on, approver, [], time.time())


def _drive(res, msgs, world, policy_on, approver, queue, t0, last=False):
    trace = res["trace"]
    try:
        for _ in range(MAX_STEPS):
            if not queue and last:  # after a human decision, no extra model call just to word a reply
                break
            if not queue:
                out = llm.call_llm(msgs, TOOLS, res.get("engine", "cloud"))
                calls = out["calls"]
                if not calls:
                    res["message"] = out.get("text") or ""
                    break
                msgs.append({"role": "assistant", "calls": calls})
                queue = list(calls)
            while queue:
                c = queue.pop(0)
                d = policy.decide(c["name"], c["args"], world) if policy_on else policy.Decision("allow")
                step = dict(call=c, verdict=d.verdict, rule=d.rule, reason=d.reason)
                trace.append(step)
                if d.verdict == "deny":
                    out = {"error": f"blocked by policy {d.rule}: {d.reason}"}
                elif d.verdict == "approve":
                    tok = approvals.request(c, world, d.rule, d.reason)
                    step["token"] = tok
                    ok = approver(tok) if approver else None
                    if ok is None:  # pause; resume() continues from this saved state
                        approvals.QUEUE[tok]["ctx"] = dict(msgs=msgs, queue=queue, policy_on=policy_on, request=res["request"], engine=res.get("engine", "cloud"))
                        res.update(status="pending_approval", token=tok)
                        return _done(res, t0)
                    approvals.decide(tok, ok, by="auto-approver")
                    out = execute(world, c, True) if ok else {"error": "rejected by human"}
                else:
                    out = execute(world, c, False)
                step["result"] = out
                msgs.append({"role": "tool", "name": c["name"], "content": out})
    except llm.LLMDown as e:
        res["error"] = str(e)
        return _done(_safe_mode(res["request"], world, res), t0)
    return _done(res, t0)


def resume(token, ok, world):
    """Human decided. Run the approved action (or report the rejection), then let the agent carry on."""
    rec = approvals.decide(token, ok)
    c = rec["call"]
    out = execute(world, c, True) if ok else {"error": "rejected by human"}
    step = dict(call=c, verdict="allow" if ok else "deny", rule=rec["rule"], reason="Approved by human" if ok else "Rejected by human", result=out)
    ctx = rec.get("ctx")
    res = dict(request=rec["ctx"]["request"] if ctx else "", policy=True, trace=[step], status="done", mode="normal", engine=ctx["engine"] if ctx else "cloud")
    if not ctx:  # safe-mode draft: nothing to continue
        return res | dict(latency=0)
    ctx["msgs"].append({"role": "tool", "name": c["name"], "content": out})
    return _drive(res, ctx["msgs"], world, ctx["policy_on"], None, ctx["queue"], time.time(), last=True)


def _safe_mode(request, world, res):
    """Model down: extract the single final action (small local model, else heuristic parser) and send it
    to a human as a draft. Nothing runs autonomously, and the policy engine still vets the draft."""
    res["mode"] = "safe"
    fields = llm.extract_json(f'Return JSON {{"tool": one of {list(TOOLS)}, "args": {{...}}}} for the final action of: {request}')
    if not (fields and fields.get("tool") in TOOLS and isinstance(fields.get("args"), dict)):
        steps = [s for s in llm.plan(request) if TOOLS[s[0]]["effect"]]  # heuristic extractor
        if not steps:
            res["message"] = "The AI model is unavailable and I could not read this as an expense claim, a booking or an application. Try again in a minute, or write it like: Claim Rs 500 for lunch at Haldirams on 2026-03-02"
            return res
        fields = {"tool": steps[-1][0], "args": steps[-1][1]}
    c = {"name": fields["tool"], "args": fields["args"]}
    d = policy.decide(c["name"], c["args"], world)
    res["trace"].append(dict(call=c, verdict=d.verdict, rule=d.rule, reason=d.reason, safe_mode=True))
    if d.verdict == "deny":
        res["status"] = "blocked"
    else:
        res.update(status="pending_approval", token=approvals.request(c, world, d.rule or "SAFE", d.reason or "safe mode: model down", draft=c))
    return res


def _done(res, t0):
    res["latency"] = round(time.time() - t0, 3)
    return res
