"""Explicit, synthetic-only real provider smoke test; never load patient records.

Run in an environment already holding GEMINI_API_KEY:
python -m scripts.check_voice_provider --run-paid-checks [--live]
Only pass/fail codes are printed. No keys, transcripts or clinical output are logged.
This establishes connectivity, not clinical correctness or phone microphone quality.
"""
import argparse
import asyncio
import json
import os


async def live_check():
    from websockets.asyncio.client import connect
    from app.voice_exam_live import PROVIDER_URL, setup_message
    model = os.getenv('VOICE_EXAM_LIVE_MODEL', 'gemini-3.5-transcribe-live')
    async with connect(PROVIDER_URL, additional_headers={'x-goog-api-key': os.environ['GEMINI_API_KEY']},
                       open_timeout=12, close_timeout=3, max_size=65536) as socket:
        await socket.send(json.dumps(setup_message(model)))
        response = json.loads(await asyncio.wait_for(socket.recv(), 15))
        if 'setupComplete' not in response: raise ValueError('Live setup failed')
        # Handshake only; no patient audio, physical microphone or clinical claim.


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-paid-checks', action='store_true')
    parser.add_argument('--live', action='store_true')
    args = parser.parse_args()
    if not args.run_paid_checks or not os.getenv('GEMINI_API_KEY'):
        print(json.dumps({'ok': False, 'code': 'OPT_IN_OR_PROVIDER_CREDENTIAL_MISSING'}));return 2
    try:
        from app.voice_exam_core import extract
        from app.voice_exam_final import finalize
        result = extract(transcript='Hasta: Soğuk su içince sağ alt dişim ağrıyor. Hekim: Ne zamandır? Hasta: İki gündür.')
        if not result['fields'].get('chief_complaint'): raise ValueError('No synthetic complaint')
        finalize({'fields': result['fields'], 'teeth': result['teeth']}, [], result['uncertain'])
        if args.live: asyncio.run(live_check())
    except Exception:
        print(json.dumps({'ok': False, 'code': 'SYNTHETIC_PROVIDER_CHECK_FAILED'}));return 1
    print(json.dumps({'ok': True, 'code': 'SYNTHETIC_PROVIDER_CHECK_PASSED', 'live_handshake': args.live}));return 0


if __name__ == '__main__': raise SystemExit(main())
