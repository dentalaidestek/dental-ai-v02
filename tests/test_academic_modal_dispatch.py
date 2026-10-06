import io
import logging
import unittest
import urllib.error
import urllib.request
import urllib.response
from email.message import Message
from unittest.mock import patch

from app.academic_modal_dispatch import wake_academic_modal_indexer, _RejectRedirects


class Response(io.BytesIO):
    status = 200


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict("os.environ", {
            "ACADEMIC_MODAL_DISPATCH_URL": "https://example.invalid/wake",
            "ACADEMIC_MODAL_DISPATCH_SECRET": "test-only-secret",
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def test_acknowledged_wake_is_observable_and_authenticated(self):
        with patch("app.academic_modal_dispatch._open_dispatch_request", return_value=Response(b'{"ok":true,"scheduled":true}')) as request:
            with self.assertLogs("uvicorn.error.academic_modal_dispatch", logging.INFO) as logs:
                self.assertTrue(wake_academic_modal_indexer())
            self.assertIn("outcome=scheduled", " ".join(logs.output))
            self.assertNotIn("test-only-secret", " ".join(logs.output))
            args, kwargs = request.call_args
            self.assertEqual(args[0].get_header("Authorization"), "Bearer test-only-secret")
            self.assertEqual(args[0].data, b"{}")
            self.assertEqual(kwargs["timeout"], 5)

    def test_transient_failure_retries_with_bounded_jitter(self):
        outcomes = [TimeoutError(), urllib.error.URLError("test-only-secret"), Response(b'{"ok":true,"scheduled":true}')]
        with patch("app.academic_modal_dispatch._open_dispatch_request", side_effect=outcomes) as request, patch("time.sleep") as sleep, patch("random.uniform", return_value=0.1) as jitter:
            with self.assertLogs("uvicorn.error.academic_modal_dispatch", logging.INFO) as logs:
                self.assertTrue(wake_academic_modal_indexer())
            self.assertEqual(request.call_count, 3)
            self.assertEqual(sleep.call_count, 2)
            self.assertEqual([c.args for c in jitter.call_args_list], [(0, 0.5), (0, 1.0)])
            self.assertNotIn("test-only-secret", " ".join(logs.output))

    def test_auth_failure_does_not_retry(self):
        error = urllib.error.HTTPError("https://example.invalid", 401, "unauthorized", {}, None)
        with patch("app.academic_modal_dispatch._open_dispatch_request", side_effect=error) as request, patch("time.sleep") as sleep:
            self.assertFalse(wake_academic_modal_indexer())
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()

    def test_insecure_or_malformed_endpoint_never_sends_secret(self):
        for endpoint in ("http://example.invalid/wake", "file:///tmp/wake", "https:///wake", "https://example.invalid:bad/wake"):
            with patch.dict("os.environ", {"ACADEMIC_MODAL_DISPATCH_URL": endpoint}), patch("app.academic_modal_dispatch._open_dispatch_request") as request:
                with self.assertLogs("uvicorn.error.academic_modal_dispatch", logging.WARNING) as logs:
                    self.assertFalse(wake_academic_modal_indexer())
                request.assert_not_called()
                self.assertNotIn("test-only-secret", " ".join(logs.output))
                self.assertNotIn(endpoint, " ".join(logs.output))

    def test_redirect_never_sends_a_second_authenticated_request(self):
        for status in (301, 302, 303, 307, 308):
            requests = []
            class HTTPSStub(urllib.request.HTTPSHandler):
                def https_open(self, request):
                    requests.append(request)
                    headers = Message()
                    headers["Location"] = "https://other.invalid/wake"
                    response = urllib.response.addinfourl(io.BytesIO(b""), headers, request.full_url, status)
                    response.msg = "Redirect"
                    return response
            opener = urllib.request.build_opener(_RejectRedirects(), HTTPSStub())
            with patch("urllib.request.build_opener", return_value=opener), patch("time.sleep") as sleep:
                self.assertFalse(wake_academic_modal_indexer())
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0].full_url, "https://example.invalid/wake")
            sleep.assert_not_called()

    def test_success_reaches_uvicorn_handler_when_root_filters_info(self):
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        root = logging.getLogger()
        server = logging.getLogger("uvicorn.error")
        previous = (root.level, server.level, server.handlers, server.propagate)
        try:
            root.setLevel(logging.WARNING)
            server.setLevel(logging.INFO)
            server.handlers = [handler]
            server.propagate = False
            with patch("app.academic_modal_dispatch._open_dispatch_request", return_value=Response(b'{"ok":true,"scheduled":true}')):
                self.assertTrue(wake_academic_modal_indexer())
            self.assertIn("outcome=scheduled", output.getvalue())
            self.assertNotIn("test-only-secret", output.getvalue())
        finally:
            root.setLevel(previous[0])
            server.setLevel(previous[1])
            server.handlers = previous[2]
            server.propagate = previous[3]

    def test_outage_and_invalid_acknowledgement_cannot_succeed(self):
        for outcome in (lambda: TimeoutError(), lambda: Response(b'{"ok":true}')):
            with patch("app.academic_modal_dispatch._open_dispatch_request", side_effect=lambda *a, **k: self._response(outcome)), patch("time.sleep"):
                self.assertFalse(wake_academic_modal_indexer())

    @staticmethod
    def _response(factory):
        result = factory()
        if isinstance(result, Exception):
            raise result
        return result


if __name__ == "__main__":
    unittest.main()
