"""One bounded Claude clinical review; no raw audio, retries or provider fallback."""
import json
import logging
import os
import re
import urllib.error
import urllib.request

from app import voice_exam_core as core
from app.clinical_privacy import redact_direct_identifiers


def _schema(node):
    if isinstance(node, list):
        return [_schema(item) for item in node]
    if not isinstance(node, dict):
        return node
    result = {key: _schema(value) for key, value in node.items()}
    if 'type' in result:
        result['type'] = result['type'].lower()
    if result.get('type') == 'object':
        result['additionalProperties'] = False
    return result


def review(prompt, data, schema):
    key = (os.getenv('ANTHROPIC_API_KEY') or '').strip()
    model = (os.getenv('VOICE_EXAM_CLAUDE_MODEL') or 'claude-haiku-5-5').strip()
    if not key or not re.fullmatch(r'claude-[A-Za-z0-9._-]{1,100}', model):
        raise core.VoiceError('Son değerlendirme için Claude yapılandırması hazır değil.')
    payload = {'model': model, 'max_tokens': 8192, 'stream': False,
        'system': prompt,
        'messages': [{'role': 'user', 'content': redact_direct_identifiers(json.dumps(data, ensure_ascii=False))}],
        'output_config': {'format': {'type': 'json_schema', 'schema': _schema(schema)}}}
    from app.http_transport import urlopen
    from app.provider_budget import reservation
    request = urllib.request.Request('https://api.anthropic.com/v1/messages', method='POST',
        data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
        headers={'Content-Type': 'application/json', 'x-api-key': key, 'anthropic-version': '2023-06-01'})
    try:
        with reservation('anthropic', model), urlopen(request, timeout=90) as response:
            raw = response.read(core.MAX_RESPONSE + 1)
    except urllib.error.HTTPError as exc:
        # Never log provider messages: they can include user data. Fixed categories only.
        body = exc.read(65536).decode('utf-8', errors='replace').casefold()
        category = ('schema_complexity' if 'complex' in body and 'schema' in body else
                    'schema_optional_limit' if 'optional' in body else
                    'schema_argument' if 'schema' in body else 'provider_argument')
        logging.getLogger(__name__).warning('voice_claude_error status=%d category=%s', exc.code, category)
        raise
    if len(raw) > core.MAX_RESPONSE:
        raise ValueError('Response too large')
    message = json.loads(raw)
    if message.get('stop_reason') != 'end_turn':
        raise ValueError('Incomplete clinical review')
    result = json.loads(''.join(block.get('text', '') for block in message.get('content', [])
                              if block.get('type') == 'text'))
    if not isinstance(result, dict) or set(result) != set(schema['required']):
        raise ValueError('Invalid clinical review')
    return result
