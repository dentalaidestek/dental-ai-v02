"""Opt-in small real-model check. Sequential, no retries, at most 20 requests.

Requires GEMINI_API_KEY already configured in this shell; never prints it.
This is a smoke evaluation, NOT a general Turkish language benchmark.
"""
import argparse
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.academic_request_understanding import SYSTEM, SCHEMA, interpret_request


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--run', action='store_true', help='Actually call the paid API; absent means print estimate only')
    parser.add_argument('--limit', type=int, default=20)
    args = parser.parse_args()
    cases = json.loads((ROOT/'evaluation/academic/semantic_requests.json').read_text())[:max(1, min(20, args.limit))]
    print(json.dumps({'cases':len(cases),'model':'gemini-2.5-flash-lite',
                      'estimated_usd_at_1000_input_200_output_each': round(len(cases)*0.00018,6),
                      'includes_answer_or_OCR_cost':False,'live_calls_enabled':args.run}))
    if not args.run:
        return
    key = os.getenv('GEMINI_API_KEY','').strip()
    if not key:
        raise SystemExit('GEMINI_API_KEY is not configured; no calls made. Do not paste the key into chat.')
    successes = 0
    total_in = total_out = 0
    for idx, case in enumerate(cases,1):
        def call(prompt):
            nonlocal total_in, total_out
            payload = {'systemInstruction':{'parts':[{'text':SYSTEM}]},
                       'contents':[{'role':'user','parts':[{'text':prompt}]}],
                       'generationConfig':{'temperature':0,'maxOutputTokens':512,
                                           'responseMimeType':'application/json','responseJsonSchema':SCHEMA}}
            request = urllib.request.Request('https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent',
                data=json.dumps(payload).encode(),method='POST',headers={'Content-Type':'application/json','x-goog-api-key':key})
            try:
                with urllib.request.urlopen(request,timeout=8) as response:
                    data = json.load(response)
            except urllib.error.HTTPError as exc:
                # Provider error bodies can echo sensitive input; omit them.
                raise RuntimeError('API HTTP status '+str(exc.code)) from None
            usage = data.get('usageMetadata',{})
            total_in += usage.get('promptTokenCount',0)
            total_out += usage.get('candidatesTokenCount',0)+usage.get('thoughtsTokenCount',0)
            return ''.join(p.get('text','') for p in data.get('candidates',[{}])[0].get('content',{}).get('parts',[]))
        started = time.perf_counter()
        result = interpret_request(case['query'],case['history'],call=call)
        plan = result.plan
        passed = bool(plan and plan.operation == case['operation']
                      and (case['scope'] is None or plan.scope == case['scope'])
                      and plan.count == case['count']
                      and all(t.casefold() in plan.resolved_query.casefold() for t in case['terms']))
        successes += passed
        print(json.dumps({'case':idx,'pass':passed,'outcome':result.outcome,
                          'elapsed_ms':round((time.perf_counter()-started)*1000),
                          'plan':plan.__dict__ if plan else None},ensure_ascii=False))
    print(json.dumps({'passed':successes,'total':len(cases),'input_tokens':total_in,
                      'output_tokens':total_out,'estimated_token_usd':(total_in*0.10+total_out*0.40)/1_000_000,
                      'requires_human_semantic_review':True}))


if __name__=='__main__':
    main()
