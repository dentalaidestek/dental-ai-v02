"""Complete source-order batches; batch budgets split work, never sample it.

This module only plans source work. It makes no model calls and does not label
OCR or a model response as verified facts.
"""
from dataclasses import dataclass
import logging

logger = logging.getLogger('uvicorn.error.academic_source_batches')


@dataclass(frozen=True)
class SourceBatch:
    title: str
    chunk_ids: tuple[int, ...]
    primary_chunk_ids: tuple[int, ...] = ()


def _question_page_batches(rows, *, max_chars, max_pages, visual_pages, visual_page_bytes, max_visual_bytes):
    """Whole pages plus one look-ahead page for continuation options."""
    from itertools import groupby
    groups=[]
    seen=set()
    ordered=sorted(rows,key=lambda r:(int(r[1]),int(r[3]),int(r[13]),int(r[0])))
    for _,items in groupby(ordered,key=lambda r:(int(r[1]),int(r[3]),int(r[4]))):
        group=[r for r in items if int(r[0]) not in seen]
        seen.update(int(r[0]) for r in group)
        if group: groups.append(group)
    def size(group):
        return sum(len(r[7] or '')+len(str(r[5] or r[2] or ''))+200 for r in group)
    def pages(group):
        return {(int(r[1]),p) for r in group for p in range(int(r[3]),int(r[4])+1)
                if visual_pages is None or (int(r[1]),p) in visual_pages}
    def byte_size(selected):
        return sum(visual_page_bytes.get(page, 0) for page in selected)
    batches=[]
    start=0
    while start<len(groups):
        end=start; chars=0; chosen_pages=set(); chosen=[]
        while end<len(groups):
            group=groups[end]
            if size(group)>max_chars or len(pages(group))>max_pages or byte_size(pages(group))>max_visual_bytes:
                raise ValueError('question page exceeds batch budget')
            following=(groups[end+1] if end+1<len(groups) and
                int(groups[end+1][0][1])==int(group[0][1]) and
                int(groups[end+1][0][3])<=int(group[-1][4])+1 else [])
            if chosen and (chars+size(group)+size(following)>max_chars or len(chosen_pages|pages(group))>max(1,max_pages-1)
                           or byte_size(chosen_pages|pages(group)|pages(following))>max_visual_bytes):
                break
            chosen.extend(group); chars+=size(group); chosen_pages |= pages(group); end+=1
        primary=tuple(int(r[0]) for r in chosen)
        if end<len(groups) and int(groups[end][0][1])==int(chosen[-1][1]) and int(groups[end][0][3])<=int(chosen[-1][4])+1:
            extra=groups[end]
            if (chars+size(extra)<=max_chars and len(chosen_pages|pages(extra))<=max_pages
                    and byte_size(chosen_pages|pages(extra))<=max_visual_bytes):
                chosen.extend(extra)
            else:
                raise ValueError('question continuation exceeds batch budget')
        titles=list(dict.fromkeys(str(r[5] or r[2] or 'Ders notu') for r in chosen))
        batches.append(SourceBatch(' / '.join(titles),tuple(int(r[0]) for r in chosen),primary))
        start=end
    return tuple(batches)


def partition_source_rows(rows, *, max_chars=96000, max_pages=16, visual_pages=None,
                          include_questions=False, visual_page_bytes=None,
                          max_visual_bytes=12*1024*1024):
    if max_chars < 1 or max_pages < 1:
        raise ValueError('invalid batch budget')
    visual_page_bytes = visual_page_bytes or {}
    if include_questions:
        return _question_page_batches(rows,max_chars=max_chars,max_pages=max_pages,visual_pages=visual_pages,
            visual_page_bytes=visual_page_bytes,max_visual_bytes=max_visual_bytes)
    seen = set()
    batches, ids, chars, pages, titles = [], [], 0, set(), []
    def flush():
        if ids:
            batches.append(SourceBatch(' / '.join(titles), tuple(ids)))
    for row in sorted(rows, key=lambda r: (int(r[1]), int(r[3]), int(r[13]), int(r[0]))):
        cid = int(row[0])
        if cid in seen or (not include_questions and str(row[6]).upper() == 'QUESTION'):
            continue
        seen.add(cid)
        title = str(row[5] or row[2] or 'Ders notu')
        size = len(row[7] or '') + len(title) + 200
        current_pages = {(int(row[1]), p) for p in range(int(row[3]), int(row[4])+1)
                         if visual_pages is None or (int(row[1]),p) in visual_pages}
        if (size > max_chars or len(current_pages) > max_pages
                or sum(visual_page_bytes.get(p,0) for p in current_pages)>max_visual_bytes):
            raise ValueError('source chunk exceeds batch budget')
        # Source identity stays on every row. Neither a heading nor a file
        # boundary requires another model call: related facts from different
        # files must be judged together when they fit the same input budget.
        if ids and (chars + size > max_chars
                    or len(pages | current_pages) > max_pages
                    or sum(visual_page_bytes.get(p,0) for p in pages|current_pages)>max_visual_bytes):
            flush()
            ids, chars, pages, titles = [], 0, set(), []
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


def focused_selected_rows(rows, request_plan):
    """Rank within an already owned file boundary; never search other files.

    Exact pages, visual reads and exhaustive/section requests keep their full
    coverage. Unmatched planner searches retain the original bounded source
    instead of turning morphology differences into a false absence claim.
    """
    if (not request_plan.source_files or request_plan.source_pages
            or request_plan.scope != 'topic' or request_plan.source_kind != 'notes'
            or request_plan.complete_sections or request_plan.source_sections
            or request_plan.needs_visual):
        return rows
    searches = tuple(dict.fromkeys((*request_plan.source_subjects,
                                    *request_plan.retrieval_queries)))
    if not searches or not rows:
        return rows
    from app.academic_semantic_retrieval import _balanced_candidates
    selected = set()
    for phrase in searches:
        pool = _balanced_candidates(rows, (phrase,), max(1, len(rows)),
                                   allow_unmatched=False, best_match_only=True)
        if not pool:
            return rows
        selected.update(int(row[0]) for row in pool)
    return [row for row in rows if int(row[0]) in selected]


def retrieve_source_batches(session, *, owner_user_id, course_id, query,
                            request_plan, recent_history=None, **kwargs):
    from app.academic_semantic_retrieval import retrieve_semantic_context
    from app.study_retrieval_v2 import RetrievalResult
    if request_plan.source_files or request_plan.source_pages:
        rows = list(load_owned_selected_rows(session, owner_user_id=owner_user_id,
            course_id=course_id, source_files=request_plan.source_files,
            source_pages=request_plan.source_pages))
        original_count = len(rows)
        rows = focused_selected_rows(rows, request_plan)
        logger.info('Academic selected source candidates before=%s after=%s scope=%s',
                    original_count, len(rows), request_plan.scope)
    else:
        loader = load_owned_question_rows if request_plan.source_kind in {'questions', 'question_patterns'} else load_owned_source_rows
        rows = list(loader(session, owner_user_id=owner_user_id, course_id=course_id))
    return retrieve_row_batches(session,rows=rows,owner_user_id=owner_user_id,
        course_id=course_id,query=query,request_plan=request_plan,recent_history=recent_history)


def load_owned_selected_rows(session, *, owner_user_id, course_id, source_files, source_pages):
    """Explicit file/page boundaries apply before any model call or batching.

    Include OCR placeholders and unclassified exam text too: selecting a page
    must not depend on whether its corrupted OCR contains a question marker.
    """
    import unicodedata
    from sqlalchemy import text
    from app.study_retrieval_v2 import _coverage_evidence_rows
    normalize = lambda value: unicodedata.normalize('NFC', value.strip()).casefold()
    files = {normalize(value) for value in source_files}
    pages = set(source_pages)
    after = 0
    while True:
        metadata = session.exec(text(
            "SELECT c.id,m.display_name,c.page_start,c.page_end FROM studyindexchunk c "
            "JOIN studymaterial m ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id "
            "AND m.course_id=c.course_id AND m.active_index_version=c.index_version "
            "WHERE c.owner_user_id=:owner AND c.course_id=:course "
            "AND m.index_status='READY' AND m.deleted_at IS NULL AND c.id>:after "
            "ORDER BY c.id LIMIT 128"),
            params={'owner': owner_user_id, 'course': course_id, 'after': after}).all()
        if not metadata:
            return
        if int(metadata[-1][0]) <= after:
            raise ValueError('selected source cursor did not advance')
        after = int(metadata[-1][0])
        ids = [int(cid) for cid, name, start, end in metadata
               if (not files or normalize(name) in files)
               and (not pages or start >= 1 and end >= start
                    and end - start + 1 <= len(pages)
                    and set(range(start, end + 1)) <= pages)]
        if not ids:
            continue
        rows = _coverage_evidence_rows(session, owner_user_id=owner_user_id,
            course_id=course_id, chunk_ids=ids, limit=len(ids), max_rows=128,
            include_questions=True)
        if set(ids) != {int(row[0]) for row in rows}:
            raise ValueError('source generation changed during selected retrieval')
        yield from rows


def load_owned_question_rows(session, *, owner_user_id, course_id):
    """Visit the complete question candidate index, retaining source order."""
    from app.study_retrieval_v2 import _question_rows
    cursor = None
    while True:
        rows = _question_rows(session, owner_user_id=owner_user_id, course_id=course_id,
                              limit=32, after_cursor=cursor)
        if not rows:
            return
        next_cursor = (int(rows[-1][1]), int(rows[-1][13]))
        if cursor is not None and next_cursor <= cursor:
            raise ValueError('question source cursor did not advance')
        yield from rows
        cursor = next_cursor


def retrieve_row_batches(session, *, rows, owner_user_id, course_id, query,
                         request_plan, recent_history=None):
    from sqlalchemy import text
    from app.academic_semantic_retrieval import retrieve_semantic_context
    from app.study_retrieval_v2 import RetrievalResult
    # Indexed OCR text has the same text budget as native text. Do not query
    # PDF byte sizes or split by scan count for ordinary text requests.
    visual_metadata = session.exec(text(
        "SELECT p.material_id,p.page_number,COALESCE(length(p.visual_pdf_bytes),0) FROM studyindexpage p JOIN studymaterial m "
        "ON m.id=p.material_id AND m.owner_user_id=p.owner_user_id AND m.course_id=p.course_id "
        "AND m.active_index_version=p.index_version WHERE p.owner_user_id=:owner AND p.course_id=:course "
        "AND m.index_status='READY' AND m.deleted_at IS NULL"),
        params={'owner':owner_user_id,'course':course_id}).all() if request_plan.needs_visual else []
    visual_pages = None if request_plan.needs_visual else set()
    visual_page_bytes = {(int(r[0]),int(r[1])):int(r[2] or 0) for r in visual_metadata if len(r)>2}
    questions = getattr(request_plan,'source_kind','notes') in {'questions', 'question_patterns'}
    inventory = getattr(request_plan,'source_kind','notes') == 'question_patterns'
    # Verbatim question output is much longer than a summary of the same
    # inputs. Bound those sections for the existing generation output budget.
    batches = partition_source_rows(rows,visual_pages=visual_pages,
        max_chars=28000 if inventory else 14000 if questions else 96000,
        max_pages=8 if inventory else 4 if questions else (8 if request_plan.scope=='topic' else 16),
        include_questions=questions,visual_page_bytes=visual_page_bytes)
    by_id = {int(row[0]): row for row in rows}
    children=[]
    for batch in batches:
        child=retrieve_semantic_context(session, owner_user_id=owner_user_id,
            course_id=course_id, query=query, request_plan=request_plan, recent_history=recent_history,
            _source_rows=[by_id[cid] for cid in batch.chunk_ids])
        child.study_task['source_files'] = list(getattr(request_plan, 'source_files', ()))
        child.study_task['source_pages'] = list(getattr(request_plan, 'source_pages', ()))
        if questions:
            child.study_task['question_start_pages']=sorted({(int(by_id[cid][1]),p)
                for cid in batch.primary_chunk_ids for p in range(int(by_id[cid][3]),int(by_id[cid][4])+1)})
        children.append(child)
    if len(children) == 1 and not (getattr(request_plan, 'source_kind', 'notes') == 'question_patterns'
                                   and getattr(request_plan, 'operation', 'answer') != 'generate_questions'):
        return children[0]
    result = RetrievalResult(resolved_query=request_plan.resolved_query,
        retrieval_mode='source_batches', evidence_sufficient=bool(children),
        study_task={key:getattr(request_plan,key) for key in
                    ('operation','scope','count','difficulty','source_kind','depth')},
        source_batches=children)
    # Continuation pages may appear in two children, but parent provenance is
    # one unique source list. They must not become two counted exam records.
    seen_evidence=set()
    for child in children:
        for item in child.evidence:
            if item.chunk_id not in seen_evidence:
                result.evidence.append(item)
                seen_evidence.add(item.chunk_id)
    result.source_material_ids = list(dict.fromkeys(item.material_id for item in result.evidence))
    return result

