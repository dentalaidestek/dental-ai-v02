"""Server-owned practice keys. No extra model call to grade a stored set."""
import hashlib
import json
import re
from app.academic_question_output import question_blocks, question_stem, same_question, question_set_issues

QUIZ_SCHEMA = {'type':'object','properties':{'questions':{'type':'array','items':{
    'type':'object','properties':{
        'stem':{'type':'string'},
        'options':{'type':'array','items':{'type':'string'},'minItems':5,'maxItems':5},
        'correct':{'type':'string','enum':list('ABCDE')},
        'rationale':{'type':'string'},
        'fact':{'type':'string','description':'Canonical source fact being tested; reuse the same wording for the same fact.'},
        'source':{'type':'string','description':'Filename and page supporting the correct choice.'},
        'material_id':{'type':'integer'},'page':{'type':'integer'}},
    'required':['stem','options','correct','rationale','fact','source','material_id','page'],'additionalProperties':False}}},
    'required':['questions'],'additionalProperties':False}

CONTRACT_PROMPT = '''\nSORU VERİ SÖZLEŞMESİ: Yalnız JSON questions üret. Her soruda stem, tam beş options (A–E sırasıyla, harf öneki olmadan), correct (A–E), rationale, fact, source, material_id ve page olsun. material_id/page verilen kanıtta bulunmalı. Kaynak bilgisini dosya/sayfa olarak yaz. fact sorulan tek olgunun kısa, kanonik ifadesidir; önceki fact ile aynı bilgiyi yeniden sorma. rationale doğru şıkkı kaynakla açıklar; kaynaktan doğrulanmayan cevap anahtarı üretme. Doğru şık pozitif soru kökünde aynen yazılı olmasın. Çeldiriciler aynı kavram düzeyinde, makul ve benzer uzunlukta olsun; bariz mutlak ifadelerle zorluğu düşürme. Kök, seçenekler ve tek doğru cevap birbiriyle tutarlı olsun. Anahtarın kullanıcıya gösterimini uygulama yapar.\n'''


def parse_quiz(raw, count, history=(), evidence=None):
    data=json.loads(raw)
    if not isinstance(data,dict) or set(data)!={'questions'} or not isinstance(data['questions'],list):
        raise ValueError('invalid quiz structure')
    questions=data['questions']
    if not 1<=len(questions)<=200 or (type(count) is int and len(questions)!=count):
        raise ValueError('invalid quiz count')
    previous=[q['fact'] for h in history for q in (h.get('quiz') or {}).get('questions',[])]
    allowed={(e.material_id,p):e.display_name for e in (evidence or []) for p in range(e.page_start,e.page_end+1)}
    seen=[]
    for q in questions:
        if not isinstance(q,dict) or set(q)!={'stem','options','correct','rationale','fact','source','material_id','page'}:
            raise ValueError('invalid quiz question')
        if any(not isinstance(q[k],str) or not q[k].strip() or len(q[k])>4000 for k in ('stem','rationale','fact','source')):
            raise ValueError('invalid quiz text')
        if type(q['material_id']) is not int or type(q['page']) is not int or q['page']<1:
            raise ValueError('invalid quiz source')
        key=(q['material_id'],q['page'])
        if evidence is not None:
            if key not in allowed:
                raise ValueError('quiz source outside selected evidence')
            q['source']=f'{allowed[key]}, sayfa {key[1]}'
        opts=q['options']
        if not isinstance(opts,list) or len(opts)!=5 or any(not isinstance(x,str) or not x.strip() or len(x)>2000 for x in opts):
            raise ValueError('invalid quiz options')
        if len({question_stem(x) for x in opts})!=5 or q['correct'] not in list('ABCDE'):
            raise ValueError('invalid quiz key')
        fact=question_stem(q['fact'])
        if any(same_question(fact,question_stem(old)) for old in previous+seen):
            raise ValueError('repeated quiz fact')
        seen.append(q['fact'])
        stem=question_stem(q['stem'])
        correct=question_stem(opts['ABCDE'.index(q['correct'])])
        negative={'yanlis','yanlistir','degil','degildir','haric'}
        if len(correct.split())>=2 and len(correct)>=12 and not (set(stem.split()) & negative) and f' {correct} ' in f' {stem} ':
            raise ValueError('quiz answer exposed in stem')
    if question_set_issues(render_quiz(data),count,history):
        raise ValueError('repeated quiz stem')
    return data


def render_quiz(quiz, show_answers=False):
    blocks=[]
    for n,q in enumerate(quiz['questions'],1):
        blocks.append(f"### Soru {n}\n{q['stem']}\n\n"+'\n\n'.join(f'{letter}) {text}' for letter,text in zip('ABCDE',q['options'])))
    if show_answers:
        blocks.append('### Cevap anahtarı\n'+'\n'.join(f"{n}. {q['correct']} — {q['rationale']} ({q['source']})" for n,q in enumerate(quiz['questions'],1)))
    return '\n\n'.join(blocks)


def answer_hash(answer):
    return hashlib.sha256(answer.encode()).hexdigest()


def pack_evidence(evidence_json, quiz, answer, versions):
    if not quiz:
        return evidence_json
    return json.dumps({'sources':json.loads(evidence_json),'quiz':quiz,
        'answer_hash':answer_hash(answer),'versions':versions},ensure_ascii=False)


def restore_quizzes(history, rows, versions):
    """Metadata only from owned DB rows, exact saved answer and current index."""
    expected=json.loads(json.dumps(versions))
    for item,row in zip(history,rows):
        if str(item.get('role','')).upper()!='ASSISTANT':
            continue
        try:
            data=json.loads(row.source_evidence_json or 'null')
            if (isinstance(data,dict) and data.get('versions')==expected
                    and data.get('answer_hash')==answer_hash(item['content'])):
                quiz=data.get('quiz')
                # Revalidate persisted schema without comparing against itself.
                parse_quiz(json.dumps(quiz),len(quiz['questions']))
                item['quiz']=quiz
        except (ValueError,TypeError,KeyError,AttributeError):
            continue


def grade_previous_quiz(history, answers):
    # Nearest assistant question set only. Never silently grade an older set.
    for item in reversed(history or []):
        if str(item.get('role','')).upper()!='ASSISTANT':
            continue
        if question_blocks(item.get('content') or ''):
            quiz=item.get('quiz')
            break
    else:
        quiz=None
    if not quiz:
        return 'Bu soru setinin doğrulanmış cevap anahtarı kayıtlı değil. Soruları kaynaklarıyla yeniden doğrulamadan puanlayamam.'
    questions=quiz['questions']
    given=dict(answers)
    if any(n>len(questions) for n in given):
        return 'Yanıt numaraları son soru setinin sınırları dışında. Son set için cevaplarını soru numaralarıyla gönder.'
    rows=[];correct=wrong=blank=0
    for n,q in enumerate(questions,1):
        choice=given.get(n)
        if choice is None:
            blank+=1;status='Boş'
        elif choice==q['correct']:
            correct+=1;status='Doğru'
        else:
            wrong+=1;status='Yanlış'
        rows.append(f"| {n} | {choice or '—'} | {q['correct']} | {status} |")
    table='| Soru | Yanıtın | Anahtar | Sonuç |\n|---|---|---|---|\n'+'\n'.join(rows)
    explanations='\n\n'.join(f"**Soru {n}:** {q['rationale']} ({q['source']})" for n,q in enumerate(questions,1))
    return f'{table}\n\nToplam {len(questions)} soru: {correct} doğru, {wrong} yanlış, {blank} boş.\n\n{explanations}'
