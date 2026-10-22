"""Synthetic dialogue and bounded local load benchmark.

--local: real validators/controllers with explicitly simulated provider transport.
--real: actual extraction + finalization once, only when GEMINI_API_KEY exists.
--sources: independently measure actual official source cold/cache lookup.
Never load production patient records. Local timings are NOT Gemini or Render timings.
"""
import argparse
import json
import os
import resource
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import ModuleType
from unittest.mock import patch

FIXTURE = Path(__file__).resolve().parents[1] / 'tests/fixtures/voice_exam_one_minute_tr.json'


def dialogue():
    item = json.loads(FIXTURE.read_text())
    return item, '\n'.join(turn['speaker'] + ': ' + turn['text'] for turn in item['turns'])


def sample_output():
    item, text = dialogue()
    turns = item['turns']
    def field(value, i): return {'value': value, 'quote': turns[i]['text']}
    return {'transcript': text, 'fields': {
        'chief_complaint': field('Üç gündür sağ altta soğukla ağrı ve gece uyandıran ağrı', 1),
        'age': field('32', 3), 'medical_history': field('Hasta diyabet beyan ediyor', 3),
        'medications': field('Metformin; doz belirtilmedi', 3),
        'allergies': field('Adı bilinmeyen antibiyotik sonrası döküntü beyanı; netleştirilmeli', 3),
        'plan': field('Röntgen ve muayeneyi tamamlayıp tedaviye karar verme; henüz kanal kararı yok', 6)},
        'teeth': [{'tooth': '45', 'status': 'FILLING', 'quote': turns[4]['text']}],
        'appointment': {'quote': turns[8]['text'], 'acceptance_quote': 'Evet'},
        'uncertain': '44 numaradaki çürük kesin değil; antibiyotik adı bilinmiyor.',
        'communication': [{'quote': 'Vitalite ne demek?', 'observation': 'Açıklama isteği', 'suggestion': 'Testin neyi değerlendirdiğini sade anlat.'}],
        'decision_barriers': [
            {'category': 'FEAR', 'quote': 'iğneyi görünce geriliyorum', 'observation': 'İğneye ilişkin tereddüt', 'question': 'Sizi en çok hangi aşama kaygılandırıyor?', 'explanation': 'İşlemleri hastanın anlayacağı biçimde açıklayın.'},
            {'category': 'COST', 'quote': 'Ücret yüksek çıkarsa bu ay yaptıramam.', 'observation': 'Ücrete ilişkin tereddüt', 'question': 'Planı ve seçenekleri konuşmak ister misiniz?', 'explanation': 'Uygun seçenekleri ve maliyeti açıkça anlatın.'}],
        'follow_up_questions': [{'quote': 'adını bilmiyorum', 'question': 'Reaksiyon olan ilacı önceki kayıt veya kutudan doğrulayabilir miyiz?', 'reason': 'İlaç bilgisi belirsiz', 'priority': 'CLARIFY_NOW'}]}


@contextmanager
def simulated_transport(delay=0):
    """Exercise actual core.extract; do not confuse supplied outputs with AI reasoning."""
    from app import http_transport
    budget = ModuleType('app.provider_budget'); budget.reservation = lambda *args: nullcontext()
    lock = threading.Lock(); stats = {'calls': 0, 'inflight': 0, 'peak_inflight': 0}
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, limit):
            try:
                time.sleep(delay)
                return json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(sample_output())}]}}]}).encode()
            finally:
                with lock: stats['inflight'] -= 1
    def opened(*args, **kwargs):
        with lock:
            stats['calls'] += 1; stats['inflight'] += 1
            stats['peak_inflight'] = max(stats['peak_inflight'], stats['inflight'])
        return Response()
    with patch.dict(sys.modules, {'app.provider_budget': budget}), patch.dict(os.environ, {'GEMINI_API_KEY':'SYNTHETIC_NOT_A_KEY'}), patch.object(http_transport, 'urlopen', opened):
        yield stats


def percentiles(values):
    values = sorted(values)
    if not values: return None
    return {'p50_ms': round(statistics.median(values), 3), 'p95_ms': round(values[min(len(values)-1, int(len(values)*.95))], 3)}


def local():
    from app import voice_exam_core as core
    _, text = dialogue(); results = {}
    before = resource.getrusage(resource.RUSAGE_SELF)
    durations = []
    with simulated_transport():
        for _ in range(100):
            start = time.perf_counter(); core.extract(transcript=text); durations.append((time.perf_counter()-start)*1000)
    results['serial_core_with_simulated_provider'] = percentiles(durations)
    results['load'] = []
    for concurrency in (1, 10, 50):
        with simulated_transport(.02) as provider:
            def request(_):
                start=time.perf_counter()
                try: core.extract(transcript=text); ok=True
                except core.VoiceError as exc:
                    if str(exc) != 'Ses çözümleme meşgul. Kaydın korunuyor; biraz sonra tekrar dene.': raise
                    ok=False
                return ok, (time.perf_counter()-start)*1000
            start=time.perf_counter()
            with ThreadPoolExecutor(max_workers=concurrency) as pool: responses=list(pool.map(request, range(100)))
            results['load'].append({'concurrency':concurrency,'attempts':100,'accepted':sum(ok for ok,_ in responses),
                'busy_rejected':sum(not ok for ok,_ in responses),'provider_peak_inflight':provider['peak_inflight'],
                'accepted_latency':percentiles([t for ok,t in responses if ok]),
                'busy_latency':percentiles([t for ok,t in responses if not ok]),
                'batch_wall_ms':round((time.perf_counter()-start)*1000,3)})
    # Malformed/non-evidenced claims must be rejected even if the fake model supplies them.
    model = sample_output(); model['fields']['medications']={'value':'Uydurma ilaç','quote':'Konuşmada olmayan ifade'}
    results['fabricated_quote_rejected'] = 'medications' not in core.normalize(model, evidence=text)['fields']
    after=resource.getrusage(resource.RUSAGE_SELF)
    results['process_peak_rss_kib']=after.ru_maxrss
    results['peak_rss_growth_kib']=max(0,after.ru_maxrss-before.ru_maxrss)
    results['cpu_user_seconds']=round(after.ru_utime-before.ru_utime,4)
    results['scope']='LOCAL ONLY; supplied provider output and 20 ms artificial provider delay. Not an AI understanding or production capacity benchmark.'
    return results


def actual():
    if not os.getenv('GEMINI_API_KEY'): return {'status':'BLOCKED_NO_GEMINI_CREDENTIAL','semantic_checks':'NOT_RUN'}
    from app.voice_exam_core import extract
    from app.voice_exam_final import finalize
    _, text=dialogue(); start=time.perf_counter(); review=extract(transcript=text); extracted=time.perf_counter()
    final=finalize({'fields':review['fields'],'teeth':review['teeth'],'appointment':review.get('appointment',{}),'source_requests':review.get('source_requests',[])},
                   [*review.get('communication',[]),*review.get('decision_barriers',[])],review['uncertain'])
    return {'status':'REAL_PROVIDER_RETURNED','extract_ms':round((extracted-start)*1000,2),
            'final_ms':round((time.perf_counter()-extracted)*1000,2),'review':review,'final':final,
            'semantic_checks':'Inspect actual synthetic outputs against fixture expectations; no automatic claim of clinical correctness.'}


def sources():
    from app.voice_exam_live_sources import lookup, _cache
    _cache.clear(); timings=[]
    for _ in range(2):
        start=time.perf_counter()
        try:
            result=lookup('metformin'); status={'ok':True,'source_id':result['id'],'excerpts':len(result['excerpts'])}
        except Exception as exc: status={'ok':False,'error_type':type(exc).__name__}
        timings.append({**status,'ms':round((time.perf_counter()-start)*1000,2)})
    return {'cold':timings[0],'warm':timings[1]}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--local',action='store_true');parser.add_argument('--real',action='store_true')
    parser.add_argument('--sources',action='store_true');parser.add_argument('--output',type=Path)
    args=parser.parse_args();fixture,text=dialogue()
    report={'fixture':fixture['id'],'word_count':len(text.split()),'synthetic':True,'actual_audio_test':False}
    if args.real: report['real_model']=actual()
    if args.local: report['local']=local()
    if args.sources: report['official_source_access']=sources()
    encoded=json.dumps(report,ensure_ascii=False,indent=2)
    if args.output: args.output.write_text(encoded+'\n')
    print(encoded)


if __name__=='__main__':main()
