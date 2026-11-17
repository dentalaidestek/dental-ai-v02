"""Bounded Expo Push transport. Never include clinical or patient content."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import uuid
from urllib import error, request

logger = logging.getLogger(__name__)

EXPO_URL = "https://exp.host/--/api/v2/push/send"
EXPO_RECEIPTS_URL = "https://exp.host/--/api/v2/push/getReceipts"
MAX_SEND_BATCH = 100
MAX_SEND_TOKENS = 1000
MAX_RECEIPT_BATCH = 1000
REQUEST_TIMEOUT_SECONDS = 8

_TOKEN_RE = re.compile(r"(?:Expo|Exponent)PushToken\[[A-Za-z0-9_-]{8,128}\]")
_ERROR_CODES = {
    "DeviceNotRegistered",
    "MessageRateExceeded",
    "InvalidCredentials",
    "MessageTooBig",
    "MismatchSenderId",
    "InvalidProviderToken",
    "PUSH_TOO_MANY_NOTIFICATIONS",
    "PUSH_TOO_MANY_RECEIPTS",
    "PUSH_TOO_MANY_EXPERIENCE_IDS",
    "TOO_MANY_REQUESTS",
    "UNAUTHORIZED",
    "TRANSPORT",
    "TRANSPORT_UNCERTAIN",
    "NO_TICKET",
    "MISSING_TICKET_ID",
    "INVALID_TICKET",
    "INVALID_RECEIPT_RESPONSE",
    "RECEIPT_NOT_READY",
    "CHECK_LEASE_EXPIRED",
    "SENDER_LEASE_EXPIRED",
    "RECEIPT_TTL_EXPIRED",
}


def is_enabled() -> bool:
    return os.getenv("MOBILE_PUSH_ENABLED", "").lower() in {"1", "true", "yes"}


def is_valid_expo_push_token(token: object) -> bool:
    return isinstance(token, str) and bool(_TOKEN_RE.fullmatch(token))


def token_fingerprint(token: str) -> str:
    """Stable one-way token binding; raw Expo tokens are never persisted in receipts."""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _receipt_id(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        return str(uuid.UUID(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _safe_error_code(value: object) -> str:
    if not isinstance(value, str):
        return "OTHER"
    if value in _ERROR_CODES or re.fullmatch(r"HTTP_[1-5][0-9]{2}", value):
        return value
    return "OTHER"


def _headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    access_token = os.getenv("EXPO_ACCESS_TOKEN", "").strip()
    if access_token:
        headers["Authorization"] = "Bearer " + access_token
    return headers


def send_push_tokens(tokens, *, title="Dental AI", body="Yeni bir bildiriminiz var.", data=None):
    """Send at most 1,000 unique tokens in <=100-message requests and retain safe tickets."""
    if not is_enabled():
        return {"enabled": False, "sent": 0, "tickets": [], "errors": []}

    unique = []
    seen = set()
    valid_unique_count = 0
    for token in tokens:
        if not is_valid_expo_push_token(token) or token in seen:
            continue
        seen.add(token)
        valid_unique_count += 1
        if len(unique) < MAX_SEND_TOKENS:
            unique.append(token)

    tickets = []
    errors = []
    for offset in range(0, len(unique), MAX_SEND_BATCH):
        batch_tokens = unique[offset:offset + MAX_SEND_BATCH]
        batch = [
            {"to": token, "title": str(title)[:120], "body": str(body)[:180],
             "sound": "default", "data": data if isinstance(data, dict) else {}}
            for token in batch_tokens
        ]
        try:
            req = request.Request(
                EXPO_URL, data=json.dumps(batch).encode("utf-8"),
                headers=_headers(), method="POST",
            )
            with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
                result = json.load(response)
            returned = result.get("data") if isinstance(result, dict) else None
            if not isinstance(returned, list):
                returned = []
            for index, token in enumerate(batch_tokens):
                item = returned[index] if index < len(returned) and isinstance(returned[index], dict) else {}
                status = item.get("status")
                if status == "ok":
                    receipt_id = _receipt_id(item.get("id"))
                    tickets.append({
                        "token_fingerprint": token_fingerprint(token),
                        "status": "ok" if receipt_id else "error",
                        "ticket_id": receipt_id,
                        "error_code": None if receipt_id else "MISSING_TICKET_ID",
                    })
                elif status == "error":
                    details = item.get("details") if isinstance(item.get("details"), dict) else {}
                    tickets.append({
                        "token_fingerprint": token_fingerprint(token),
                        "status": "error",
                        "ticket_id": None,
                        "error_code": _safe_error_code(details.get("error")),
                    })
                else:
                    tickets.append({
                        "token_fingerprint": token_fingerprint(token),
                        "status": "error",
                        "ticket_id": None,
                        "error_code": "INVALID_TICKET",
                    })
        except error.HTTPError as exc:
            errors.append({
                "error_code": "HTTP_" + str(int(exc.code)),
                "ambiguous": False,
            })
            logger.warning("Expo push request rejected: HTTP %s", int(exc.code))
        except (error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
            # A timeout may happen after Expo accepted the request. Do not retry it
            # automatically: an ambiguous retry could create a duplicate notification.
            errors.append({"error_code": "TRANSPORT_UNCERTAIN", "ambiguous": True})
            logger.warning("Expo push transport unavailable: %s", type(exc).__name__)

    return {
        "enabled": True,
        "sent": sum(1 for item in tickets if item["status"] == "ok"),
        "tickets": tickets,
        "errors": errors,
        "truncated": max(0, valid_unique_count - len(unique)),
    }


def get_push_receipts(receipt_ids):
    """Fetch at most 1,000 UUID receipts; callers own retry timing and persistence."""
    ids = []
    seen = set()
    for value in receipt_ids:
        receipt_id = _receipt_id(value)
        if receipt_id is None:
            raise ValueError("Invalid Expo receipt ID")
        if receipt_id not in seen:
            seen.add(receipt_id)
            ids.append(receipt_id)
    if len(ids) > MAX_RECEIPT_BATCH:
        raise ValueError("At most 1,000 Expo receipts may be requested at once")
    if not ids:
        return {"ok": True, "receipts": {}}

    try:
        req = request.Request(
            EXPO_RECEIPTS_URL,
            data=json.dumps({"ids": ids}).encode("utf-8"),
            headers=_headers(),
            method="POST",
        )
        with request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            result = json.load(response)
        data = result.get("data") if isinstance(result, dict) else None
        if not isinstance(data, dict):
            return {"ok": False, "receipts": {}, "error_code": "INVALID_RECEIPT_RESPONSE"}
        receipts = {}
        for key, value in data.items():
            receipt_id = _receipt_id(key)
            if receipt_id in seen and isinstance(value, dict):
                receipts[receipt_id] = value
        return {"ok": True, "receipts": receipts}
    except error.HTTPError as exc:
        logger.warning("Expo receipt request rejected: HTTP %s", int(exc.code))
        return {"ok": False, "receipts": {}, "error_code": "HTTP_" + str(int(exc.code))}
    except (error.URLError, TimeoutError, OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Expo receipt transport unavailable: %s", type(exc).__name__)
        return {"ok": False, "receipts": {}, "error_code": "TRANSPORT"}
