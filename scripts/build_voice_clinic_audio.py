#!/usr/bin/env python3
"""Reproducible synthetic 90s Turkish clinic test audio, not real microphone data.

Optional test-only dependency: espeakng-loader==0.2.4; ffmpeg on PATH.
Speech is synthetic, not a human/naturalness benchmark. Noise simulates a clinic;
it is not a field recording. No patient or downloaded audio is used.
"""
import argparse
import array
import ctypes as c
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import tempfile
import wave


def write_wave(path, samples, rate):
    pcm = array.array('h', (round(max(-1., min(1., x)) * 32767) for x in samples))
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1); f.setsampwidth(2); f.setframerate(rate); f.writeframes(pcm.tobytes())


def read_wave(path):
    with wave.open(str(path), 'rb') as f:
        assert f.getnchannels() == 1 and f.getsampwidth() == 2
        return f.getframerate(), [x / 32768 for x in array.array('h', f.readframes(f.getnframes()))]


def speech_engine():
    import espeakng_loader as e
    lib = c.CDLL(e.get_library_path())
    lib.espeak_Initialize.argtypes = [c.c_int, c.c_int, c.c_char_p, c.c_int]
    lib.espeak_Initialize.restype = c.c_int
    rate = lib.espeak_Initialize(2, 0, str(Path(e.get_data_path()).parent).encode(), 0x8000)
    if rate <= 0: raise RuntimeError('speech_init_failed')
    parts = []
    cbtype = c.CFUNCTYPE(c.c_int, c.POINTER(c.c_short), c.c_int, c.c_void_p)
    @cbtype
    def callback(samples, n, events):
        if samples and n: parts.append(c.string_at(samples, n * 2))
        return 0
    lib.espeak_SetSynthCallback.argtypes = [cbtype]; lib.espeak_SetSynthCallback(callback)
    lib.espeak_SetVoiceByName.argtypes = [c.c_char_p]
    lib.espeak_SetParameter.argtypes = [c.c_int, c.c_int, c.c_int]
    lib.espeak_Synth.argtypes = [c.c_void_p, c.c_size_t, c.c_uint, c.c_int, c.c_uint, c.c_uint, c.c_void_p, c.c_void_p]
    voices = {'Hasta': b'tr+m2', 'Hekim': b'tr+m3', 'Asistan': b'tr+f4', 'Ebeveyn': b'tr+f2'}
    def synth(turn, index):
        parts.clear()
        if lib.espeak_SetVoiceByName(voices[turn['speaker']]) != 0: raise RuntimeError('voice_unavailable')
        lib.espeak_SetParameter(1, 174 + (index % 3) * 3, 0)
        text = turn['text'].encode() + b'\0'
        if lib.espeak_Synth(text, len(text), 0, 1, 0, 1, None, None) != 0: raise RuntimeError('synthesis_failed')
        lib.espeak_Synchronize()
        # Keep callback alive in closure throughout all calls.
        assert callback
        return [x / 32768 for x in array.array('h', b''.join(parts))]
    return rate, synth


def clinic_noise(length, rate, seed):
    rng = random.Random(seed)
    noise = []; low = 0.
    # Continuous ventilation/room rumble plus intermittent distant handpiece-like
    # whine and small tray clicks. No lexical background speech is fabricated.
    for i in range(length):
        t = i / rate
        low = .985 * low + .015 * rng.gauss(0, 1)
        x = 3.8 * low + .025 * rng.gauss(0, 1)
        x += .028 * math.sin(2 * math.pi * 80 * t) + .012 * math.sin(2 * math.pi * 160 * t)
        for onset in (17., 43., 68.):
            dt = t - onset
            if 0 <= dt < 1.2:
                x += .025 * math.sin(math.pi * dt / 1.2)**2 * math.sin(2 * math.pi * 2400 * t)
        for onset in (11., 36., 61., 80.):
            dt = t - onset
            if 0 <= dt < .07:
                x += .07 * math.exp(-dt * 65) * math.sin(2 * math.pi * 3200 * t)
        noise.append(x)
    return noise


def build(fixture, output):
    data = json.loads(Path(fixture).read_text())
    if data.get('synthetic') is not True: raise ValueError('synthetic_fixture_required')
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    rate, synth = speech_engine(); manifest = []
    for index, case in enumerate(data['cases']):
        pcm = [0.] * int(.2 * rate)
        for j, turn in enumerate(case['dialogue']):
            pcm.extend(synth(turn, j)); pcm.extend([0.] * int((.22 + .04 * (j % 3)) * rate))
        raw_seconds = len(pcm) / rate
        speed = raw_seconds / 88.5
        if not .65 <= speed <= 1.7: raise ValueError('unnatural_time_fit:' + case['id'])
        with tempfile.TemporaryDirectory() as temp:
            raw = Path(temp) / 'raw.wav'; fitted = Path(temp) / 'fitted.wav'
            write_wave(raw, pcm, rate)
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(raw), '-af', f'atempo={speed:.9f}', str(fitted)], check=True)
            actual_rate, speech = read_wave(fitted)
        assert actual_rate == rate
        # Reject overflow instead of cutting any spoken words to fit the limit.
        if len(speech) > int(89.5 * rate): raise ValueError('speech_would_be_truncated')
        speech.extend([0.] * (90 * rate - len(speech)))
        active = [x for x in speech if abs(x) > .01]
        if not active: raise ValueError('empty_speech')
        speech_rms = math.sqrt(sum(x*x for x in active) / len(active))
        snr = 18 if index % 2 == 0 else 14
        noise = clinic_noise(len(speech), rate, 902600 + index)
        noise_rms = math.sqrt(sum(x*x for x in noise) / len(noise))
        gain = speech_rms * 10 ** (-snr / 20) / noise_rms
        noise = [x * gain for x in noise]
        mixed = [a+b for a,b in zip(speech, noise)]
        scale = .9 / max(max(abs(x) for x in mixed), max(abs(x) for x in speech))
        clean = output / (case['id'] + '-clean.wav'); noisy = output / (case['id'] + '-clinic.wav')
        write_wave(clean, (x*scale for x in speech), rate)
        write_wave(noisy, (x*scale for x in mixed), rate)
        row = {'case_id': case['id'], 'seconds':90., 'sample_rate':rate, 'channels':1,
               'speech_engine':'espeakng-loader==0.2.4', 'speech_type':'synthetic',
               'noise_type':'synthetic ventilation, low hum, distant tool and tray clicks',
               'noise_seed':902600+index, 'snr_db_active_speech':snr, 'raw_seconds':round(raw_seconds,3),
               'time_fit_factor':round(speed,6), 'role_labels_spoken':False, 'human_recording':False,
               'truncated_speech':False, 'clean_file':clean.name, 'noisy_file':noisy.name,
               'clean_sha256':hashlib.sha256(clean.read_bytes()).hexdigest(),
               'noisy_sha256':hashlib.sha256(noisy.read_bytes()).hexdigest()}
        manifest.append(row); print(json.dumps(row, ensure_ascii=False), flush=True)
    (output/'manifest.json').write_text(json.dumps({'synthetic':True,'cases':manifest},ensure_ascii=False,indent=2)+'\n')
    return manifest


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',default='tests/fixtures/voice_clinic90_dialogues.json')
    parser.add_argument('--output',required=True)
    args=parser.parse_args();build(args.fixture,args.output)
