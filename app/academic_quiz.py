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
        'fact':{'type':'string','description':'Source-supported knowledge tested, including the distinct claims of a multi-statement question; reuse the same wording for the same knowledge.'},
        'source':{'type':'string','description':'Filename and page supporting the correct choice.'},
        'material_id':{'type':'integer'},'page':{'type':'integer'}},
    'required':['stem','options','correct','rationale','fact','source','material_id','page'],'additionalProperties':False}}},
    'required':['questions'],'additionalProperties':False}

CONTRACT_PROMPT = '''\nSORU VERİ SÖZLEŞMESİ: Yalnız JSON questions üret. Her soruda stem, tam beş options (A–E sırasıyla, harf öneki olmadan), correct (A–E), rationale, fact, source, material_id ve page olsun. material_id/page verilen kanıtta bulunmalı. Kaynak bilgisini dosya/sayfa olarak yaz. fact sorunun sınadığı bilginin kısa, kanonik ifadesidir; öncüllü soruda farklı öncülleri tek bir tanıma indirgeme. Önceki fact ile aynı bilgiyi yeniden sorma. Öncüllü biçim istenmişse stem içinde ayrı satırlarda I., II., III. bulunmalı; options bunların kombinasyonları olmalıdır. Güncel düzeltme mesajında önceki etkin isteğin adet, ana başlık çeşitliliği, alt başlık ve zorluk koşullarını da koru. rationale doğru şıkkı kaynakla açıklar; kaynaktan doğrulanmayan cevap anahtarı üretme. Doğru şık pozitif soru kökünde aynen yazılı olmasın. Çeldiriciler aynı kavram düzeyinde, makul ve benzer uzunlukta olsun; bariz mutlak ifadelerle zorluğu düşürme. Kök, seçenekler ve tek doğru cevap birbiriyle tutarlı olsun. Anahtarın kullanıcıya gösterimini uygulama yapar.\n'''


_quality=QUIZ_SCHEMA['properties']['questions']['items']
_quality['properties'].update({
    'topic':{'type':'string','description':'Distinct broad source topic, not a cosmetic title.'},
    'asked_truth':{'type':'boolean','description':'True if the stem asks for true statements, false if it asks for false statements. True for ordinary questions.'},
    'statements':{'type':'array','maxItems':5,'items':{'type':'object','properties':{
        'text':{'type':'string'},'true':{'type':'boolean'}},'required':['text','true'],'additionalProperties':False}},
    'option_combinations':{'type':'array','maxItems':5,'items':{'type':'array','maxItems':5,'items':{'type':'integer'}}}})
_quality['required'].extend(['topic','asked_truth','statements','option_combinations'])
CONTRACT_PROMPT+='''\nKALİTE DENETİMİ: Her soruda gerçek ana kaynak konusunu topic alanına yaz.
Öncüllü sorularda statements içinde öncül metinlerini sırayla ve kaynağa göre
doğru/yanlış değerlerini true alanında ver. asked_truth kökün doğru öncülleri
istediğinde true, yanlış öncülleri istediğinde false olsun. option_combinations beş şıkkın
öncül numaralarını A–E sırasıyla taşısın; örneğin I ve III için [1,3]. Doğru
şıkkın kombinasyonu tam olarak doğru öncülleri içermeli. Öncülsüz sorularda bu
iki dizi boş olsun. Kullanıcıya bu denetim verilerini gösterme. Kaynağa ve
gerekçene göre öncüllerin doğruluğunu, tek doğru şıkkı ve konu dağılımını aynı
üretimde kontrol et; yalnız biçimsel olarak geçerli bir set hazırlama.\n'''


def parse_quiz(raw, count, history=(), evidence=None,*,require_quality=False,distinct_topics=False):
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
        required={'stem','options','correct','rationale','fact','source','material_id','page'}
        quality={'topic','asked_truth','statements','option_combinations'}
        if (not isinstance(q,dict) or not required<=set(q) or set(q)-required-quality
                or (set(q)&quality and not quality<=set(q)) or (require_quality and not quality<=set(q))):
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
        if quality<=set(q):
            if not isinstance(q['topic'],str) or not 0<len(q['topic'].strip())<=160 or type(q['asked_truth']) is not bool:
                raise ValueError('invalid quiz topic')
            statements=q['statements'];combinations=q['option_combinations']
            if not isinstance(statements,list) or not isinstance(combinations,list) or len(statements)>5:
                raise ValueError('invalid statement metadata')
            if statements:
                if not 2<=len(statements)<=5 or len(combinations)!=5:
                    raise ValueError('invalid statement count')
                for statement in statements:
                    if (not isinstance(statement,dict) or set(statement)!={'text','true'}
                            or type(statement['true']) is not bool or not isinstance(statement['text'],str)
                            or not statement['text'].strip()
                            or question_stem(statement['text']) not in question_stem(q['stem'])):
                        raise ValueError('statement outside question stem')
                for combo in combinations:
                    if (not isinstance(combo,list) or any(type(i) is not int or not 1<=i<=len(statements) for i in combo)
                            or len(set(combo))!=len(combo)):
                        raise ValueError('invalid statement combination')
                romans={'I':1,'II':2,'III':3,'IV':4,'V':5}
                for option,combo in zip(opts,combinations):
                    words=question_stem(option)
                    shown={romans[t] for t in re.findall(r'\b(?:III|II|IV|I|V)\b',option.upper())}
                    if words in {'hepsi','tumu','tamami'}:shown=set(range(1,len(statements)+1))
                    elif words in {'hicbiri','hic birisi'}:shown=set()
                    elif not shown:raise ValueError('unreadable statement option')
                    if shown!=set(combo):raise ValueError('displayed statement combination mismatch')
                truths={i for i,s in enumerate(statements,1) if s['true']==q['asked_truth']}
                matches=[i for i,combo in enumerate(combinations) if set(combo)==truths]
                if matches!=['ABCDE'.index(q['correct'])] or len({tuple(sorted(c)) for c in combinations})!=5:
                    raise ValueError('statement key mismatch')
            elif combinations or re.search(r'(?m)^\s*(?:I|II|III)[.)]\s',q['stem']):
                raise ValueError('missing statement metadata')
        fact=question_stem(q['fact'])
        if any(same_question(fact,question_stem(old)) for old in previous+seen):
            raise ValueError('repeated quiz fact')
        seen.append(q['fact'])
        stem=question_stem(q['stem'])
        correct=question_stem(opts['ABCDE'.index(q['correct'])])
        negative={'yanlis','yanlistir','degil','degildir','haric'}
        if len(correct.split())>=2 and len(correct)>=12 and not (set(stem.split()) & negative) and f' {correct} ' in f' {stem} ':
            raise ValueError('quiz answer exposed in stem')
    if distinct_topics and len({question_stem(q.get('topic','')) for q in questions})!=len(questions):
        raise ValueError('repeated main topic')
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


def previous_quiz_key(history, corrections=()):
    """Display the model's saved key; never infer answers or select an older set."""
    for item in reversed(history or []):
        if str(item.get('role', '')).upper() != 'ASSISTANT':
            continue
        if item.get('quiz') or question_blocks(item.get('content') or ''):
            quiz = item.get('quiz')
            break
    else:
        quiz = None
    if not quiz:
        return 'Bu son soru setinin doğrulanmış cevap anahtarı kayıtlı değil. Kaynaklarıyla yeniden doğrulanmadan cevap anahtarı gösterilemiyor.'
    questions = [dict(question) for question in quiz['questions']]
    if any(not 1 <= item['number'] <= len(questions) for item in corrections):
        return 'Cevap anahtarı kontrolü son soru setiyle eşleşmedi. Yanıt hazırlanamadı.'
    for item in corrections:
        question = questions[item['number']-1]
        question['correct'] = item['choice']
        question['rationale'] = item['rationale']
    return '### Cevap anahtarı\n\n' + '\n\n'.join(
        f"**{number}. {question['correct']}** — {question['rationale']} ({question['source']})"
        for number, question in enumerate(questions, 1))


def grade_previous_quiz(history, answers, corrections=()):
    # Nearest assistant question set only. Never silently grade an older set.
    for item in reversed(history or []):
        if str(item.get('role','')).upper()!='ASSISTANT':
            continue
        if item.get('quiz') or question_blocks(item.get('content') or ''):
            quiz=item.get('quiz')
            break
    else:
        quiz=None
    if not quiz:
        return 'Bu soru setinin doğrulanmış cevap anahtarı kayıtlı değil. Soruları kaynaklarıyla yeniden doğrulamadan puanlayamam.'
    questions=[dict(question) for question in quiz['questions']]
    if any(not 1 <= item['number'] <= len(questions) for item in corrections):
        return 'Cevap anahtarı kontrolü son soru setiyle eşleşmedi. Değerlendirme yapılamadı.'
    for item in corrections:
        question=questions[item['number']-1]
        question['correct']=item['choice']
        question['rationale']=item['rationale']
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

