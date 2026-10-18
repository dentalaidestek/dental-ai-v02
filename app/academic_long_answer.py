"""Bounded completion of long prose using the same source evidence."""

MAX_ANSWER_CHARS = 240_000
MAX_CONTINUATIONS = 3
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
    for attempt in range(MAX_CONTINUATIONS + 1):
        emitted = False
        call_options = dict(options)
        if attempt:
            call_options['max_output_tokens'] = max(16000, options['max_output_tokens'])
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
            if len(answer) + len(chunk) > MAX_ANSWER_CHARS:
                raise LongAnswerError('Yanıt PDF hazırlama sınırını aştığı için tamamlanamadı; eksik PDF kaydedilmedi.')
            answer += chunk
            yield chunk
        if attempt and prefix:
            chunk = _without_repeated_tail(previous, prefix)
            if chunk:
                if len(answer) + len(chunk) > MAX_ANSWER_CHARS:
                    raise LongAnswerError('Yanıt PDF hazırlama sınırını aştığı için tamamlanamadı; eksik PDF kaydedilmedi.')
                emitted = True
                answer += chunk
                yield chunk
        truncated = getattr(provider, 'last_finish_reason', 'UNKNOWN') == 'MAX_TOKENS'
        if not truncated:
            if not emitted:
                raise LongAnswerError('Akademik AI boş yanıt döndürdü; eksik PDF kaydedilmedi.')
            return
        if not allow_continuation or attempt == MAX_CONTINUATIONS:
            raise LongAnswerError('Yanıt uzunluk sınırına ulaştığı için tamamlanamadı; eksik PDF kaydedilmedi.')
        # A thinking-only token stop can have no text. Give it a larger budget
        # as well, without pretending there is already an answer to save.
        if attempt and len(answer) == before:
            raise LongAnswerError('Yanıtın devamı oluşturulamadı; eksik PDF kaydedilmedi.')
        retrieval.study_task['auto_pdf'] = True
