"""Bound HTTP admission and multipart bytes before framework spooling."""
import os
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse


class RequestLimits:
    def __init__(self, app, *, max_bytes=None):
        self.app = app
        self.max_bytes = max_bytes or int(os.getenv('DENTAL_MAX_REQUEST_BYTES', str(320 * 1024 * 1024)))
        self.maximum = int(os.getenv('DENTAL_MAX_HTTP_REQUESTS', '32'))
        self.active = 0
        self.uploads = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') in {'/healthz', '/readyz'}:
            await self.app(scope, receive, send)
            return
        if self.active >= self.maximum:
            await JSONResponse({'ok': False, 'error': 'Service busy; retry later'}, status_code=503,
                               headers={'Retry-After': '5'})(scope, receive, send)
            return
        headers = dict(scope.get('headers', []))
        try:
            if int(headers.get(b'content-length', b'0')) > self.max_bytes:
                await JSONResponse({'detail': 'Upload too large'}, status_code=413)(scope, receive, send)
                return
        except ValueError:
            await JSONResponse({'detail': 'Invalid Content-Length'}, status_code=400)(scope, receive, send)
            return
        multipart = b'multipart/form-data' in headers.get(b'content-type', b'')
        if multipart and self.uploads >= int(os.getenv('DENTAL_MAX_UPLOADS', '2')):
            await JSONResponse({'detail': 'Upload capacity occupied'}, status_code=503, headers={'Retry-After': '5'})(scope, receive, send)
            return
        self.active += 1
        if multipart:
            self.uploads += 1
        total = 0
        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > self.max_bytes:
                    raise HTTPException(413, 'Upload too large')
            return message
        try:
            await self.app(scope, bounded_receive, send)
        finally:
            self.active -= 1
            if multipart:
                self.uploads -= 1
