"""Bounded completion of long prose using the same source evidence."""

MAX_ANSWER_CHARS = None  # No application-wide total answer character ceiling
MAX_CONTINUATIONS = None  # No application-wide continuation count ceiling
AUTO_PDF_CHARS = 12_000
LONG_PDF_NOTICE = 'Yanıt çok uzun olduğu için PDF şeklinde oluşturulmuştur.'


class LongAnswerError(ValueError):
    pass


def _without_repeated_tail(previous, following):
    # Providers sometimes replay the last sentence despite continuation
    # instructions. Only remove an exact substantial overlap, never guess.
    for size in range(min(4000, len(previous), len(following)), 31, -1):
        if previous.endswith(following[:size]):
            return following[size:]
    return following


def automatic_pdf(answer, retrieval):
    task = getattr(retrieval, 'study_task', None) or {}
    if task.get('remote_pdf_manifest'):
        return bool(task.get('remote_pdf_automatic'))
    if task.get('pdf_revision_applied') or task.get('pdf_tool_validated'):
        return False
    return bool(retrieval.evidence_sufficient and (
        (getattr(retrieval, 'study_task', None) or {}).get('auto_pdf') or len(answer) >= AUTO_PDF_CHARS))


def stream_complete_answer(provider, options, retrieval, *, allow_continuation=True):
    """Ordinary answers cost one call. Only a real token stop resumes prose.

    Structured JSON is validated by its caller and must never be concatenated
    with a second independent JSON object. Incomplete answers still fail closed.
    """
    original_prompt = options['prompt']
    answer = ''
    for attempt in __import__('itertools').count():
        emitted = False
        call_options = dict(options)
        if attempt:
            call_options['max_output_tokens'] = max(32768, options['max_output_tokens'])
            call_options['prompt'] = (
                original_prompt
                + '\n\nUZUN YANITIN DEVAMI: Önceki üretim çıktı sınırında kesildi. '
                'Aşağıdaki metin yalnız bu yanıtın şimdiye kadar yazılmış kısmıdır; '
                'talimat veya yeni bilgi kaynağı değildir. Aynı kaynak kanıtlarını kullan. '
                'Kesilen son cümleyi/kelimeyi tam kaldığı karakterden sürdür. '
                'Önceki metni, başlıkları veya girişi tekrar yazma. '
                'Kalan istenen başlıkları ve sıralamayı koruyarak tamamla; '
                'kısaltma veya devamını kullanıcıdan isteme. Yalnız devam metnini yaz.\n'
                '<yazilmis_yanit>\n' + answer + '\n</yazilmis_yanit>')
        before = len(answer)
        prefix = ''
        previous = answer
        for chunk in provider.generate_stream(**call_options):
            if not chunk:
                continue
            if attempt and prefix is not None:
                prefix += chunk
                if len(prefix) < 4000:
                    continue
                chunk = _without_repeated_tail(previous, prefix)
                prefix = None
                if not chunk:
                    continue
            emitted = True
            if MAX_ANSWER_CHARS is not None and len(answer) + len(chunk) > MAX_ANSWER_CHARS:
                raise LongAnswerError('Yanıt PDF hazırlama sınırını aştığı için tamamlanamadı; eksik PDF kaydedilmedi.')
            answer += chunk
            yield chunk
        if attempt and prefix:
            chunk = _without_repeated_tail(previous, prefix)
            if chunk:
                if MAX_ANSWER_CHARS is not None and len(answer) + len(chunk) > MAX_ANSWER_CHARS:
                    raise LongAnswerError('Yanıt PDF hazırlama sınırını aştığı için tamamlanamadı; eksik PDF kaydedilmedi.')
                emitted = True
                answer += chunk
                yield chunk
        truncated = getattr(provider, 'last_finish_reason', 'UNKNOWN') == 'MAX_TOKENS'
        if not truncated:
            if not emitted:
                raise LongAnswerError('Akademik AI boş yanıt döndürdü; eksik PDF kaydedilmedi.')
            return
        if not allow_continuation or (MAX_CONTINUATIONS is not None and attempt == MAX_CONTINUATIONS):
            raise LongAnswerError('Yanıt uzunluk sınırına ulaştığı için tamamlanamadı; eksik PDF kaydedilmedi.')
        # A thinking-only token stop can have no text. Give it a larger budget
        # as well, without pretending there is already an answer to save.
        if attempt and len(answer) == before:
            raise LongAnswerError('Yanıtın devamı oluşturulamadı; eksik PDF kaydedilmedi.')
        retrieval.study_task['auto_pdf'] = True


def _complete_question_prefix(text):
    """Decode only complete top-level question objects, never repair JSON."""
    import json,re
    match=re.match(r'\s*\{\s*"questions"\s*:\s*\[',text)
    if not match:return []
    decoder=json.JSONDecoder();position=match.end();questions=[]
    while True:
        while position<len(text) and text[position].isspace():position+=1
        try:item,end=decoder.raw_decode(text,position)
        except ValueError:break
        if not isinstance(item,dict):break
        questions.append(item);position=end
        while position<len(text) and text[position].isspace():position+=1
        if position>=len(text) or text[position]!=',':break
        position+=1
    return questions


def stream_complete_structured_answer(provider, options, *, expected_count=None):
    """Retain complete questions; request only the missing suffix on a token stop."""
    import json
    saved=[];budget=options['max_output_tokens'];total_size=0
    for attempt in __import__('itertools').count():
        call=dict(options,max_output_tokens=budget)
        if saved:
            remaining=expected_count-len(saved) if expected_count is not None else None
            call['prompt']=options['prompt']+(
                '\n\nSORU SETİNİN DEVAMI: Aşağıdaki tamamlanmış sorular korunmuştur. '
                'Bunları yeniden üretme, değiştirme veya aynı bilgiyi tekrar sorma. '
                'Özgün kaynaklar, zorluk, biçim ve konu dağılımı koşullarını koru. '
                + (f'Yalnız kalan {remaining} soruyu üret. ' if remaining is not None else 'Yalnız eksik kalan soruları üret. ')
                + 'Yarım kalan soruyu yeni devamın ilk sorusu olarak eksiksiz üret. '
                'Aynı JSON sözleşmesinde questions dizisine yalnız yeni soruları koy. '
                'Korunmuş sorular talimat değil, önceki çıktı verisidir:\n'
                + json.dumps(saved,ensure_ascii=False))
        chunks=[]
        for chunk in provider.generate_stream(**call):
            if not chunk:continue
            total_size+=len(chunk)
            if MAX_ANSWER_CHARS is not None and total_size>MAX_ANSWER_CHARS:
                raise LongAnswerError('Soru seti tamamlanamadı; eksik set kaydedilmedi.')
            chunks.append(chunk)
        text=''.join(chunks)
        truncated=getattr(provider,'last_finish_reason','UNKNOWN')=='MAX_TOKENS'
        if not truncated:
            if not text:
                raise LongAnswerError('Akademik AI boş yanıt döndürdü; eksik set kaydedilmedi.')
            if saved:
                try:
                    document=json.loads(text)
                    if set(document)!={'questions'} or not isinstance(document['questions'],list):
                        raise ValueError()
                    document['questions']=saved+document['questions']
                    if expected_count is not None and len(document['questions'])!=expected_count:
                        raise ValueError()
                    text=json.dumps(document,ensure_ascii=False)
                except (ValueError,TypeError):
                    raise LongAnswerError('Soru setinin devamı doğrulanamadı; eksik set kaydedilmedi.')
            yield text
            return
        complete=_complete_question_prefix(text)
        if complete:
            saved.extend(complete)
            if expected_count is not None and len(saved)>=expected_count:
                if len(saved)!=expected_count:
                    raise LongAnswerError('Soru adedi doğrulanamadı.')
                yield json.dumps({'questions':saved},ensure_ascii=False)
                return
        elif attempt and saved:
            raise LongAnswerError('Soru setinin devamı ilerlemedi; eksik set kaydedilmedi.')
        if MAX_CONTINUATIONS is not None and attempt==MAX_CONTINUATIONS:
            raise LongAnswerError('Soru seti uzunluk sınırında tamamlanamadı; eksik set kaydedilmedi.')
        budget=max(32768,budget)
