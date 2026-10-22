"""Authenticated server-side Gemini Live proxy. No audio persistence or browser API key."""
import asyncio
import base64
import json
import os
import re
import threading
import time
from urllib.parse import urlsplit

from fastapi import Request, WebSocket, WebSocketDisconnect
from starlette.concurrency import run_in_threadpool
from app import voice_exam_core as core

_lock = threading.Lock()
_active = set()
MAX_SECONDS = 570
PROVIDER_URL = 'wss://generativelanguage.googleapis.com/ws/google.ai.generativelanguage.v1beta.GenerativeService.BidiGenerateContent'


def live_enabled():
    return core.enabled() and os.getenv('VOICE_EXAM_LIVE_ENABLED', '1') == '1'


def same_origin(socket):
    origin = urlsplit(socket.headers.get('origin', ''))
    expected = 'https' if socket.url.scheme == 'wss' else 'http'
    return origin.scheme == expected and origin.netloc == socket.url.netloc


def setup_message(model):
    return {'setup': {'model': 'models/' + model,
        'generationConfig': {'responseModalities': ['TEXT']},
        'inputAudioTranscription': {'languageCodes': ['tr-TR']}}}


async def proxy(socket, provider):
    """One bounded PCM stream. Final and interim hypotheses stay distinct."""
    await provider.send(json.dumps(setup_message(os.getenv('VOICE_EXAM_LIVE_MODEL', 'gemini-3.5-transcribe-live'))))
    first = json.loads(await asyncio.wait_for(provider.recv(), timeout=15))
    if 'setupComplete' not in first:
        raise ValueError('Live setup failed')
    await socket.send_json({'type': 'ready'})
    finalized = asyncio.Event()

    async def upstream():
        started = time.monotonic(); total = 0
        while True:
            message = await socket.receive()
            if message['type'] == 'websocket.disconnect':
                return 'disconnect'
            audio = message.get('bytes')
            if audio is not None:
                if not audio or len(audio) > 6400 or len(audio) % 2:
                    raise ValueError('Invalid PCM frame')
                total += len(audio)
                if total > 128000 + (time.monotonic()-started)*40000:
                    raise ValueError('Audio rate exceeded')
                await provider.send(json.dumps({'realtimeInput': {'audio': {
                    'mimeType': 'audio/pcm;rate=16000', 'data': base64.b64encode(audio).decode()}}}))
            else:
                text = message.get('text', '')
                if len(text) > 200:
                    raise ValueError('Invalid control')
                control = json.loads(text)
                if control.get('type') in {'pause', 'finish'}:
                    finalized.clear()
                    await provider.send(json.dumps({'realtimeInput': {'audioStreamEnd': True}}))
                    try:
                        await asyncio.wait_for(finalized.wait(), timeout=3)
                        flushed = True
                    except asyncio.TimeoutError:
                        flushed = False
                    await socket.send_json({'type': 'ended', 'flushed': flushed})
                    return 'ended'
                raise ValueError('Unknown control')

    async def downstream():
        async for raw in provider:
            if len(raw) > 65536:
                raise ValueError('Provider message too large')
            body = json.loads(raw)
            if body.get('error') or body.get('goAway'):
                raise ValueError('Provider session ended')
            content = body.get('serverContent', {})
            for name, kind in (('interimInputTranscription', 'interim'), ('inputTranscription', 'final')):
                text = content.get(name, {}).get('text', '')
                if text:
                    if not isinstance(text, str) or len(text) > 6000:
                        raise ValueError('Transcript too large')
                    await socket.send_json({'type': kind, 'text': text})
                    if kind == 'final':
                        finalized.set()

    tasks = [asyncio.create_task(upstream()), asyncio.create_task(downstream())]
    try:
        done, pending = await asyncio.wait(tasks, timeout=MAX_SECONDS, return_when=asyncio.FIRST_COMPLETED)
        if not done:
            raise ValueError('Session limit')
        for task in done:
            task.result()
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def register_live(router):
    @router.websocket('/patients/{patient_id}/voice-exam/live')
    async def live(socket: WebSocket, patient_id: int):
        from app.voice_exam import _access
        if not live_enabled() or not same_origin(socket):
            return await socket.close(code=1008)
        scope = dict(socket.scope, type='http', method='GET', scheme='https' if socket.url.scheme == 'wss' else 'http')
        user, fingerprint, error = await run_in_threadpool(_access, Request(scope), patient_id)
        if error is not None:
            return await socket.close(code=1008)
        key = os.getenv('GEMINI_API_KEY', '')
        model = os.getenv('VOICE_EXAM_LIVE_MODEL', 'gemini-3.5-transcribe-live')
        if not key or not re.fullmatch(r'gemini-[A-Za-z0-9._-]{1,100}', model):
            return await socket.close(code=1013)
        with _lock:
            allowed = user.id not in _active and len(_active) < 4
            if allowed:
                _active.add(user.id)
        if not allowed:
            return await socket.close(code=1013)
        try:
            await socket.accept()
            initial = await asyncio.wait_for(socket.receive_text(), timeout=8)
            if len(initial) > 200 or json.loads(initial) != {'type': 'start', 'consent': True}:
                return await socket.close(code=1008)
            from websockets.asyncio.client import connect
            from app.provider_budget import reservation
            # Key only in server-side header; never in browser URL or errors.
            with reservation('gemini', model):
                async with connect(PROVIDER_URL, additional_headers={'x-goog-api-key': key},
                    open_timeout=12, close_timeout=3, max_size=65536, max_queue=8,
                    ping_interval=20, ping_timeout=20) as provider:
                    await proxy(socket, provider)
        except (WebSocketDisconnect, asyncio.CancelledError):
            pass
        except Exception:
            try:
                await socket.send_json({'type': 'error', 'message': 'Canlı bağlantı kesildi. Son konuşma bölümü eksik olabilir. Mikrofon durduruldu; devam etmek için yeniden başlat.'})
            except Exception:
                pass
        finally:
            with _lock:
                _active.discard(user.id)
            try:
                await socket.close()
            except Exception:
                pass

