"""Bound HTTP admission and multipart bytes before framework spooling."""
import os
import re
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

_ACADEMIC_QUESTION = re.compile(r'^/notes/courses/[^/]+/ai/ask(?:-stream)?/?$')
_TEXT_ACTIONS = {'/login', '/register', '/forgot-password', '/reset-password', '/verify-email', '/account/password'}
_MOBILE_AUTH = re.compile(r'^/api/mobile/v1/auth/[^/]+/?$')
_MOBILE_ACADEMIC_QUESTION = re.compile(r'^/api/mobile/v1/academic/courses/[^/]+/ask/?$')


def _academic_question(scope):
    return scope.get('method') == 'POST' and bool(
        scope.get('path') in {'/ai/ask', '/ai/ask/'}
        or _ACADEMIC_QUESTION.fullmatch(scope.get('path', ''))
        or _MOBILE_ACADEMIC_QUESTION.fullmatch(scope.get('path', '')))


class RequestLimits:
    def __init__(self, app, *, max_bytes=None):
        self.app = app
        self.max_bytes = max_bytes or int(os.getenv('DENTAL_MAX_REQUEST_BYTES', str(320 * 1024 * 1024)))
        self.maximum = int(os.getenv('DENTAL_MAX_HTTP_REQUESTS', '32'))
        # Reserve ordinary HTTP capacity for navigation while slow model
        # streams are open. This bounds preparation as well as provider I/O.
        self.academic_maximum = min(max(1, int(os.getenv('DENTAL_MAX_ACADEMIC_REQUESTS', '2'))),
                                    max(1, self.maximum - 1))
        self.active = 0
        self.uploads = 0
        self.academic = 0

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or scope.get('path') in {'/healthz', '/readyz'}:
            await self.app(scope, receive, send)
            return
        academic = _academic_question(scope)
        if academic and self.academic >= self.academic_maximum:
            await JSONResponse({'ok': False, 'error': 'Akademik AI şu anda yoğun. Kısa süre sonra yeniden dene.'},
                               status_code=503, headers={'Retry-After': '5'})(scope, receive, send)
            return
        if self.active >= self.maximum:
            await JSONResponse({'ok': False, 'error': 'Service busy; retry later'}, status_code=503,
                               headers={'Retry-After': '5'})(scope, receive, send)
            return
        headers = dict(scope.get('headers', []))
        text_action = academic or (scope.get('method') == 'POST' and (
            scope.get('path', '').rstrip('/') in _TEXT_ACTIONS
            or _MOBILE_AUTH.fullmatch(scope.get('path', ''))))
        body_limit = min(self.max_bytes, 65536) if text_action else self.max_bytes
        try:
            if int(headers.get(b'content-length', b'0')) > body_limit:
                await JSONResponse({'detail': 'Upload too large'}, status_code=413)(scope, receive, send)
                return
        except ValueError:
            await JSONResponse({'detail': 'Invalid Content-Length'}, status_code=400)(scope, receive, send)
            return
        # The question form uses FormData but accepts only text. It must not
        # occupy the file-upload lane. Its full body remains byte bounded.
        multipart = b'multipart/form-data' in headers.get(b'content-type', b'') and not academic
        if multipart and self.uploads >= int(os.getenv('DENTAL_MAX_UPLOADS', '2')):
            await JSONResponse({'detail': 'Upload capacity occupied'}, status_code=503, headers={'Retry-After': '5'})(scope, receive, send)
            return
        self.active += 1
        if academic:
            self.academic += 1
        if multipart:
            self.uploads += 1
        total = 0
        async def bounded_receive():
            nonlocal total
            message = await receive()
            if message['type'] == 'http.request':
                total += len(message.get('body', b''))
                if total > body_limit:
                    raise HTTPException(413, 'Upload too large')
            return message
        try:
            await self.app(scope, bounded_receive, send)
        finally:
            self.active -= 1
            if academic:
                self.academic -= 1
            if multipart:
                self.uploads -= 1
