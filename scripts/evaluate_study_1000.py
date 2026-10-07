"""Frozen 1000-case study routing audit; never claims end-to-end accuracy.

Gold is authored independently of output. Inputs are synthetic Turkish study
conversations; no private conversation corpus, SQL, Gemini or browser is used.
Run --freeze once, then evaluate the stored cases without changing gold.
"""
from __future__ import annotations
import argparse, hashlib, json, re, runpy, sys, time
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
FOLD=str.maketrans('çğıöşüÇĞİÖŞÜ','cgiosuCGIOSU')

def norm(text):return ' '.join(str(text or '').translate(FOLD).lower().split())
def present(text,term):
    # Exact canonical aliases are equivalent; retain clinical subtypes.
    # Generic cyst is intentionally NOT accepted for dentigerous cyst.
    if norm(term)=='sefalometrik' and any(present(text,alias) for alias in ('sefalometri','cephalometry')):
        return True
    text=str(text).replace('_',' ')
    return bool(re.search(r'(?<!\w)'+re.escape(norm(term))+r'(?:i|u|in|un|ini|unu|nin|nun|nini|nunu|si|su|sini|sunu|sinin|sunun|a|e|ya|ye|da|de|ta|te|dan|den|tan|ten|lar|ler|lari|leri|larda|lerde|lardan|lerden|larin|lerin)?(?!\w)',norm(text)))
def msg(role,text):return {'role':role,'content':text}

def generate():
    # Each scenario pairs a different subject/reference/count/qualifier and
    # request style. 20 families are not 1000 independent product features.
    topics=[('flor kullanımı','flor'),('pulpitis','pulpitis'),('apikal periodontitis','apikal'),
      ('Nance apareyi','nance'),('Downs analizi','downs'),('ANB açısı','anb'),
      ('SNA açısı','sna'),('SNB açısı','snb'),('implant stabilitesi','implant'),
      ('lokal anestezi','anestezi'),('alveolit','alveolit'),('gingivitis','gingivitis'),
      ('bruksizm','bruksizm'),('perikoronitis','perikoronitis'),('osteomiyelit','osteomiyelit'),
      ('pulpotomi','pulpotomi'),('pulpektomi','pulpektomi'),('MTA kullanımı','mta'),
      ('EDTA irrigasyonu','edta'),('sodyum hipoklorit','hipoklorit'),('apeksifikasyon','apeksifikasyon'),
      ('rejeneratif endodonti','rejeneratif'),('cam iyonomer siman','iyonomer'),('kompozit rezin','kompozit'),
      ('fissür örtücü','fissur'),('yer tutucu','tutucu'),('Bolton analizi','bolton'),('Wits analizi','wits'),
      ('Spee eğrisi','spee'),('Wilson eğrisi','wilson'),('Bennett açısı','bennett'),
      ('overjet','overjet'),('overbite','overbite'),('crossbite','crossbite'),('sefalometrik analiz','sefalometrik'),
      ('oral lökoplaki','lokoplaki'),('oral kandidiyazis','kandidiyazis'),('liken planus','liken'),
      ('aftöz ülser','aftoz'),('dentigeröz kist','dentigeroz'),('odontojenik keratokist','keratokist'),
      ('odontoma','odontoma'),('ameloblastoma','ameloblastoma'),('internal rezorpsiyon','rezorpsiyon'),
      ('furkasyon lezyonları','furkasyon'),('kök yüzeyi düzleştirme','duzlestirme'),
      ('mandibula kondil kırığı','kondil'),('inferior alveolar sinir','alveolar'),
      ('mental foramen','mental'),('maksiller sinüs','sinus')]
    rows=[]
    prefixes=('','Kral ','Hocam ','Ya ','Rica etsem ')
    scope=('Bu ders notlarını','Bütün slaytları','Bu dersin tamamını','Notların hepsini','Ders notlarını')
    styles=('sınav odaklı','yüksek verimli şekilde','ana başlıkları atlamadan','kısa ve anlaşılır','madde madde',
            'kritik ayrıntılarıyla','baştan sona','mantığını kurarak','örneklerle','ayrıntılı')
    feedback=('sen dalga mı geçiyorsun','beni anlamıyorsun','aynı şeyi yazıp duruyorsun','alakasız cevap verdin',
              'ben bunu istemedim','yine aynı cevabı verdin','ne diyorsun ya','dalga mı geçiyosun',
              'beni anlamıyosun','yanlış cevap verdin')
    outline=('Her başlığı tek bir paragrafla anlat','Başlıkları atlama','Hepsini madde madde anlat',
             'Kalan başlıkları da açıkla','Her konuyu ayrı ayrı anlat','Her başlığı 3 cümleyle açıkla',
             'Başlık başlık git','Her başlık için bir paragraf yaz','Her başlığı tablo halinde göster',
             'Her başlığı tek bir oaragrafla anlat')
    depths=('daha ayrıntılı anlat','adam gibi anlat','kafama oturmadı','anlamıyom','bunu biraz aç',
            'ezber değil mantığını anlat','şunu tane tane anlat','örnekle anlat','kısa kesme ayrıntıya gir',
            'bu çok yüzeysel her başlığı açıkla')
    priorities=('Hoca nerden sorabilir','Sınavda ne çıkar','Hoca hangi konulardan sorar','Öğretmen ne sorabilir',
                'Hocanın nereden sorabileceğini anlat','En kritik yerleri ayır','Sınav için önemli noktaları çıkar',
                'Hoca nasıl sorar','Buradan nasıl soru çıkar','Neye daha çok çalışayım')
    markings=('Hocanın altını çizdiği yerler var mı','Notlarda altı çizili yerler nerede',
              'Slaytlarda işaretli yerler var mı','Hocanın özellikle vurguladığı noktaları göster',
              'Bence burdan gelmez hocanın özellikle vurguladığı işaretli yerler var mı',
              'Hangi sayfalarda hoca işaret koymuş','Kırmızıyla yazılan yerleri getir',
              'Yıldız konmuş başlıklar hangileri','Hocanın önemli dediği yerleri bul','Kalın yazılmış kısımları göster')
    for i,(topic,key) in enumerate(topics):
        previous,previous_key=topics[(i+7)%len(topics)]
        old=[msg('USER',previous+' anlat'),msg('ASSISTANT','Önceki konu açıklaması.')]
        history=[msg('USER',topic+' anlat'),msg('ASSISTANT',f'{topic} açıklaması. {previous} ilgisiz bir örnektir.')]
        course=[msg('USER','Bu ders notlarını özetle'),msg('ASSISTANT',f'1. {topic}\n2. {previous}')]
        quiz=[msg('USER',topic+' hakkında bir soru sor'),msg('ASSISTANT',f'Soru 1\n{topic} için hangi bilgi doğrudur?\nA) Seçenek bir\nB) Seçenek iki\nC) Seçenek üç')]
        batch=old+[msg('USER',f'{topic} hakkında {i+2} soru hazırla'),
                   msg('ASSISTANT','\n\n'.join(f'Soru {n}\n{topic} için klinik soru {n} nedir?\nA) a\nB) b\nC) c' for n in range(1,i+3)))]
        def add(family,q,h,gold,dimension):
            rows.append({'id':f'{family}-{i+1:02d}','family':family,'query':q,'history':h,
                         'gold':gold,'dimension':dimension,'provenance':'authored synthetic Turkish study scenario'})
        control=prefixes[i%5]+scope[i%5]+' '+styles[i//5]+' '
        add('course_summary',control+'özetle',old,{'course':True,'task':'summarize'},'source/manner/stale-topic')
        add('course_teaching',control+'öğret',old,{'course':True,'task':'explain'},'source/depth/stale-topic')
        add('course_quiz',f'{scope[i%5]} kullanarak {i+1} zorlayıcı soru hazırla; cevap anahtarını gösterme',old,
            {'course':True,'generate':True,'count':i+1},'source/count/hidden-key')
        add('named_definition',prefixes[i%5]+topic+' nedir?',old,{'current':key,'no_context':previous_key},'named-topic/definition')
        add('named_procedure',topic+' nasıl uygulanır, hangi durumlarda kullanılır?',old,
            {'current':key,'no_context':previous_key,'facets':['treatment','indication']},'named-topic/multiple-facets')
        add('named_numeric_fact',topic+' için notlarda geçen sayısal değerleri ve birimlerini açıkla',old,
            {'current':key,'no_context':previous_key},'named-topic/numeric-evidence')
        add('outline_format',prefixes[i//10]+outline[i%10],history,{'inherited':key,'task':'explain','no_quiz_answer':True},'scope/manner/verb')
        add('depth_repair',prefixes[i//10]+depths[i%10],history,{'inherited':key,'task':'explain','no_quiz_answer':True},'comprehension/depth')
        add('exam_priorities',prefixes[i//10]+priorities[i%10],history,{'inherited':key,'task':'exam_points'},'exam-selection/style')
        add('source_markings',prefixes[i//10]+markings[i%10],course,{'course':True,'visual':True},'source-markings/not-prediction')
        answer=('A','Cevabım B','Bence C','A şıkkı','Çürüğü önlemek için')[i%5]
        add('single_quiz_answer',answer,quiz,{'reference':True,'inherited':key},'actual-pending-question/answer-style')
        n=i+2
        add('grouped_quiz_answers',f'Cevaplarım 1A, {n}B',batch,{'grouped':[1,n],'inherited':key},'batch/reference/count')
        add('ordinal_quiz_reference',f'{n}. soruyu daha ayrıntılı açıkla',batch,{'inherited':key,'selected_text':f'klinik soru {n}'},'ordinal/factual-stem/distractors')
        chain=history+[msg('USER',previous+' anlat'),msg('ASSISTANT','Yeni konunun açıklaması.')]
        add('return_previous_topic',prefixes[i%5]+'Bir önceki konuya dön, daha basit anlat',chain,{'inherited':key,'no_context':previous_key},'two-topic/relative-reference')
        add('topic_switch_during_quiz','Şimdi '+previous+' konusuna geçelim',quiz,{'current':previous_key,'no_context':key,'no_quiz_answer':True},'new-topic/not-grading')
        add('qualifier_replacement',f'Çocukları değil erişkinleri kastediyorum, {topic} için aynı şeyi anlat',
            [msg('USER','Çocuklarda '+topic+' anlat')],{'current':key,'qualifier':'eriskin','forbidden_qualifier':'cocuk'},'age/negation/topic-retention')
        add('multipart_request',topic+' tanımını anlat, neden oluştuğunu açıkla ve nasıl tedavi edildiğini söyle',old,
            {'current':key,'no_context':previous_key,'facets':['definition','cause','treatment']},'multiple-facets/one-turn')
        add('unknown_topic',f'Zorbital{i+1} sendromunu notlara göre anlat',history,
            {'current':f'zorbital{i+1}','no_context':key},'unknown-noun/no-stale-inheritance')
        add('unbound_reference',prefixes[i//10]+depths[i%10],[],{'clarify':True},'missing-topic/no-guessed-context')
        add('frustration',prefixes[i//10]+feedback[i%10],quiz,{'repair':True,'no_quiz_answer':True},'speech-act/pending-quiz-preservation')
    return rows


def run(cases):
    from app import study_retrieval_v2 as r
    from app.dental_query_intent import build_dental_requirement_plan as plan,classify_academic_study_task as task,classify_dental_study_plan
    from app.academic_dialogue import active_question_reference,numbered_answer_references
    from app.academic_request_slots import conversational_repair
    results=[];started=time.perf_counter()
    for case in cases:
        q=case['query'];h=case['history'];gold=case['gold'];checks={}
        try:
            resolved=r.resolve_followup_query(q,h);p=plan(resolved);t=task(resolved)
            context=resolved.rsplit(' — ',1)[0] if ' — ' in resolved else ''
            searchable=' '.join([*p.subject_terms,*p.subject_node_ids,context])
            scope=r._course_coverage_requested(resolved,p,t)
            if 'course' in gold:checks['course_scope']=scope==gold['course'] and not p.subject_terms and not p.subject_node_ids
            if 'task' in gold:checks['task']=bool(t and t.task==gold['task'])
            if 'generate' in gold:checks['generation']=bool(t and t.generate_new_questions)
            if 'count' in gold:
                study=classify_dental_study_plan(resolved);checks['count']=bool(study and study.count==gold['count'])
            if 'current' in gold:checks['named_subject']=present(searchable,gold['current'])
            if 'inherited' in gold:checks['context_reference']=bool(context and present(context,gold['inherited']))
            if 'no_context' in gold:checks['no_stale_context']=not present(context,gold['no_context'])
            if gold.get('no_quiz_answer'):checks['not_grading']=active_question_reference(q,h) is None
            if gold.get('visual'):checks['visual_source']=p.requires_visual_source
            if gold.get('reference'):checks['actual_question_reference']=active_question_reference(q,h) is not None
            if 'grouped' in gold:checks['grouped_reference']=[ref.number for ref in numbered_answer_references(q,h)]==gold['grouped']
            if 'selected_text' in gold:checks['selected_stem']=gold['selected_text'] in context
            if 'facets' in gold:checks['facets']=set(gold['facets']).issubset(p.requested_facets)
            if 'qualifier' in gold:checks['qualifier']=gold['qualifier'] in {norm(v) for v in p.qualifiers}
            if 'forbidden_qualifier' in gold:checks['no_stale_qualifier']=gold['forbidden_qualifier'] not in {norm(v) for v in p.qualifiers}
            if gold.get('repair'):checks['conversation_repair']=conversational_repair(q)
            if gold.get('clarify'):
                from types import SimpleNamespace
                def reject_candidates(*args,**kwargs):
                    raise AssertionError('Unbound subjectless request attempted candidate access')
                session=SimpleNamespace(get_bind=lambda:SimpleNamespace(dialect=SimpleNamespace(name='postgresql')),exec=reject_candidates)
                try:
                    from unittest.mock import patch
                    with patch.object(r,'text',side_effect=AssertionError('Unbound request constructed candidate SQL'),create=True):
                        output=r.retrieve_course_context_v2(session,owner_user_id=1,course_id=3,query=q)
                    checks['unbound_clarification']=output.retrieval_mode=='clarification' and bool(output.clarification)
                except AssertionError:
                    checks['unbound_clarification']=False
            result={**case,'resolved':resolved,'subject_terms':p.subject_terms,'subject_nodes':p.subject_node_ids,
                    'task':t.task if t else None,'facets':p.requested_facets,'qualifiers':p.qualifiers,'checks':checks,
                    'passed':bool(checks) and all(checks.values())}
        except Exception as error:result={**case,'checks':{'execution':False},'passed':False,'error':f'{type(error).__name__}: {error}'}
        results.append(result)
    families={}
    for family in sorted({case['family'] for case in cases}):
        group=[row for row in results if row['family']==family];passed=sum(row['passed'] for row in group)
        families[family]={'total':len(group),'passed':passed,'failed':len(group)-passed,'percent':round(100*passed/len(group),1)}
    failed_checks=Counter(key for row in results for key,value in row['checks'].items() if not value)
    passed=sum(row['passed'] for row in results)
    return {'scope':'local intent/context/reference audit of draft code; no live SQL or generation',
            'total':len(results),'passed':passed,'failed':len(results)-passed,'percent':round(100*passed/len(results),1),
            'elapsed_seconds':round(time.perf_counter()-started,3),'categories':families,'failed_checks':dict(failed_checks),
            'production_end_to_end':{'tested':0,'unverified':len(results),'percent':None,'reason':'No authorized DentalAI browser session or database/provider credentials in this environment.'},
            'gold_policy':'Authored before evaluation; every assertion must pass. Unreviewed flags are not automatically confirmed product defects. No fixes or gold edits during this run.',
            'diversity':'1000 distinct input+history+gold scenarios, 20 behavior families, 50 subject/count/reference positions; not 1000 independent product features.',
            'cases':results}


def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--freeze',action='store_true')
    ap.add_argument('--language-only',action='store_true');ap.add_argument('--cases',default='tests/academic_v2/study_1000_cases.json')
    ap.add_argument('--report',default='artifacts/study-1000-report.json');args=ap.parse_args()
    path=ROOT/args.cases
    if args.freeze:
        if path.exists():raise SystemExit('Frozen corpus already exists; will not overwrite gold.')
        cases=generate();assert len(cases)==1000
        assert len({json.dumps([row['query'],row['history'],row['gold']],ensure_ascii=False,sort_keys=True) for row in cases})==1000
        path.write_text(json.dumps(cases,ensure_ascii=False,indent=2));print('Frozen 1000 distinct scenarios.');return
    cases=json.loads(path.read_text());assert len(cases)==1000
    sys.path.insert(0,str(ROOT))
    if args.language_only:runpy.run_path(str(ROOT/'tests/academic_v2/language_probe.py'))
    report=run(cases);report['unique_query_texts']=len({case['query'] for case in cases})
    report['unique_scenarios']=len({json.dumps([case['query'],case['history'],case['gold']],ensure_ascii=False,sort_keys=True) for case in cases})
    report['scorer_revision']='3: exact canonical aliases, finite Turkish nominal suffixes, explicit unbound candidate-access assertion; no app/gold changes'
    report['code_commit']='94e4154836085e32444d19de2ea4b6814ca78f4e (draft; app code unchanged during measurement)'
    report['scorer_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    report['component_sha256']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'app').glob('*.py')}
    report['corpus_sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    dest=ROOT/args.report;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    summary=dest.with_suffix('.md')
    lines=['1000 senaryonun yerel niyet/bağlam testi', '',f"Sonuç: {report['passed']}/1000 (%{report['percent']}); başarısız/inceleme gereken: {report['failed']}.",
           '', 'Bu oran canlı retrieval/cevap doğruluğu değildir. SQL, gerçek chunk seçimi, kaynak yeterliliği, Gemini cevabı ve girişli /ask-stream doğrulanmadı.',
           '', '| Kategori | Geçti | Toplam | % |','|---|---:|---:|---:|']
    for name,data in report['categories'].items():lines.append(f"| {name} | {data['passed']} | {data['total']} | {data['percent']} |")
    lines+=['','Başarısız kontrol türleri: '+json.dumps(report['failed_checks'],ensure_ascii=False),
            '', 'Beklentiler ölçüm öncesinde donduruldu. Bütün kontroller geçmeden senaryo başarılı sayılmadı. İşaretlenenler kök sebep/gold incelemesi gerektirir.',
            '', f"Farklı soru metni: {report['unique_query_texts']}; soru + geçmiş + beklenti bakımından farklı senaryo: {report['unique_scenarios']}. Aynı kısa cevap/komutun farklı bağlamlarda davranışı da ölçüldü.",
            '', 'Canlı uçtan uca doğrulanan: 0/1000. Üretim doğruluk yüzdesi: ölçülmedi.']
    summary.write_text('\n'.join(lines)+'\n')
    print(json.dumps({key:value for key,value in report.items() if key not in {'cases','component_sha256'}},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
