"""Bounded connection reuse with urllib-compatible provider error contracts.

No automatic retries: existing provider/job policies own retry budgets.
Only use from synchronous workers or explicitly offloaded request handlers.
"""
import atexit
import io
import urllib.error
import urllib.request
import urllib3

_POOL = urllib3.PoolManager(num_pools=8, maxsize=4, block=True)
atexit.register(_POOL.clear)


class Response:
    def __init__(self, response):
        self._response = response
        self.headers = response.headers
        self.status = response.status

    def read(self, amount=None):
        try:
            return self._response.read(amount)
        except urllib3.exceptions.HTTPError as exc:
            self.close()
            raise urllib.error.URLError(type(exc).__name__) from exc

    def readline(self, amount=-1):
        try:
            return self._response.readline(amount)
        except urllib3.exceptions.HTTPError as exc:
            self.close()
            raise urllib.error.URLError(type(exc).__name__) from exc

    def __iter__(self):
        while line := self.readline():
            yield line

    def getcode(self):
        return self.status

    def getheader(self, name, default=None):
        return self.headers.get(name, default)

    def close(self):
        # A partially consumed SSE stream must never re-enter the pool dirty.
        if not self._response.isclosed():
            self._response.close()
        self._response.release_conn()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def urlopen(request, timeout=75):
    if isinstance(request, str):
        request = urllib.request.Request(request)
    try:
        response = _POOL.request(
            request.get_method(), request.full_url,
            body=request.data, headers=dict(request.header_items()),
            timeout=urllib3.Timeout(connect=min(5.0, float(timeout)), read=float(timeout)),
            pool_timeout=2.0, retries=False, redirect=False, preload_content=False,
        )
    except urllib3.exceptions.HTTPError as exc:
        # Preserve existing URLError handling without leaking credentialed URLs.
        raise urllib.error.URLError(type(exc).__name__) from exc
    wrapped = Response(response)
    if response.status >= 300:
        try:
            body = wrapped.read(65536)
        finally:
            wrapped.close()
        raise urllib.error.HTTPError(request.full_url, response.status,
                                     response.reason, response.headers, io.BytesIO(body))
    return wrapped
