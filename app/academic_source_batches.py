"""Complete source-order batches; batch budgets split work, never sample it.

This module only plans source work. It makes no model calls and does not label
OCR or a model response as verified facts.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceBatch:
    title: str
    chunk_ids: tuple[int, ...]


def partition_source_rows(rows, *, max_chars=96000, max_pages=16):
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
        current_pages = {(int(row[1]), p) for p in range(int(row[3]), int(row[4])+1)}
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
    batches = partition_source_rows(rows)
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
