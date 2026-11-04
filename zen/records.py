"""Executed claims and payments, kept in DynamoDB (table zen_records, one partition per user). Writes go through one background
worker so a slow or failing AWS call never slows or breaks a chat. Evals, batch runs and local mode have no owner and write nothing."""
import datetime, json, os, queue, threading, uuid
from . import aws

TABLE = os.environ.get("ZEN_DDB_TABLE", "zen_records")
STATUS = {"error": None}
_q = queue.Queue()


def enabled(owner="x"):
    if os.environ.get("ZEN_DDB") == "off" or not owner or not aws.creds()[0]:
        return False
    return owner != "local" or os.environ.get("ZEN_DDB") == "on"  # local dev mode stays out of the real table unless asked


def _worker():
    while True:
        item = _q.get()
        try:
            aws.dynamo("PutItem", {"TableName": TABLE, "Item": item})
            STATUS["error"] = None
        except Exception as e:
            STATUS["error"] = str(e)[:200]


threading.Thread(target=_worker, daemon=True).start()


def save(owner, kind, data):
    if not enabled(owner):
        return
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _q.put({"user_id": {"S": owner}, "sk": {"S": f"{now}#{uuid.uuid4().hex[:8]}"}, "kind": {"S": kind}, "created_at": {"S": now}, "data": {"S": json.dumps(data)}})


def recent(owner, limit=50):
    if not enabled(owner):
        return []
    try:
        r = aws.dynamo("Query", {"TableName": TABLE, "KeyConditionExpression": "user_id = :u", "ExpressionAttributeValues": {":u": {"S": owner}},
                                 "ScanIndexForward": False, "Limit": limit})
        STATUS["error"] = None
        return [dict(kind=i["kind"]["S"], created_at=i["created_at"]["S"], **json.loads(i["data"]["S"])) for i in r.get("Items", [])]
    except Exception as e:
        STATUS["error"] = str(e)[:200]
        return []
