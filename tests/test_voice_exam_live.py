import asyncio
import json
from types import SimpleNamespace

import pytest
from app.voice_exam_live import proxy, same_origin, setup_message


@pytest.mark.parametrize('origin,scheme,expected', [
    ('https://dentalai.tr', 'wss', True),
    ('https://evil.example', 'wss', False),
    ('http://dentalai.tr', 'wss', False),
    ('', 'wss', False),
])
def test_live_requires_exact_origin(origin, scheme, expected):
    socket = SimpleNamespace(headers={'origin': origin}, url=SimpleNamespace(scheme=scheme, netloc='dentalai.tr'))
    assert same_origin(socket) is expected


def test_setup_is_transcription_only_and_contains_no_key_or_patient():
    config = setup_message('gemini-test')
    assert config['setup']['generationConfig']['responseModalities'] == ['TEXT']
    assert config['setup']['inputAudioTranscription']['languageCodes'] == ['tr-TR']
    assert set(config) == {'setup'}


class Provider:
    def __init__(self):self.queue=asyncio.Queue();self.sent=[]
    async def send(self, text):
        body=json.loads(text);self.sent.append(body)
        if 'setup' in body:await self.queue.put(json.dumps({'setupComplete': {}}))
        elif body.get('realtimeInput', {}).get('audio'):
            await self.queue.put(json.dumps({'serverContent': {'interimInputTranscription': {'text': 'Geçici'}}}))
        else:await self.queue.put(json.dumps({'serverContent': {'inputTranscription': {'text': 'Soğuk içemiyorum.'}}}))
    async def recv(self):return await self.queue.get()
    def __aiter__(self):return self
    async def __anext__(self):return await self.recv()


class Socket:
    def __init__(self, frame):self.frames=[{'type':'websocket.receive','bytes':frame},{'type':'websocket.receive','text':json.dumps({'type':'finish'})}];self.sent=[]
    async def receive(self):
        if self.frames:return self.frames.pop(0)
        await asyncio.Future()
    async def send_json(self, body):self.sent.append(body)


def test_pcm_stream_flushes_final_transcription_and_closes_tasks():
    async def scenario():
        provider=Provider();socket=Socket(b'\x00\x00'*1600)
        await asyncio.wait_for(proxy(socket,provider),2)
        assert socket.sent[0] == {'type':'ready'}
        assert {'type':'final','text':'Soğuk içemiyorum.'} in socket.sent
        assert socket.sent[-1] == {'type':'ended','flushed':True}
        audio=provider.sent[1]['realtimeInput']['audio']
        assert audio['mimeType']=='audio/pcm;rate=16000'
        assert provider.sent[-1]=={'realtimeInput':{'audioStreamEnd':True}}
    asyncio.run(scenario())


@pytest.mark.parametrize('frame',[b'x',b'x'*6402,b''])
def test_live_rejects_malformed_or_oversized_audio(frame):
    async def scenario():
        with pytest.raises(ValueError,match='PCM'):
            await proxy(Socket(frame),Provider())
    asyncio.run(scenario())
