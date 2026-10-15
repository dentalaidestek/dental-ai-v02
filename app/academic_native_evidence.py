"""Complete native text for already-selected, owned source pages.

The persisted page checkpoint can retain a value that old search chunks lost.
This is a bounded read of the active generation, never OCR or a model call.
Question pages stay on the original-page/transcription path.
"""
import json
import re
from sqlalchemy import text


def _question_page(body):
    from app.study_chunking import chunk_dental_page
    return (any(c.content_kind == 'QUESTION' for c in chunk_dental_page(body))
            or len(re.findall(r'(?:^|\s|\()[A-E][.)]\s+', body)) >= 2)


def selected_native_pages(session, *, owner_user_id, course_id, evidence):
    bind = getattr(session, 'get_bind', lambda: None)()
    if getattr(getattr(bind, 'dialect', None), 'name', '') != 'postgresql' or not evidence:
        return {}
    selected = {(e.material_id, page) for e in evidence
                for page in range(e.page_start, e.page_end + 1)}
    rows = session.exec(text('''
        SELECT p.material_id,p.page_number,m.display_name,p.text_content
        FROM studyindexpage p JOIN studymaterial m
          ON m.id=p.material_id AND m.owner_user_id=p.owner_user_id
         AND m.course_id=p.course_id AND m.active_index_version=p.index_version
        WHERE p.owner_user_id=:owner AND p.course_id=:course
          AND m.index_status='READY' AND m.deleted_at IS NULL
          AND p.extraction_method='PDF_TEXT' AND p.status='EXTRACTED'
          AND p.material_id=ANY(:ids) AND p.page_number=ANY(:pages)
          AND EXISTS (
            SELECT 1 FROM studyindexchunk chosen WHERE chosen.id=ANY(:chunk_ids)
              AND chosen.material_id=p.material_id AND chosen.owner_user_id=p.owner_user_id
              AND chosen.course_id=p.course_id AND chosen.index_version=p.index_version
              AND chosen.page_start<=p.page_number AND chosen.page_end>=p.page_number)
        ORDER BY p.material_id,p.page_number
    '''), params={'owner':owner_user_id,'course':course_id,
                 'chunk_ids':[e.chunk_id for e in evidence],
                 'ids':sorted({m for m,_ in selected}),
                 'pages':sorted({p for _,p in selected})}).all()
    result = {}
    for material, page, name, body in rows:
        key = (int(material), int(page))
        if key not in selected or not body or _question_page(body):
            continue
        result[key] = (f'[KANIT_NATIVE material_id={key[0]} sayfa={key[1]} '
                       f'dosya={json.dumps(name, ensure_ascii=False)} tür=PDF_TEXT]\n{body}')
    return result


def apply_native_pages(result, native):
    if not native:
        return
    # Keep evidence IDs for attribution. Replace only context whose complete
    # page span is covered by the native checkpoint; preserve all scan notices.
    covered = tuple(f'[KANIT material_id={item.material_id} sayfa={item.page_start} '
        for item in result.evidence if
        {(item.material_id,p) for p in range(item.page_start,item.page_end+1)} <= native.keys())
    # Scan warnings may precede the evidence blocks; never zip this list to IDs.
    result.note_context = [context for context in result.note_context
                           if not context.startswith(covered)]
    result.note_context.extend(native.values())


def matching_native_pages(session, *, owner_user_id, course_id, searches):
    """Find names split away from definitions by old chunk generations.

    Focus on the rarest literal source token per planned subject; common words
    cannot crowd out a specific name. Every returned page is owned, active and
    native text, and is checked for actual MCQ structure before factual use.
    """
    tokens=[];indices=[];phrases=[]
    for index,phrase in enumerate(searches):
        for token in dict.fromkeys(re.findall(r'[^\W_]+',phrase.casefold())):
            tokens.append(token);indices.append(index);phrases.append(phrase)
    if not tokens:
        return [],False
    rows=session.exec(text('''
      WITH native AS (
        SELECT p.material_id,p.page_number,p.index_version,p.text_content,m.display_name,
               to_tsvector('simple',p.text_content) AS document
        FROM studyindexpage p JOIN studymaterial m
          ON m.id=p.material_id AND m.owner_user_id=p.owner_user_id
         AND m.course_id=p.course_id AND m.active_index_version=p.index_version
        WHERE p.owner_user_id=:owner AND p.course_id=:course
          AND m.index_status='READY' AND m.deleted_at IS NULL
          AND p.extraction_method='PDF_TEXT' AND p.status='EXTRACTED'
      ), terms AS (
        SELECT * FROM unnest(CAST(:indices AS INTEGER[]),CAST(:tokens AS TEXT[]),
          CAST(:phrases AS TEXT[])) AS t(subject,term,phrase)
      ), frequencies AS (
        SELECT t.subject,t.term,t.phrase,COUNT(*) AS frequency
        FROM terms t JOIN native n ON n.document @@ plainto_tsquery('simple',t.term)
        GROUP BY t.subject,t.term,t.phrase
      ), focus AS (
        SELECT DISTINCT ON(subject) * FROM frequencies
        ORDER BY subject,frequency,length(term) DESC,term
      ), matched AS (
        SELECT f.subject,hits.* FROM focus f CROSS JOIN LATERAL (
          SELECT n.* FROM native n
          WHERE n.document @@ plainto_tsquery('simple',f.term)
          ORDER BY (n.document @@ plainto_tsquery('simple',f.phrase)) DESC,
            (position(f.term in lower(left(n.text_content,160)))>0) DESC,
            ts_rank_cd(n.document,plainto_tsquery('simple',f.term)) DESC,
            n.material_id,n.page_number
          LIMIT 2
        ) hits
      )
      SELECT c.id,n.material_id,n.display_name,c.page_start,c.page_end,
             c.section_title,'TEXT',n.text_content,
             NULL::BIGINT,NULL::DOUBLE PRECISION,NULL::BIGINT,NULL::DOUBLE PRECISION,
             1.0::DOUBLE PRECISION,c.chunk_index,c.semantic_json,n.subject
      FROM matched n CROSS JOIN LATERAL (
        SELECT c.* FROM studyindexchunk c WHERE c.owner_user_id=:owner AND c.course_id=:course
          AND c.material_id=n.material_id AND c.index_version=n.index_version
          AND c.page_start<=n.page_number AND c.page_end>=n.page_number
        ORDER BY (c.content_kind='QUESTION'),c.chunk_index,c.id LIMIT 1
      ) c ORDER BY n.subject,n.material_id,n.page_number
    '''),params={'owner':owner_user_id,'course':course_id,
                 'indices':indices,'tokens':tokens,'phrases':phrases}).all()
    selected=[];seen=set();covered=set()
    for row in rows:
        if _question_page(row[7]):
            continue
        covered.add(int(row[15]))
        key=(int(row[1]),int(row[3]))
        if key not in seen:
            seen.add(key);selected.append(tuple(row[:15]))
    return selected,covered==set(range(len(searches)))
