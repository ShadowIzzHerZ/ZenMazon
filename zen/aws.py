"""Minimal signed DynamoDB client (AWS Signature V4) so the app stays dependency-free.
Credentials come from AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY (hosts) or the default profile in ~/.aws/credentials (this Mac)."""
import configparser, datetime, hashlib, hmac, json, os, urllib.request
from . import net


def creds():
    k, s, t = os.environ.get("AWS_ACCESS_KEY_ID"), os.environ.get("AWS_SECRET_ACCESS_KEY"), os.environ.get("AWS_SESSION_TOKEN")
    if k and s:
        return k, s, t
    cp = configparser.ConfigParser()
    cp.read(os.path.expanduser("~/.aws/credentials"))
    p = os.environ.get("AWS_PROFILE", "default")
    if cp.has_section(p) and cp[p].get("aws_access_key_id"):
        return cp[p]["aws_access_key_id"], cp[p].get("aws_secret_access_key"), cp[p].get("aws_session_token")
    return None, None, None


def region():
    return os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "ap-south-1"


def _h(key, msg):
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def dynamo(op, body):
    k, s, t = creds()
    if not k:
        raise RuntimeError("no AWS credentials")
    reg, host, payload = region(), f"dynamodb.{region()}.amazonaws.com", json.dumps(body).encode()
    amz = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    day = amz[:8]
    hdr = {"content-type": "application/x-amz-json-1.0", "host": host, "x-amz-date": amz, "x-amz-target": "DynamoDB_20120810." + op}
    if t:
        hdr["x-amz-security-token"] = t
    names = sorted(hdr)
    canon = "POST\n/\n\n" + "".join(f"{n}:{hdr[n]}\n" for n in names) + "\n" + ";".join(names) + "\n" + hashlib.sha256(payload).hexdigest()
    scope = f"{day}/{reg}/dynamodb/aws4_request"
    to_sign = f"AWS4-HMAC-SHA256\n{amz}\n{scope}\n{hashlib.sha256(canon.encode()).hexdigest()}"
    key = _h(_h(_h(_h(("AWS4" + s).encode(), day), reg), "dynamodb"), "aws4_request")
    hdr["authorization"] = f"AWS4-HMAC-SHA256 Credential={k}/{scope}, SignedHeaders={';'.join(names)}, Signature={hmac.new(key, to_sign.encode(), hashlib.sha256).hexdigest()}"
    req = urllib.request.Request(f"https://{host}/", payload, hdr)
    try:
        return json.load(net.urlopen(req, timeout=10))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"DynamoDB {op}: {e.read().decode()[:200]}")
