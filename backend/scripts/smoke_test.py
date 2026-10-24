"""Run against a local demo server: python scripts/smoke_test.py"""

import json
import os
import urllib.request

base = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
key = os.getenv("API_KEY", "local-dev-secret")
req = urllib.request.Request(
    base + "/api/v1/ask",
    data=json.dumps({"query": "differentiate polynomial x^3"}).encode(),
    headers={"Content-Type": "application/json", "X-API-Key": key},
    method="POST",
)
opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
with opener.open(req, timeout=10) as res:
    body = json.load(res)
print(json.dumps(body, indent=2))
if body["status"] != "answered":
    raise SystemExit("Smoke test failed: answer unavailable")
