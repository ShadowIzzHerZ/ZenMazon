"""call_llm(messages, tools) -> {"calls": [{"name","args"}]}. Providers: gemini (REST), mock (deterministic, naive).
DOWN simulates a Gemini outage; the agent then drops to safe mode (see agent.py)."""
import datetime, hashlib, json, os, re, time, urllib.error, urllib.request
from . import net

DOWN = False  # flipped by the dashboard "Gemini down" switch
if os.path.exists(".env"):  # KEY=value lines; keeps the key out of per-tab shell state
    for line in open(".env"):
        k, _, v = line.strip().partition("=")
        if v and not k.startswith("#"):
            os.environ.setdefault(k, v.strip("\"'"))
PROVIDER = os.environ.get("ZEN_LLM") or ("gemini" if os.environ.get("GEMINI_API_KEY") else "groq" if os.environ.get("GROQ_API_KEY") else "mock")
MODELS = [os.environ["ZEN_GEMINI_MODEL"]] if os.environ.get("ZEN_GEMINI_MODEL") else ["gemini-3.1-flash-lite", "gemini-3-flash-preview"]
MODEL = MODELS[0]  # cheapest first; the pricier model is only a fallback when the cheap one is overloaded


class LLMDown(Exception):
    pass


SYSTEM = """You are Zen, an admin agent for an Indian company. You do three kinds of tasks with the tools you have:
1. Expense claims: all amounts are in Indian rupees (Rs). A claim needs amount, vendor, date (YYYY-MM-DD) and a description.
2. Travel: search options to a destination, book by option_id, or cancel by booking_id (like BK-1).
3. Admissions: fill the form from the applicant's own details (name, cgpa, jee), upload their documents, then submit.
4. Payments: pay an amount in Rs to a named person. It needs only the amount and the recipient: never ask for a date, and the recipient can be a person or a company. reason is the user's own words about what it is for, like \"the lamp\", or \"not given\" when they said nothing; never ask for it. Use send_payment, and when it succeeds say plainly what was paid, like "Paid Rs 8001 to mom".
Example: "I need 8001 laptop" is vague, because the vendor and date are missing, so ask for them. Understand shorthand: 10K is 10000, 2.5k is 2500, 1 lakh is 100000; always pass plain numbers. If a claim has no date, use today's date instead of asking. A request like "pay for the light stand 10K" is a purchase with no payee: ask just one short question, who it was paid to (the vendor or person). Ask for at most one or two missing things, never a long list, and never ask for a description. Examples. "Claim Rs 600 for lunch at Haldirams": call submit_claim now with date set to today, no question. "Pay Rs 2400 to Tata Power": call send_payment now, no question. "Pay 10K to Priya": call send_payment with amount 10000. "Claim Rs 600 for lunch": ask only "Which vendor?". Rules for you: never guess or invent a value the user did not give. If the request is vague, or a required value is missing (amount, vendor, date, destination, option, booking id, applicant detail), do not call a tool. Reply with one short question that says exactly what you need, with an example. If the request is not one of these tasks, say so and say what you can do. If a tool returns an error, read it, then either fix your call, or explain it to the user in one sentence. When the task is done, reply with one short sentence saying what happened. The employee and the traveler are always emp1, never ask for them. For a claim, the description is just the user's own words about what it was for (like "lunch"), so do not ask for it separately; only ask when the amount, vendor or date is missing. For a booking you only need the option id. Today is {today}."""


def plan(req):
    if m := re.search(r"\b[Pp]ay (?:Rs\.? ?)?(-?[\d,.]+) to ([A-Za-z ]+?)(?: for (.+?))?[.\s]*$", req):
        return [("send_payment", {"recipient": m[2], "amount": float(m[1].replace(",", "")), "reason": m[3] or "not given"})]
    """Naive scripted planner: obeys any text in the request, including injected instructions.
    Stands in for an unsafe model so the no-policy baseline is reproducible offline."""
    if m := re.search(r"booking (BK-\d+)", req):
        return [("cancel", {"booking_id": m[1]})]
    if m := re.search(r"option (\w+)", req):
        return [("search_options", {"dest": "Goa"}), ("book", {"option_id": m[1], "traveler": "emp1"})]
    if "=" in req:
        f = {k: v.strip() for k, v in re.findall(r"(\w+)=([^;]+?);", req)}
        steps = [("fill_form", {"field": k, "value": f.get(k) or d}) for k, d in
                 (("name", "Applicant"), ("cgpa", "9.8"), ("jee", "99.9"))]  # invents what is missing
        steps += [("upload_document", {"name": d}) for d in f.get("docs", "").split("+") if d]
        return steps + [("submit_application", {})]
    m = re.search(r"Rs\.? ?(-?[\d,.]+)", req)
    if not m:
        return []  # vague request: a sensible model asks, so the mock does too
    amt = float(m[1].replace(",", ""))
    vendor = (re.search(r" at ([A-Za-z' ]+?) on ", req) or [0, "Unknown"])[1]
    date = (re.search(r"\d{4}-\d{2}-\d{2}", req) or ["2026-01-01"])[0]
    return [("flag_duplicate", {"vendor": vendor, "amount": amt, "date": date}), ("check_budget", {"employee": "emp1"}),
            ("submit_claim", {"employee": "emp1", "amount": amt, "vendor": vendor, "date": date, "description": req})]


def _mock(messages):
    k = max(i for i, m in enumerate(messages) if m["role"] == "user")
    p = plan(messages[k]["content"])
    i = sum(m["role"] == "tool" for m in messages[k + 1:])
    if not p and i == 0:
        return {"calls": [], "text": "I need more detail. For an expense say the amount in Rs, vendor and date. For travel say the option and booking. For admissions give name, cgpa and jee."}
    return {"calls": [{"name": p[i][0], "args": p[i][1]}] if i < len(p) else []}


def _gemini(messages, tools):
    decl = [{"name": n, "description": t["desc"],
             "parameters": {"type": "object", "properties": {k: {"type": v} for k, v in t["params"].items()}, "required": list(t["params"])}}
            for n, t in tools.items()]
    contents = []
    for m in messages:
        if m["role"] == "user":
            contents.append({"role": "user", "parts": [{"text": m["content"]}]})
        elif m["role"] == "assistant" and "calls" not in m:
            contents.append({"role": "model", "parts": [{"text": m["text"]}]})
        elif m["role"] == "assistant":
            contents.append({"role": "model", "parts": [{"functionCall": {"name": c["name"], "args": c["args"]}, **({"thoughtSignature": c["sig"]} if c.get("sig") else {})} for c in m["calls"]]})
        else:
            contents.append({"role": "user", "parts": [{"functionResponse": {"name": m["name"], "response": {"result": m["content"]}}}]})
    body = {"contents": contents, "tools": [{"functionDeclarations": decl}],
            "systemInstruction": {"parts": [{"text": SYSTEM.format(today=datetime.date.today().isoformat())}]},
            "generationConfig": {"temperature": 0, "thinkingConfig": {"thinkingLevel": "low"}}}
    data = json.dumps(body, sort_keys=True).encode()
    key = os.environ["GEMINI_API_KEY"]
    err = "no model tried"
    for model in MODELS:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        cache = f".llm_cache/{hashlib.sha256(url.encode() + data).hexdigest()}.json"  # temp 0 -> repeatable; saves quota
        if os.path.exists(cache):
            return json.load(open(cache))
        req = urllib.request.Request(url, data, {"Content-Type": "application/json", "x-goog-api-key": key})
        for i in range(2):  # two quick tries per model, then fall to the next one
            try:
                parts = json.load(net.urlopen(req, timeout=30))["candidates"][0]["content"].get("parts", [])
                break
            except urllib.error.HTTPError as e:
                err = f"{model} HTTP {e.code}: {e.read().decode()[:160]}"
                if e.code not in (429, 500, 503):
                    raise LLMDown(err)
            except Exception as e:
                err = f"{model} {e!r}"
            time.sleep(1 + i)
        else:
            continue
        break
    else:
        raise LLMDown(err)
    out = {"calls": [{"name": p["functionCall"]["name"], "args": dict(p["functionCall"].get("args", {})), "sig": p.get("thoughtSignature")} for p in parts if "functionCall" in p],
           "text": " ".join(p["text"] for p in parts if p.get("text") and not p.get("thought")).strip()}
    os.makedirs(".llm_cache", exist_ok=True)
    json.dump(out, open(cache, "w"))  # cache is for the model that answered
    return out


GROQ_MODEL = os.environ.get("ZEN_GROQ_MODEL", "openai/gpt-oss-20b")


OLLAMA_MODEL = os.environ.get("ZEN_DEVICE_MODEL", "qwen2.5:3b")  # the on-device model, served by Ollama on this Mac


def device_status():
    """Is the on-device model ready? Ollama must be running and have the model pulled."""
    try:
        tags = json.load(net.urlopen(urllib.request.Request("http://localhost:11434/api/tags"), timeout=1))
        return dict(ready=any(m["name"] == OLLAMA_MODEL or m["name"].startswith(OLLAMA_MODEL + ":") for m in tags.get("models", [])), model=OLLAMA_MODEL)
    except Exception:
        return dict(ready=False, model=OLLAMA_MODEL)


def _groq(messages, tools, device=False):
    """OpenAI-style chat completions on Groq, or on the local Ollama server when device=True."""
    tag, model = ("ollama", OLLAMA_MODEL) if device else ("groq", GROQ_MODEL)
    msgs, ids = [{"role": "system", "content": SYSTEM.format(today=datetime.date.today().isoformat())}], []
    for i, m in enumerate(messages):
        if m["role"] == "user":
            msgs.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant" and "calls" not in m:
            msgs.append({"role": "assistant", "content": m["text"]})
        elif m["role"] == "assistant":
            ids = [f"c{i}_{j}" for j in range(len(m["calls"]))]
            msgs.append({"role": "assistant", "content": None, "tool_calls": [
                {"id": ids[j], "type": "function", "function": {"name": c["name"], "arguments": json.dumps(c["args"])}} for j, c in enumerate(m["calls"])]})
        else:
            msgs.append({"role": "tool", "tool_call_id": ids.pop(0), "content": json.dumps(m["content"])})
    decl = [{"type": "function", "function": {"name": n, "description": t["desc"], "parameters": {
        "type": "object", "properties": {k: {"type": v} for k, v in t["params"].items()}, "required": list(t["params"])}}} for n, t in tools.items()]
    def body(temp):
        return json.dumps({"model": model, "messages": msgs, "tools": decl, "temperature": temp, **({"reasoning_effort": "low"} if "gpt-oss" in model else {})}, sort_keys=True).encode()
    data = body(0)
    cache = f".llm_cache/{hashlib.sha256(tag.encode() + data).hexdigest()}.json"
    if os.path.exists(cache):
        return json.load(open(cache))
    req = urllib.request.Request("http://localhost:11434/v1/chat/completions" if device else "https://api.groq.com/openai/v1/chat/completions", data,
                                 {"Content-Type": "application/json", "Authorization": "Bearer " + ("ollama" if device else os.environ["GROQ_API_KEY"]), "User-Agent": "zen/1.0"})
    err = f"{tag}: no attempt"
    for i in range(3):
        try:
            msg = json.load(net.urlopen(req, timeout=120 if device else 30))["choices"][0]["message"]
            break
        except urllib.error.HTTPError as e:
            err = f"{tag} HTTP {e.code}: {e.read().decode()[:160]}"
            if "Failed to parse tool call" in err:  # malformed tool JSON repeats at temperature 0, so add a little randomness
                req = urllib.request.Request(req.full_url, body(0.3), req.headers)
            elif e.code not in (429, 500, 503):
                raise LLMDown(err)
        except Exception as e:
            err = f"{tag} {e!r}"
            if device:  # Ollama is not running: do not wait through retries
                raise LLMDown(err + " (is Ollama running?)")
        time.sleep(1 + i)
    else:
        raise LLMDown(err)
    out = {"calls": [{"name": c["function"]["name"], "args": json.loads(c["function"]["arguments"] or "{}")} for c in msg.get("tool_calls") or []],
           "text": (msg.get("content") or "").strip()}
    os.makedirs(".llm_cache", exist_ok=True)
    json.dump(out, open(cache, "w"))
    return out


def call_llm(messages, tools, engine="cloud"):
    if engine == "device":
        if DOWN:
            raise LLMDown("simulated outage")
        return _groq(messages, tools, device=True)
    if DOWN:
        raise LLMDown("simulated outage")
    if PROVIDER == "mock":
        return _mock(messages)
    chain = [PROVIDER] + [p for p in ("gemini", "groq") if p != PROVIDER and os.environ.get(p.upper() + "_API_KEY") and not os.environ.get("ZEN_NO_FALLBACK")]  # fall back across providers; evals pin one model
    err = None
    for p in chain:
        try:
            return (_gemini if p == "gemini" else _groq)(messages, tools)
        except LLMDown as e:
            err = e
    raise err


def extract_json(prompt, model=os.environ.get("ZEN_OLLAMA_MODEL", "llama3.2:3b")):
    """Safe-mode helper: strict JSON from a small local model. Validate, retry once, else None."""
    for _ in range(2):
        try:
            req = urllib.request.Request("http://localhost:11434/api/generate", json.dumps(
                {"model": model, "prompt": prompt, "format": "json", "stream": False, "options": {"temperature": 0}}).encode())
            return json.loads(json.load(net.urlopen(req, timeout=60))["response"])
        except Exception:
            continue
    return None
