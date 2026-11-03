import json, os, urllib.request, urllib.error
k = os.environ["GEMINI_API_KEY"]
for m in ("gemini-3.1-flash-lite",):
    u = f"https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"
    r = urllib.request.Request(u, json.dumps({"contents": [{"role": "user", "parts": [{"text": "say hi"}]}]}).encode(),
                               {"Content-Type": "application/json", "x-goog-api-key": k})
    try:
        print(m, "OK", json.load(urllib.request.urlopen(r, timeout=30))["candidates"][0]["content"]["parts"][0]["text"][:40])
    except urllib.error.HTTPError as e:
        print(m, e.code, e.read().decode()[:300])
    except Exception as e:
        print(m, repr(e))
