"""Complete source-order batches; batch budgets split work, never sample it.

This module only plans source work. It makes no model calls and does not label
OCR or a model response as verified facts.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceBatch:
    title: str
    chunk_ids: tuple[int, ...]


def partition_source_rows(rows, *, max_chars=96000, max_pages=16, visual_pages=None):
    if max_chars < 1 or max_pages < 1:
        raise ValueError('invalid batch budget')
    seen = set()
    batches, ids, chars, pages, titles = [], [], 0, set(), []
    material = None
    def flush():
        if ids:
            batches.append(SourceBatch(' / '.join(titles), tuple(ids)))
    for row in sorted(rows, key=lambda r: (int(r[1]), int(r[3]), int(r[13]), int(r[0]))):
        cid = int(row[0])
        if cid in seen or str(row[6]).upper() == 'QUESTION':
            continue
        seen.add(cid)
        title = str(row[5] or row[2] or 'Ders notu')
        size = len(row[7] or '') + len(title) + 200
        current_pages = {(int(row[1]), p) for p in range(int(row[3]), int(row[4])+1)
                         if visual_pages is None or (int(row[1]),p) in visual_pages}
        if size > max_chars or len(current_pages) > max_pages:
            raise ValueError('source chunk exceeds batch budget')
        # Adjacent small headings share a call, while each row retains its full
        # parent/child heading. A heading is not itself a paid-call boundary.
        if ids and (material != int(row[1]) or chars + size > max_chars
                    or len(pages | current_pages) > max_pages):
            flush()
            ids, chars, pages, titles = [], 0, set(), []
        material = int(row[1])
        ids.append(cid); chars += size; pages.update(current_pages)
        if title not in titles:
            titles.append(title)
    flush()
    return tuple(batches)


def load_owned_source_rows(session, *, owner_user_id, course_id):
    """Read every published factual chunk with keyset pagination and ownership.

    Hydration is intentionally independent of search top-k. Existing bounded
    hydration executes at most 128 rows per short query without omitting rows.
    """
    from app.study_retrieval_v2 import _coverage_metadata_page, _coverage_evidence_rows
    after = 0
    while True:
        metadata = _coverage_metadata_page(session, owner_user_id=owner_user_id,
            course_id=course_id, after_id=after, limit=128)
        if not metadata:
            return
        ids = [int(row[0]) for row in metadata]
        rows = _coverage_evidence_rows(session, owner_user_id=owner_user_id,
            course_id=course_id, chunk_ids=ids, limit=len(ids), max_rows=128)
        if set(ids) != {int(row[0]) for row in rows}:
            raise ValueError('source generation changed during batch planning')
        yield from rows
        after = ids[-1]


def retrieve_source_batches(session, *, owner_user_id, course_id, query,
                            request_plan, recent_history=None, **kwargs):
    from app.academic_semantic_retrieval import retrieve_semantic_context
    from app.study_retrieval_v2 import RetrievalResult
    rows = list(load_owned_source_rows(session, owner_user_id=owner_user_id, course_id=course_id))
    return retrieve_row_batches(session,rows=rows,owner_user_id=owner_user_id,
        course_id=course_id,query=query,request_plan=request_plan,recent_history=recent_history)


def retrieve_row_batches(session, *, rows, owner_user_id, course_id, query,
                         request_plan, recent_history=None):
    from sqlalchemy import text
    from app.academic_semantic_retrieval import retrieve_semantic_context
    from app.study_retrieval_v2 import RetrievalResult
    # Only original visual pages count toward the page budget. Fifty short
    # digital text slides need not become fifty calls or be cut at page eight.
    visual_pages = None if request_plan.needs_visual else {(int(row[0]),int(row[1])) for row in session.exec(text(
        "SELECT p.material_id,p.page_number FROM studyindexpage p JOIN studymaterial m "
        "ON m.id=p.material_id AND m.owner_user_id=p.owner_user_id AND m.course_id=p.course_id "
        "AND m.active_index_version=p.index_version WHERE p.owner_user_id=:owner AND p.course_id=:course "
        "AND m.index_status='READY' AND m.deleted_at IS NULL "
        "AND (p.extraction_method LIKE '%OCR%' OR p.extraction_method='IMAGE')"),
        params={'owner':owner_user_id,'course':course_id}).all()}
    batches = partition_source_rows(rows,visual_pages=visual_pages,
        max_pages=8 if request_plan.scope=='topic' else 16)
    by_id = {int(row[0]): row for row in rows}
    children = [retrieve_semantic_context(session, owner_user_id=owner_user_id,
        course_id=course_id, query=query, request_plan=request_plan, recent_history=recent_history,
        _source_rows=[by_id[cid] for cid in batch.chunk_ids]) for batch in batches]
    if len(children) == 1:
        return children[0]
    result = RetrievalResult(resolved_query=request_plan.resolved_query,
        retrieval_mode='source_batches', evidence_sufficient=bool(children),
        study_task={key:getattr(request_plan,key) for key in
                    ('operation','scope','count','difficulty','source_kind','depth')},
        source_batches=children)
    result.evidence = [item for child in children for item in child.evidence]
    result.source_material_ids = list(dict.fromkeys(item.material_id for item in result.evidence))
    return result
