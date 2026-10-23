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


def review(prompt, data, schema, *, extraction=False):
    key = (os.getenv('ANTHROPIC_API_KEY') or '').strip()
    model = (os.getenv('VOICE_EXAM_CLAUDE_MODEL') or 'claude-haiku-5-5').strip()
    if not key or not re.fullmatch(r'claude-[A-Za-z0-9._-]{1,100}', model):
        raise core.VoiceError('Son değerlendirme için Claude yapılandırması hazır değil.')
    payload = {'model': model, 'max_tokens': 16384 if extraction else 8192, 'stream': False,
        'system': prompt,
        'messages': [{'role': 'user', 'content': redact_direct_identifiers(json.dumps(data, ensure_ascii=False))}]}
    if extraction:
        # One forced, non-executable data tool avoids compiling the wide extraction
        # grammar. normalize() still validates every clinical quotation and value.
        payload['tools'] = [{'name': 'clinical_extract', 'description': 'Return the clinical extraction as structured data only.',
                             'input_schema': _schema(schema)}]
        payload['tool_choice'] = {'type': 'tool', 'name': 'clinical_extract'}
    else:
        payload['output_config'] = {'format': {'type': 'json_schema', 'schema': _schema(schema)}}
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
    if extraction:
        blocks = [block for block in message.get('content', []) if block.get('type') == 'tool_use']
        stop = message.get('stop_reason')
        logging.getLogger(__name__).warning('voice_claude_extraction stop=%s tools=%d',
            stop if stop in {'end_turn', 'tool_use', 'max_tokens', 'refusal', 'stop_sequence'} else 'other', len(blocks))
        if message.get('stop_reason') != 'tool_use' or len(blocks) != 1 or blocks[0].get('name') != 'clinical_extract':
            raise ValueError('Incomplete clinical extraction')
        result = blocks[0].get('input')
        if isinstance(result, dict):
            # Some tool replies wrap the extraction in one object/JSON string.
            # Unpack only recognized root keys; never infer medical content.
            extras = set(result) - set(schema['required'])
            if len(extras) == 1:
                nested = result[next(iter(extras))]
                wrapper_kind = 'object' if isinstance(nested, dict) else 'json' if isinstance(nested, str) else 'other'
                if isinstance(nested, str):
                    try:
                        nested = json.loads(nested)
                    except (ValueError, TypeError):
                        nested = None
                known = set(nested) & set(schema['required']) if isinstance(nested, dict) else set()
                logging.getLogger(__name__).warning('voice_claude_extraction wrapper=%s known_keys=%d', wrapper_kind, len(known))
                if isinstance(nested, dict) and known and set(nested) <= set(schema['required']):
                    overlap = set(result) & set(nested)
                    if any(result[key] != nested[key] for key in overlap):
                        raise ValueError('Conflicting extraction wrapper')
                    result = {key: value for key, value in result.items() if key not in extras} | nested
            missing = set(schema['required']) - set(result)
            logging.getLogger(__name__).warning('voice_claude_extraction missing=%s extra_count=%d',
                ','.join(sorted(missing)), len(set(result) - set(schema['required'])))
            # Optional coaching/checklist omissions do not erase valid clinical facts.
            # Critical clinical structures must always be present and normalize()
            # validates their values and quotations before anything reaches the UI.
            if not {'clinical_facts', 'fields', 'teeth', 'appointment'} <= set(result):
                raise ValueError('Missing clinical extraction')
            defaults = {'transcript': '', 'uncertain': '', **{key: [] for key in
                ('communication', 'decision_barriers', 'follow_up_questions', 'source_requests',
                 'literature_topics', 'removed_fields', 'removed_teeth')}}
            result = {key: result.get(key, defaults.get(key)) for key in schema['required']}
    else:
        if message.get('stop_reason') != 'end_turn':
            raise ValueError('Incomplete clinical review')
        result = json.loads(''.join(block.get('text', '') for block in message.get('content', [])
                                  if block.get('type') == 'text'))
    if not isinstance(result, dict) or set(result) != set(schema['required']):
        raise ValueError('Invalid clinical review')
    return result
