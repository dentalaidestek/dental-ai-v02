"""Reject browser-origin mutations from unrelated sites without DB work.

Native clients and server callbacks without Origin retain their existing auth
contracts. This supplements session authentication; it is not a CORS policy.
"""
import os
from urllib.parse import urlsplit

from starlette.responses import JSONResponse


def _origin(value):
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname or parsed.username or parsed.password:
            return None
        if parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
            return None
        return (parsed.scheme.lower(), parsed.hostname.lower(),
                parsed.port or (443 if parsed.scheme == 'https' else 80))
    except (ValueError, AttributeError):
        return None


class BrowserOriginGuard:
    def __init__(self, app):
        self.app = app
        configured = os.getenv('WEB_ALLOWED_ORIGINS', 'https://dentalai.tr,https://www.dentalai.tr')
        self.allowed = {item for value in configured.split(',') if (item := _origin(value.strip()))}

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('method') not in {'POST', 'PUT', 'PATCH', 'DELETE'}:
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get('headers', []))
        supplied = headers.get(b'origin')
        rejected = False
        if supplied is not None:
            origin = _origin(supplied.decode('latin-1'))
            host = headers.get(b'host', b'').decode('latin-1')
            target = _origin(scope.get('scheme', 'http') + '://' + host)
            rejected = origin is None or (origin != target and origin not in self.allowed)
        elif headers.get(b'sec-fetch-site', b'').lower() == b'cross-site':
            rejected = True
        if rejected:
            await JSONResponse({'ok': False, 'error': 'Bu kaynaktan işlem yapılamaz.'}, status_code=403,
                headers={'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff'})(scope, receive, send)
            return
        await self.app(scope, receive, send)
