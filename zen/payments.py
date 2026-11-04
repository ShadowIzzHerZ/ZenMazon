"""Optional payment sandbox: with Razorpay TEST keys set, an approved payment also creates an order in the Razorpay test dashboard.
No money moves in test mode. Live keys are refused on purpose. Without keys the payment stays simulated."""
import base64, json, os, urllib.request, uuid
from . import net


def mode():
    k = os.environ.get("RAZORPAY_KEY_ID", "")
    return "razorpay-test" if k.startswith("rzp_test_") and os.environ.get("RAZORPAY_KEY_SECRET") else "simulated"


def pay(recipient, amount, reason):
    """Returns {"provider", "id"} on success, {"provider", "error"} on failure, None when no sandbox is configured."""
    if os.environ.get("RAZORPAY_KEY_ID", "").startswith("rzp_live_"):
        return dict(provider="razorpay", error="live keys are refused, use rzp_test_ keys")
    if mode() != "razorpay-test":
        return None
    auth = base64.b64encode(f'{os.environ["RAZORPAY_KEY_ID"]}:{os.environ["RAZORPAY_KEY_SECRET"]}'.encode()).decode()
    body = json.dumps({"amount": int(round(float(amount) * 100)), "currency": "INR", "receipt": "zen-" + uuid.uuid4().hex[:8],
                       "notes": {"recipient": str(recipient)[:80], "reason": str(reason)[:80]}}).encode()
    req = urllib.request.Request("https://api.razorpay.com/v1/orders", body, {"Content-Type": "application/json", "Authorization": "Basic " + auth})
    try:
        return dict(provider="razorpay-test", id=json.load(net.urlopen(req, timeout=15))["id"])
    except Exception as e:
        return dict(provider="razorpay-test", error=str(getattr(e, "read", lambda: e)())[:160] if hasattr(e, "read") else str(e)[:160])
