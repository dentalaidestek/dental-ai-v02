"""Expo transport regressions; all HTTP responses are mocked."""
import json
import os
import unittest
import uuid
from unittest.mock import patch
from urllib.error import HTTPError

from app.mobile_push import (
    EXPO_RECEIPTS_URL,
    MAX_RECEIPT_BATCH,
    REQUEST_TIMEOUT_SECONDS,
    get_push_receipts,
    send_push_tokens,
    token_fingerprint,
)


def token(index):
    return f"ExpoPushToken[device{index:08d}abcdef]"


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def read(self, *_):
        return json.dumps(self.payload).encode("utf-8")


class PushTransportTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": ""}), patch("app.mobile_push.request.urlopen") as send:
            result = send_push_tokens([token(1)])
            self.assertEqual(result["sent"], 0)
            self.assertEqual(result["tickets"], [])
            send.assert_not_called()

    def test_deduplicates_and_returns_only_fingerprinted_ticket_metadata(self):
        receipt_id = str(uuid.UUID(int=1))
        captured = []

        def fake_open(req, timeout):
            captured.extend(json.loads(req.data))
            self.assertEqual(timeout, REQUEST_TIMEOUT_SECONDS)
            return _Response({"data": [{"status": "ok", "id": receipt_id}]})

        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": "true"}), patch(
            "app.mobile_push.request.urlopen", side_effect=fake_open
        ):
            result = send_push_tokens([token(1), token(1), "invalid"])

        self.assertEqual(len(captured), 1)
        self.assertEqual(result["sent"], 1)
        self.assertEqual(result["tickets"], [{
            "token_fingerprint": token_fingerprint(token(1)),
            "status": "ok",
            "ticket_id": receipt_id,
            "error_code": None,
        }])
        self.assertNotIn(token(1), json.dumps(result))

    def test_never_sends_more_than_one_hundred_per_request(self):
        batches = []
        sequence = 0

        def fake_open(req, timeout):
            nonlocal sequence
            count = len(json.loads(req.data))
            batches.append(count)
            ids = []
            for _ in range(count):
                sequence += 1
                ids.append({"status": "ok", "id": str(uuid.UUID(int=sequence))})
            return _Response({"data": ids})

        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": "true"}), patch(
            "app.mobile_push.request.urlopen", side_effect=fake_open
        ):
            result = send_push_tokens([token(i) for i in range(205)])

        self.assertEqual(batches, [100, 100, 5])
        self.assertEqual(result["sent"], 205)
        self.assertEqual(len(result["tickets"]), 205)

    def test_send_input_is_bounded_to_one_thousand_unique_tokens(self):
        calls = []

        def fake_open(req, timeout):
            payload = json.loads(req.data)
            calls.append(len(payload))
            start = sum(calls[:-1])
            return _Response({
                "data": [
                    {"status": "ok", "id": str(uuid.UUID(int=start + index + 1))}
                    for index in range(len(payload))
                ]
            })

        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": "true"}), patch(
            "app.mobile_push.request.urlopen", side_effect=fake_open
        ):
            result = send_push_tokens([token(i) for i in range(1005)])

        self.assertEqual(calls, [100, 100, 100, 100, 100, 100, 100, 100, 100, 100])
        self.assertEqual(result["sent"], 1000)
        self.assertEqual(result["truncated"], 5)

    def test_ticket_level_device_not_registered_is_returned_as_safe_code(self):
        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": "true"}), patch(
            "app.mobile_push.request.urlopen",
            return_value=_Response({
                "data": [{
                    "status": "error",
                    "message": "must not be persisted",
                    "details": {"error": "DeviceNotRegistered"},
                }]
            }),
        ):
            result = send_push_tokens([token(1)])

        self.assertEqual(result["tickets"][0]["error_code"], "DeviceNotRegistered")
        self.assertNotIn("must not be persisted", json.dumps(result))
        self.assertNotIn(token(1), json.dumps(result))

    def test_timeout_is_ambiguous_and_not_silently_counted_as_sent(self):
        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": "true"}), patch(
            "app.mobile_push.request.urlopen", side_effect=TimeoutError()
        ):
            result = send_push_tokens([token(1)])

        self.assertEqual(result["sent"], 0)
        self.assertEqual(result["tickets"], [])
        self.assertEqual(result["errors"], [{"error_code": "TRANSPORT_UNCERTAIN", "ambiguous": True}])

    def test_http_error_is_reported_without_raw_provider_body(self):
        failure = HTTPError("https://expo.invalid", 429, "limited", {}, None)
        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": "true"}), patch(
            "app.mobile_push.request.urlopen", side_effect=failure
        ):
            result = send_push_tokens([token(1)])

        self.assertEqual(result["errors"], [{"error_code": "HTTP_429", "ambiguous": False}])

    def test_receipt_lookup_uses_official_endpoint_and_bearer_token(self):
        receipt_id = str(uuid.UUID(int=123))
        captured = {}

        def fake_open(req, timeout):
            captured["url"] = req.full_url
            captured["payload"] = json.loads(req.data)
            captured["authorization"] = req.get_header("Authorization")
            captured["timeout"] = timeout
            return _Response({"data": {receipt_id: {"status": "ok"}}})

        with patch.dict(os.environ, {"EXPO_ACCESS_TOKEN": "test-secret"}), patch(
            "app.mobile_push.request.urlopen", side_effect=fake_open
        ):
            result = get_push_receipts([receipt_id, receipt_id])

        self.assertEqual(captured["url"], EXPO_RECEIPTS_URL)
        self.assertEqual(captured["payload"], {"ids": [receipt_id]})
        self.assertEqual(captured["authorization"], "Bearer test-secret")
        self.assertEqual(captured["timeout"], REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(result, {"ok": True, "receipts": {receipt_id: {"status": "ok"}}})

    def test_receipt_lookup_rejects_more_than_one_thousand_ids(self):
        ids = [str(uuid.UUID(int=index + 1)) for index in range(MAX_RECEIPT_BATCH + 1)]
        with patch("app.mobile_push.request.urlopen") as send:
            with self.assertRaises(ValueError):
                get_push_receipts(ids)
            send.assert_not_called()

    def test_receipt_lookup_rejects_untrusted_id_shapes(self):
        with patch("app.mobile_push.request.urlopen") as send:
            with self.assertRaises(ValueError):
                get_push_receipts(["not-a-ticket"])
            send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
