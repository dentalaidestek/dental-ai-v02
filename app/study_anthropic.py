"""Claude Messages transport for Academic AI; no SDK retries or provider chain."""
from __future__ import annotations

import base64
from copy import deepcopy
import json
import logging
import os
import random
import socket
import threading
import time
import urllib.error
import urllib.request

from app.http_transport import urlopen
from app.study_provider import StudyProvider, StudyProviderError, provider_reservation
from app.study_router_state import record_api_result, target_available

logger = logging.getLogger('uvicorn.error.study_anthropic')


def _output_schema(schema):
    """Adapt transport constraints; the planner still validates its full contract."""
    schema = deepcopy(schema)
    # Keep the existing planner grammar small. Nested nullable page/form plans
    # add many grammar states to an already wide academic request contract.
    # Only the transport encodes this field; parse_request validates the full
    # decoded tool plan before any file or database operation is performed.
    properties = schema.get('properties', {})
    if 'pdf_tools' in properties:
        tool_schema = properties['pdf_tools']
        properties['pdf_tools'] = {'type': 'string', 'description':
            'For no mechanical PDF operation return an empty string. Otherwise return '
            'a JSON-encoded object matching this schema, not prose: ' +
            json.dumps(tool_schema, ensure_ascii=False, separators=(',', ':'))}
    def visit(node):
        if not isinstance(node, dict):
            return
        for key in ('minimum', 'maximum', 'minLength', 'maxLength', 'minItems', 'maxItems'):
            if key in node:
                value = node.pop(key)
                node['description'] = (node.get('description', '') + f' {key}: {value}.').strip()
        if node.get('type') == 'object':
            node['additionalProperties'] = False
        for value in node.values():
            if isinstance(value, dict):
                visit(value)
            elif isinstance(value, list):
                for child in value:
                    visit(child)
    visit(schema)
    return schema


def _events(response):
    """SSE permits multiple data lines and CRLF; never parse unfinished frames."""
    data = []
    for raw in response:
        line = raw.decode('utf-8').rstrip('\r\n')
        if not line:
            if data:
                yield json.loads('\n'.join(data))
                data = []
        elif line.startswith('data:'):
            data.append(line[5:].lstrip(' '))


class AnthropicStudyProvider(StudyProvider):
    name = 'anthropic'
    BASE_URL = 'https://api.anthropic.com/v1/messages'
    RETRYABLE_HTTP_CODES = {408, 429, 500, 502, 503, 504, 529}

    def __init__(self):
        self.api_key = (os.getenv('ANTHROPIC_API_KEY') or '').strip()
        self.timeout = 75
        self.capacity_retry = False
        self._capacity_recovery_used = False
        self._stream_state = threading.local()
        self.response_schema = None

    @property
    def last_finish_reason(self):
        return getattr(self._stream_state, 'finish_reason', 'UNKNOWN')

    @last_finish_reason.setter
    def last_finish_reason(self, value):
        self._stream_state.finish_reason = value

    def supports_generation_attachment(self, mime_type):
        return mime_type in {'application/pdf', 'image/jpeg', 'image/png', 'image/webp', 'image/gif'}

    def _payload(self, *, model, system_prompt, history, prompt, attachments=None,
                 temperature=.3, max_output_tokens=7000, response_schema=None, stream=False):
        messages = []
        for item in history:
            text = str(item.get('content') or '').strip()
            if text:
                messages.append({'role': 'assistant' if str(item.get('role')).upper() == 'ASSISTANT' else 'user',
                                 'content': text})
        content = []
        for attachment in attachments or []:
            mime = attachment.get('mime_type')
            data = attachment.get('data')
            if not self.supports_generation_attachment(mime) or not isinstance(data, bytes) or not data:
                raise StudyProviderError('Kaynak eki desteklenmiyor veya okunamadı.', code=415)
            if attachment.get('label'):
                content.append({'type': 'text', 'text': str(attachment['label'])})
            content.append({'type': 'document' if mime == 'application/pdf' else 'image',
                'source': {'type': 'base64', 'media_type': mime,
                           'data': base64.b64encode(data).decode('ascii')}})
        content.append({'type': 'text', 'text': prompt})
        messages.append({'role': 'user', 'content': content})
        effort = os.getenv('STUDY_ANTHROPIC_EFFORT', 'medium').strip().lower()
        if effort not in {'low', 'medium', 'high', 'xhigh', 'max'}:
            raise StudyProviderError('Akademik AI düşünme ayarı geçersiz.', code=400)
        payload = {'model': model, 'system': system_prompt, 'messages': messages,
                   'max_tokens': max_output_tokens, 'stream': stream,
                   'output_config': {'effort': effort}}
        # Haiku's adaptive thinking uses the model default sampling settings.
        # Never forward Gemini-specific temperature, media, or schema fields.
        schema = response_schema if response_schema is not None else self.response_schema
        if schema is not None:
            payload['output_config']['format'] = {'type': 'json_schema', 'schema': _output_schema(schema)}
        return payload

    def _recover_capacity(self, error, model):
        if (not self.capacity_retry or self._capacity_recovery_used
                or error.code not in {503, 529} or not error.retryable):
            return False
        self._capacity_recovery_used = True
        deadline = time.monotonic() + 6
        pause = threading.Event()
        pause.wait(random.uniform(.1, .3))
        while time.monotonic() < deadline:
            if target_available(self.name, model):
                logger.info('Academic capacity recovery provider=anthropic retry=1')
                return True
            pause.wait(min(.25, max(0, deadline - time.monotonic())))
        return False

    @staticmethod
    def _stop_reason(reason):
        if reason == 'max_tokens':
            return 'MAX_TOKENS'
        if reason in {'end_turn', 'stop_sequence'}:
            return 'STOP'
        raise StudyProviderError('Akademik AI yanıtı tamamlanamadı.')

    def _run_once(self, payload):
        if not self.api_key:
            raise StudyProviderError('ANTHROPIC_API_KEY tanımlı değil.', code=401)
        model = payload['model']
        if not target_available(self.name, model):
            raise StudyProviderError('Akademik AI sağlayıcısı geçici beklemede.', code=429,
                                     retryable=True, tracked=True)
        request = urllib.request.Request(self.BASE_URL, method='POST',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'x-api-key': self.api_key, 'anthropic-version': '2023-06-01',
                     'Content-Type': 'application/json'})
        started = time.perf_counter()
        self.last_finish_reason = 'UNKNOWN'
        usage, headers, success, code, emitted = {}, {}, False, None, False
        first_text_ms = None
        try:
            with provider_reservation(self.name, model), urlopen(request, timeout=self.timeout) as response:
                headers = response.headers
                code = getattr(response, 'status', 200)
                if not payload['stream']:
                    result = json.loads(response.read().decode('utf-8'))
                    usage = result.get('usage') or {}
                    self.last_finish_reason = self._stop_reason(result.get('stop_reason'))
                    answer = ''.join(block.get('text', '') for block in result.get('content', [])
                                     if block.get('type') == 'text')
                    if not answer.strip():
                        raise StudyProviderError('Akademik AI boş yanıt döndürdü.')
                    emitted = True
                    success = True
                    yield answer
                else:
                    stopped = False
                    for event in _events(response):
                        kind = event.get('type')
                        if kind == 'message_start':
                            usage.update((event.get('message') or {}).get('usage') or {})
                        elif kind == 'message_delta':
                            usage.update(event.get('usage') or {})
                            reason = (event.get('delta') or {}).get('stop_reason')
                            if reason:
                                self.last_finish_reason = self._stop_reason(reason)
                        elif kind == 'content_block_start':
                            block = event.get('content_block') or {}
                            text = block.get('text', '') if block.get('type') == 'text' else ''
                            if text:
                                emitted = True
                                first_text_ms = first_text_ms or round((time.perf_counter()-started)*1000)
                                yield text
                        elif kind == 'content_block_delta':
                            delta = event.get('delta') or {}
                            if delta.get('type') == 'text_delta' and delta.get('text'):
                                emitted = True
                                first_text_ms = first_text_ms or round((time.perf_counter()-started)*1000)
                                yield delta['text']
                        elif kind == 'error':
                            failure = (event.get('error') or {}).get('type')
                            error_code = {'overloaded_error': 529, 'rate_limit_error': 429,
                                          'api_error': 500}.get(failure, 500)
                            raise StudyProviderError('Akademik AI sağlayıcı akışı kesildi.',
                                code=error_code, retryable=error_code in self.RETRYABLE_HTTP_CODES)
                        elif kind == 'message_stop':
                            stopped = True
                            break
                    if not stopped or self.last_finish_reason == 'UNKNOWN' or not emitted:
                        raise StudyProviderError('Akademik AI yanıt akışı tamamlanmadı.')
                    success = True
        except urllib.error.HTTPError as exc:
            code, headers = exc.code, exc.headers
            # Raw provider errors may contain source/user text. Never log them.
            body = exc.read(16384).decode('utf-8', errors='replace').lower()
            reason = ('schema_complexity' if 'schema' in body and any(
                word in body for word in ('complex', 'compil', 'nesting')) else
                'schema_argument' if 'schema' in body else
                'billing' if any(word in body for word in ('credit balance', 'billing')) else
                'request_argument')
            logger.warning('Academic upstream failure provider=anthropic code=%s reason=%s', code, reason)
            raise StudyProviderError('Akademik AI sağlayıcı isteği başarısız oldu.',
                code=code, retryable=code in self.RETRYABLE_HTTP_CODES, tracked=True) from exc
        except StudyProviderError as exc:
            if exc.code is not None:
                code = exc.code
            exc.tracked = True
            raise
        except (urllib.error.URLError, TimeoutError, socket.timeout) as exc:
            code = None
            raise StudyProviderError('Akademik AI sağlayıcısına bağlantı kurulamadı.',
                                     retryable=True, tracked=True) from exc
        except (ValueError, TypeError, AttributeError, KeyError) as exc:
            raise StudyProviderError('Akademik AI sağlayıcı cevabı okunamadı.', tracked=True) from exc
        finally:
            elapsed = round((time.perf_counter()-started)*1000)
            meta = record_api_result(provider=self.name, model=model, operation='generation',
                success=success, status_code=code, latency_ms=elapsed,
                response_headers=headers, response_json={'usage': usage} if usage else None)
            logger.info('Academic provider timing provider=anthropic model=%s mode=%s '
                        'total_ms=%s first_text_ms=%s finish=%s success=%s input_tokens=%s output_tokens=%s',
                        model, 'stream' if payload['stream'] else 'json', elapsed,
                        first_text_ms, self.last_finish_reason, success,
                        meta.get('prompt_tokens') if isinstance(meta,dict) else None,
                        meta.get('output_tokens') if isinstance(meta,dict) else None)

    def _run(self, payload):
        emitted = False
        try:
            for text in self._run_once(payload):
                emitted = emitted or bool(text)
                yield text
            return
        except StudyProviderError as error:
            if emitted or not self._recover_capacity(error, payload['model']):
                raise
        yield from self._run_once(payload)

    def generate(self, **kwargs):
        answer = ''.join(self._run(self._payload(**kwargs, stream=False)))
        if self.last_finish_reason == 'MAX_TOKENS':
            raise StudyProviderError('Akademik AI yanıtı uzunluk sınırında tamamlanamadı.')
        return answer

    def generate_stream(self, **kwargs):
        yield from self._run(self._payload(**kwargs, stream=True))
