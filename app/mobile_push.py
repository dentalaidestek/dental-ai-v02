"""Best-effort Expo Push transport. Never include clinical or patient content."""
import json
import logging
import os
from urllib import request, error

logger = logging.getLogger(__name__)
EXPO_URL = "https://exp.host/--/api/v2/push/send"

def send_push_tokens(tokens, *, title="Dental AI", body="Yeni bir bildiriminiz var.", data=None):
    """Send in bounded batches. Returns ticket summaries; failures never block core transactions."""
    if not os.getenv("MOBILE_PUSH_ENABLED", "").lower() in {"1", "true", "yes"}:
        return {"enabled": False, "sent": 0}
    unique = list(dict.fromkeys(t for t in tokens if isinstance(t, str) and
                               (t.startswith("ExponentPushToken[") or t.startswith("ExpoPushToken[")) and t.endswith("]")))
    sent = 0
    for offset in range(0, min(len(unique), 1000), 100):
        batch = [{"to": token, "title": title[:120], "body": body[:180],
                  "sound": "default", "data": data or {}} for token in unique[offset:offset+100]]
        payload = json.dumps(batch).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        access_token = os.getenv("EXPO_ACCESS_TOKEN", "").strip()
        if access_token:
            headers["Authorization"] = "Bearer " + access_token
        try:
            req = request.Request(EXPO_URL, data=payload, headers=headers, method="POST")
            with request.urlopen(req, timeout=8) as response:
                result = json.load(response)
            tickets = result.get("data", [])
            sent += sum(1 for t in tickets if t.get("status") == "ok")
            for ticket in tickets:
                if ticket.get("status") != "ok":
                    logger.warning("Expo push ticket rejected: %s", ticket.get("details", {}).get("error", "unknown"))
        except (OSError, ValueError, error.HTTPError) as exc:
            logger.warning("Expo push transport unavailable: %s", type(exc).__name__)
    return {"enabled": True, "sent": sent}
