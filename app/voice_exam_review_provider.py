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


def _configuration():
    key = (os.getenv('ANTHROPIC_API_KEY') or '').strip()
    model = (os.getenv('VOICE_EXAM_CLAUDE_MODEL') or 'claude-haiku-5-5').strip()
    if not key or not re.fullmatch(r'claude-[A-Za-z0-9._-]{1,100}', model):
        raise core.VoiceError('Son değerlendirme için Claude yapılandırması hazır değil.')
    return key, model


def _log_http_error(exc, stage):
    # Never log provider messages: they can include patient data or credentials.
    body = exc.read(65536).decode('utf-8', errors='replace').casefold()
    category = ('schema_complexity' if 'complex' in body and 'schema' in body else
                'schema_optional_limit' if 'optional' in body else
                'schema_argument' if 'schema' in body else 'provider_argument')
    tags = ('input_schema', 'schema', 'strict', 'required', 'additionalproperties',
            'enum', 'empty', 'invalid', 'unsupported', 'object', 'array',
            'string', 'type', 'properties', 'format', 'optional', 'limit',
            'complex', 'compilation', 'timeout', 'union', 'anyof', 'allof',
            'model', 'beta', 'feature', 'supported', 'maximum', 'minimum',
            'tools', 'union_tag_invalid', 'extra_forbidden', 'allowed_domains',
            'max_uses', 'web_search', 'web_fetch', 'web_search_20250305',
            'web_fetch_20250910', 'output_config', 'not_found', 'permission')
    diagnostics = ','.join(tag for tag in tags if re.search(r'\b' + tag + r'\b', body)) or 'other'
    logging.getLogger(__name__).warning('voice_claude_error status=%d category=%s diagnostics=%s stage=%s',
                                       exc.code, category, diagnostics, stage)


def review(prompt, data, schema, *, extraction=False):
    key, model = _configuration()
    payload = {'model': model, 'max_tokens': 16384 if extraction else 8192, 'stream': False,
        'system': prompt,
        'messages': [{'role': 'user', 'content': redact_direct_identifiers(json.dumps(data, ensure_ascii=False))}]}
    if extraction:
        # Use a forced, non-executable data tool without optional strict grammar
        # compilation. Live rejection diagnostics implicate that option; retain
        # local validation independently of provider feature availability.
        # Required structures and grounded values are checked below and in
        # normalize(); the model response is never trusted by itself.
        payload['tools'] = [{'name': 'clinical_extract', 'description': 'Return the clinical extraction as structured data only.',
                             'input_schema': _schema(schema)}]
        # Extraction is one data object; parallel calls violate its atomic contract.
        payload['tool_choice'] = {'type': 'tool', 'name': 'clinical_extract', 'disable_parallel_tool_use': True}
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
        _log_http_error(exc, 'extraction' if extraction else 'final')
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
                    def empty(value):
                        return not value or isinstance(value, dict) and all(empty(v) for v in value.values())
                    nested = dict(nested)
                    for key in overlap:
                        if result[key] == nested[key]:
                            continue
                        if key == 'transcript':
                            nested[key] = data.get('clinical_text', '')
                        elif empty(result[key]):
                            continue
                        elif empty(nested[key]):
                            nested[key] = result[key]
                        elif key == 'uncertain' and isinstance(result[key], str) and isinstance(nested[key], str):
                            nested[key] = result[key] + '\n' + nested[key]
                        elif key == 'appointment' and isinstance(result[key], dict) and isinstance(nested[key], dict):
                            evidence = data.get('clinical_text', '')
                            left = {k: core.appointment_evidence_quote(result[key].get(k, ''), evidence)
                                    for k in ('quote', 'acceptance_quote')}
                            right = {k: core.appointment_evidence_quote(nested[key].get(k, ''), evidence)
                                     for k in ('quote', 'acceptance_quote')}
                            merged = {}
                            for name in left:
                                a, b = left[name], right[name]
                                if not a or not b or a in b or b in a:
                                    merged[name] = max((a, b), key=len)
                                else:
                                    raise ValueError('Conflicting extraction appointment')
                            nested[key] = merged
                        else:
                            logging.getLogger(__name__).warning('voice_claude_extraction conflict_key=%s', key)
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
        stop = message.get('stop_reason')
        usage = message.get('usage')
        count = usage.get('output_tokens') if isinstance(usage, dict) else None
        logging.getLogger(__name__).warning('voice_final_provider stop=%s output_tokens=%d',
            stop if isinstance(stop, str) and stop in {'end_turn', 'max_tokens', 'refusal', 'tool_use', 'pause_turn', 'stop_sequence'} else 'other',
            count if type(count) is int and 0 <= count <= 10000000 else -1)
        if stop != 'end_turn':
            raise ValueError('Incomplete clinical review')
        result = json.loads(''.join(block.get('text', '') for block in message.get('content', [])
                                  if block.get('type') == 'text'))
    if not isinstance(result, dict) or set(result) != set(schema['required']):
        raise ValueError('Invalid clinical review')
    return result



def research_message(prompt, data, tools, *, previous_messages=None, timeout=60):
    """Native tools on isolated public scopes; never patient-specific final JSON.

    Budget accounting uses the same configured provider/model and shared transport.
    Caller owns bounded pause continuation, tool errors and evidence validation.
    """
    import math
    stage, response_bytes = 'configuration', -1
    try:
        key, model = _configuration()
        stage = 'time-budget'
        if not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 < timeout <= 90:
            raise ValueError('Invalid research time budget')
        stage = 'request-encoding'
        messages = previous_messages if previous_messages is not None else [
            {'role': 'user', 'content': redact_direct_identifiers(json.dumps(data, ensure_ascii=False))}]
        payload = {'model': model, 'max_tokens': 2048, 'stream': False,
                   'system': prompt, 'messages': messages, 'tools': tools}
        from app.http_transport import urlopen
        from app.provider_budget import reservation
        request = urllib.request.Request('https://api.anthropic.com/v1/messages', method='POST',
            data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
            headers={'Content-Type': 'application/json', 'x-api-key': key, 'anthropic-version': '2023-06-01'})
        stage = 'reservation'
        with reservation('anthropic', model):
            stage = 'transport'
            with urlopen(request, timeout=timeout) as response:
                stage = 'response-read'
                raw = response.read(core.MAX_RESPONSE + 1)
                response_bytes = len(raw)
            stage = 'reservation'
        stage = 'response-size'
        if response_bytes > core.MAX_RESPONSE:
            raise ValueError('Research response too large')
        stage = 'response-json'
        message = json.loads(raw)
        stage = 'response-shape'
        if not isinstance(message, dict) or not isinstance(message.get('content'), list):
            raise ValueError('Invalid native research response')
        stage = 'response-metadata'
        stop = message.get('stop_reason')
        logging.getLogger(__name__).warning('voice_public_research stop=%s blocks=%d',
            stop if stop in {'end_turn', 'tool_use', 'max_tokens', 'refusal', 'pause_turn', 'stop_sequence'} else 'other', len(message['content']))
        return message
    except Exception as exc:
        # Stages and categories are server-owned constants. Never stringify an
        # exception: transport reasons and provider bodies can contain secrets.
        category = ('http' if isinstance(exc, urllib.error.HTTPError) else
                    'timeout' if isinstance(exc, TimeoutError) or
                    isinstance(exc, urllib.error.URLError) and isinstance(exc.reason, TimeoutError) else
                    'transport' if isinstance(exc, urllib.error.URLError) else
                    {'configuration': 'configuration', 'time-budget': 'time-budget',
                     'reservation': 'budget', 'response-size': 'oversize',
                     'response-json': 'invalid-json', 'response-shape': 'invalid-message',
                     'response-metadata': 'invalid-metadata'}.get(stage, 'unexpected'))
        status = exc.code if isinstance(exc, urllib.error.HTTPError) and type(exc.code) is int and 100 <= exc.code <= 599 else -1
        logging.getLogger(__name__).warning(
            'voice_public_research_failure stage=%s category=%s http_status=%d response_bytes=%d response_limit=%d',
            stage, category, status, response_bytes, core.MAX_RESPONSE)
        if isinstance(exc, urllib.error.HTTPError):
            _log_http_error(exc, 'research')
        raise

