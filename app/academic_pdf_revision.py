"""Append completed owned chat content to an owned PDF without regenerating it."""
from sqlmodel import select


def append_saved_pdf(session, *, message_model, plan, owner_user_id, course_id, history):
    from app.academic_pdf import MAX_PDF_TEXT
    from app.study_retrieval_v2 import RetrievalResult

    def unavailable(message):
        return RetrievalResult(resolved_query=plan.resolved_query,
            retrieval_mode='pdf_append_unavailable', clarification=message)

    if message_model is None:
        return unavailable('Eklenecek içerik ve önceki PDF doğrulanamadı.')
    turns = history[-8:]
    indices = plan.pdf_addition_turns or tuple(
        i for i in range(len(turns)-1, -1, -1)
        if str(turns[i].get('role', '')).upper() == 'ASSISTANT')[:1]
    if not indices or any(i >= len(turns) for i in indices):
        return unavailable('PDF’ye eklenecek önceki cevabı belirtir misin?')
    selected = [turns[i] for i in indices]
    if any(str(t.get('role', '')).upper() != 'ASSISTANT'
           or str(t.get('mode', '')).endswith('_PDF')
           or type(t.get('id')) is not int for t in selected):
        return unavailable('PDF’ye eklenecek mevcut tablo veya cevabı belirtir misin?')
    # Re-read every chosen row with ownership/course fences. Model output only
    # chooses bounded dialogue positions, never arbitrary database identifiers.
    ids = [t['id'] for t in selected]
    rows = list(session.exec(select(message_model).where(
        message_model.owner_user_id == owner_user_id,
        message_model.course_id == course_id,
        message_model.role == 'ASSISTANT', message_model.id.in_(ids),
    ).order_by(message_model.id)).all())
    if (len(rows) != len(ids) or any(not row.content.strip()
            or row.mode.endswith('_PDF') for row in rows)):
        return unavailable('Eklenecek cevap artık bulunamadı; PDF oluşturulmadı.')
    base = session.exec(select(message_model).where(
        message_model.owner_user_id == owner_user_id,
        message_model.course_id == course_id,
        message_model.role == 'ASSISTANT',
        message_model.mode.endswith('_PDF', autoescape=True),
        message_model.id < rows[0].id,
    ).order_by(message_model.id.desc()).limit(1)).first()
    if base is None or not base.content.strip():
        return unavailable('Bu sohbette eklenecek içeriğin öncesinde oluşturulmuş PDF bulunamadı. Hangi PDF’ye ekleyelim?')
    parts = [base.content]
    for row in rows:
        if row.content not in parts:
            parts.append(row.content)
    total = sum(map(len, parts)) + 2 * (len(parts)-1)
    if total > MAX_PDF_TEXT:
        return unavailable('Birleştirilmiş içerik PDF uzunluk sınırını aşıyor; mevcut PDF korunuyor.')
    return RetrievalResult(resolved_query=plan.resolved_query,
        retrieval_mode='appended_answer_pdf', evidence_sufficient=True,
        prepared_answer='\n\n'.join(parts))
