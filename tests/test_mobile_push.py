"""Push transport safety regression tests; no external requests."""
import json
import os
import unittest
from unittest.mock import patch

from app.mobile_push import send_push_tokens


class _Response:
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, *_):
        return b'{"data":[{"status":"ok"}]}'

class PushTransportTests(unittest.TestCase):
    def test_disabled_by_default(self):
        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": ""}), patch("app.mobile_push.request.urlopen") as send:
            result = send_push_tokens(["ExpoPushToken[abc]"])
            self.assertEqual(result["sent"], 0)
            send.assert_not_called()

    def test_deduplicates_and_ignores_invalid_tokens(self):
        captured = []
        def fake_open(req, timeout):
            captured.extend(json.loads(req.data))
            return _Response()
        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": "true"}), patch("app.mobile_push.request.urlopen", side_effect=fake_open):
            send_push_tokens(["ExpoPushToken[abc]", "ExpoPushToken[abc]", "invalid"])
        self.assertEqual([x["to"] for x in captured], ["ExpoPushToken[abc]"])

    def test_never_sends_more_than_one_hundred_per_request(self):
        batches = []
        class Response:
            def __init__(self, count):
                self.count = count
            def __enter__(self):
                return self
            def __exit__(self, *_):
                return False
            def read(self, *_):
                return json.dumps({"data": [{"status": "ok"}] * self.count}).encode()
        def fake_open(req, timeout):
            count = len(json.loads(req.data))
            batches.append(count)
            return Response(count)
        tokens = [f"ExpoPushToken[{i}]" for i in range(205)]
        with patch.dict(os.environ, {"MOBILE_PUSH_ENABLED": "true"}), patch("app.mobile_push.request.urlopen", side_effect=fake_open):
            result = send_push_tokens(tokens)
        self.assertEqual(batches, [100, 100, 5])
        self.assertEqual(result["sent"], 205)


if __name__ == "__main__":
    unittest.main()
