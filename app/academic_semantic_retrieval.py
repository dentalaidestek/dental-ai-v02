"""Gemini-directed owned retrieval, without the legacy language/reranking engine.

Search ranking is lexical, not a claim that the retrieved candidates answer the
question. Gemini assesses support in the final grounded response.
"""
from __future__ import annotations

import re
import logging
import json
from sqlalchemy import text
from app.academic_request_understanding import StudyRequest
from app.academic_chunk_links import get_course_links, source_nodes
from app.study_retrieval_v2 import (
    Evidence, RetrievalResult, _fts_rows, _semantic_fts_query,
    _semantic_fts_fallback, _question_rows, _academic_question_rows,
    _coverage_evidence_rows, _coverage_hydration_ids, get_or_build_coverage_plan,
)

logger = logging.getLogger('uvicorn.error.academic_semantic_retrieval')


class SectionEvidenceRows(list):
    """Complete named-section rows, requiring coverage rather than top-k."""


def _linked_candidates(session, rows, searches, *, owner_user_id, course_id, limit):
    """Keep Gemini's independent subjects balanced while following source links."""
    pools = [_balanced_candidates(rows, (phrase,), limit) for phrase in searches]
    seeds = []
    for phrase, pool in zip(searches, pools):
        wanted = set(re.findall(r'[^\W_]+', phrase.casefold()))
        aligned = [row for row in pool if wanted.intersection(
            re.findall(r'[^\W_]+', ((row[5] or '') + ' ' + (row[7] or '')).casefold()))]
        seeds.append(aligned[:2])
    links = get_course_links(session, owner_user_id=owner_user_id, course_id=course_id)
    # A named source section is a coverage request, not a top-k question.
    # Hydrate it in bounded database pages, never truncate its contents.
    named_ids = [links.named_section_ids(phrase) for phrase in searches]
    logger.info('Academic heading lookup matches=%s diagnostics=%s',
                [len(ids) for ids in named_ids],
                [links.lookup_diagnostics(phrase) for phrase in searches])
    if any(named_ids):
        ids = list(dict.fromkeys(cid for group in named_ids for cid in group))
        # A comparison may pair a complete section with a short unnamed topic.
        ids += [int(row[0]) for group,named in zip(pools,named_ids) if not named for row in group]
        ids = list(dict.fromkeys(ids))
        hydrated = []
        for offset in range(0,len(ids),128):
            page = ids[offset:offset+128]
            hydrated.extend(_coverage_evidence_rows(session,owner_user_id=owner_user_id,
                course_id=course_id,chunk_ids=page,limit=len(page),max_rows=128))
        if set(ids) != {int(row[0]) for row in hydrated}:
            raise ValueError('source generation changed during section retrieval')
        return SectionEvidenceRows(hydrated)
    if not any(source_nodes(row) or row[5] and len(str(row[5]).strip()) >= 6
               for group in seeds for row in group):
        return _balanced_candidates(rows, searches, limit)
    focuses = [links.focus_nodes(phrase) for phrase in searches]
    for i, focus in enumerate(focuses):
        if focus:
            from app.dental_knowledge_graph import exact_nodes_in_subset
            pools[i] = [row for row in pools[i] if focus.intersection(source_nodes(row)) or
                        (not source_nodes(row) and exact_nodes_in_subset(
                            (row[5] or '') + ' ' + (row[7] or ''), tuple(focus)))]
            seeds[i] = pools[i][:2]
    named_sections = [bool(links.requested_sections(group, (phrase,)))
                      for group, phrase in zip(seeds, searches)]
    # Named sections may span many short slides. Bound total text/work rather
    # than discarding the section's middle at the ordinary 16-chunk limit.
    selection_limit = 128 if any(named_sections) else limit
    linked_ids = [links.related_ids(group, max(2, selection_limit // len(pools)),
                                   section_queries=(phrase,), focus_nodes=focus)
                  for group, phrase, focus in zip(seeds, searches, focuses)]
    ids = list(dict.fromkeys(cid for group in linked_ids for cid in group))
    hydrated = _coverage_evidence_rows(session, owner_user_id=owner_user_id,
        course_id=course_id, chunk_ids=ids, limit=min(selection_limit, len(ids)),
        max_rows=selection_limit) if ids else []
    by_id = {int(row[0]): row for row in hydrated}
    combined = []
    for pool, group, named in zip(pools, linked_ids, named_sections):
        related = [by_id[cid] for cid in group if cid in by_id]
        merged = pool[:2]
        if named:
            combined.append(merged + related)
            continue
        for offset in range(max(len(pool)-2, len(related))):
            if offset < len(related):
                merged.append(related[offset])
            if offset + 2 < len(pool):
                merged.append(pool[offset + 2])
        combined.append(merged)
    selected, seen, text_chars = [], set(), 0
    for offset in range(max((len(p) for p in combined), default=0)):
        for pool in combined:
            if offset < len(pool) and int(pool[offset][0]) not in seen:
                row = pool[offset]
                size = len(row[7] or '') + len(row[5] or '') + 160
                if any(named_sections) and text_chars + size > 96000:
                    continue
                text_chars += size
                seen.add(int(row[0])); selected.append(row)
                if len(selected) == selection_limit:
                    return selected
    return selected


def _balanced_candidates(rows, phrases, limit):
    """Round-robin lexical pools so a frequent search cannot crowd out another."""
    def terms(value):
        return set(re.findall(r'[^\W_]+', value.casefold()))
    pools = []
    for phrase in phrases:
        wanted = terms(phrase)
        scored = []
        for row in rows:
            present = terms((row[5] or '') + ' ' + (row[7] or ''))
            overlap = len(wanted & present)
            if overlap:
                scored.append((overlap / max(1, len(wanted)), row))
        scored.sort(key=lambda item: -item[0])
        pools.append([item[1] for item in scored])
    selected, seen = [], set()
    for offset in range(len(rows)):
        for pool in pools:
            if offset < len(pool) and int(pool[offset][0]) not in seen:
                row = pool[offset]
                selected.append(row); seen.add(int(row[0]))
                if len(selected) == limit:
                    return selected
    for row in rows:
        if int(row[0]) not in seen:
            selected.append(row); seen.add(int(row[0]))
            if len(selected) == limit:
                break
    return selected


def _source_cursor(history):
    # Only consume the server-persisted assistant cursor, never the user message.
    for item in reversed(history or []):
        if str(item.get('role', '')).upper() == 'ASSISTANT':
            match = re.search(r'<!--ACADEMIC_Q_CURSOR:(\d+):(\d+)-->', item.get('content') or '')
            if match:
                return tuple(map(int, match.groups()))
            break
    return None


def retrieve_semantic_context(session, *, owner_user_id, course_id, query,
                              request_plan, recent_history=None, limit=16, _source_rows=None):
    if session.get_bind().dialect.name != 'postgresql':
        raise RuntimeError('Academic semantic retrieval requires PostgreSQL')
    if not isinstance(request_plan, StudyRequest):
        raise ValueError('Gemini request plan is required')
    result = RetrievalResult(resolved_query=request_plan.resolved_query,
                             semantic_planner_attempted=True,
                             study_task={key:getattr(request_plan,key) for key in
                                         ('operation','scope','count','difficulty','source_kind','depth')})
    if request_plan.operation == 'clarify':
        result.retrieval_mode = 'clarification'
        result.clarification = request_plan.clarification
        return result
    limit = min(32, max(4, limit, 24 if request_plan.depth == 'detailed' else 16))
    if _source_rows is not None:
        rows = list(_source_rows)
        result.retrieval_mode = 'source_batch'
    elif request_plan.scope == 'course' and request_plan.source_kind == 'questions':
        rows = _question_rows(session, owner_user_id=owner_user_id, course_id=course_id,
                              limit=17, after_cursor=_source_cursor(recent_history) if request_plan.continue_source else None)
        result.has_more = len(rows) > 16
        rows = rows[:16]
        result.retrieval_mode = 'questions_exhaustive'
    elif request_plan.scope == 'course':
        count = min(48, max(24, request_plan.count or 0,
                           48 if request_plan.depth == 'detailed' or request_plan.operation == 'generate_questions' else 24))
        coverage = get_or_build_coverage_plan(session, owner_user_id=owner_user_id,
                                              course_id=course_id, requested_count=count)
        rows = _coverage_evidence_rows(session, owner_user_id=owner_user_id,
            course_id=course_id, chunk_ids=_coverage_hydration_ids(coverage, limit=count), limit=count)
        if request_plan.source_kind == 'question_patterns':
            rows = _academic_question_rows(session, owner_user_id=owner_user_id,
                course_id=course_id, limit=16) + rows
        result.retrieval_mode = 'coverage'
    else:
        searches = request_plan.retrieval_queries
        if not searches:
            raise ValueError('Gemini topic searches are required')
        rows = _fts_rows(session, owner_user_id=owner_user_id, course_id=course_id,
            lexical_query=_semantic_fts_query(searches), query_vector=None,
            embedding_provider='', embedding_model='', limit=min(96, limit * 3),
            lexical_groups=tuple(_semantic_fts_query((phrase,)) for phrase in searches),
            lexical_fallback_groups=tuple(_semantic_fts_fallback(phrase) for phrase in searches))
        if request_plan.source_kind == 'questions':
            rows = [row for row in rows if row[6] == 'QUESTION']
        rows = (_balanced_candidates(rows, searches, limit)
                if request_plan.source_kind == 'questions' else
                _linked_candidates(session, rows, searches, owner_user_id=owner_user_id,
                                   course_id=course_id, limit=limit))
        result.retrieval_mode = 'semantic_candidates'
    if (_source_rows is None and request_plan.scope == 'topic'
            and isinstance(rows,SectionEvidenceRows)
            and (len({(int(row[1]),page) for row in rows for page in range(int(row[3]),int(row[4])+1)}) > 8
                 or sum(len(row[7] or '')+len(row[5] or '')+200 for row in rows)>96000)):
        from app.academic_source_batches import retrieve_row_batches
        partitioned = retrieve_row_batches(session,rows=rows,owner_user_id=owner_user_id,
            course_id=course_id,query=query,request_plan=request_plan,recent_history=recent_history)
        return partitioned
    logger.info('Academic source retrieval mode=%s candidates=%s limit=%s',
                result.retrieval_mode, len(rows), limit)
    seen = set()
    for row in rows:
        if int(row[0]) in seen:
            continue
        seen.add(int(row[0]))
        evidence = Evidence(chunk_id=int(row[0]), material_id=int(row[1]), display_name=row[2],
            page_start=int(row[3]), page_end=int(row[4]), section_title=row[5],
            content_kind=row[6], text=row[7], lexical_rank=row[8], semantic_rank=None,
            hybrid_score=float(row[12] or 0), chunk_index=int(row[13] or 0))
        result.evidence.append(evidence)
        result.note_context.append(
            f'[KANIT material_id={evidence.material_id} sayfa={evidence.page_start} '
            f'bölüm={evidence.section_title or "-"} tür={evidence.content_kind}]\n{evidence.text}')
        if evidence.material_id not in result.source_material_ids:
            result.source_material_ids.append(evidence.material_id)
    # This means candidates exist, not that a rule engine proved factual support.
    result.evidence_sufficient = bool(result.evidence)
    # The planner has not seen the selected pages and cannot know whether OCR
    # omitted crossed-out options, answer marks or handwritten corrections.
    scanned_pages = set()
    if result.evidence:
        selected_pages = {(item.material_id, page) for item in result.evidence
                          for page in range(item.page_start, item.page_end + 1)}
        checkpoints = session.exec(text('''SELECT p.material_id,p.page_number
            FROM studyindexpage p JOIN studymaterial m
              ON m.id=p.material_id AND m.owner_user_id=p.owner_user_id
             AND m.course_id=p.course_id AND m.active_index_version=p.index_version
            WHERE p.owner_user_id=:owner AND p.course_id=:course
              AND m.index_status='READY' AND m.deleted_at IS NULL
              AND p.material_id=ANY(:ids) AND p.page_number=ANY(:pages)
              AND (p.extraction_method LIKE '%OCR%' OR p.extraction_method='IMAGE')'''),
            params={'owner':owner_user_id,'course':course_id,'ids':result.source_material_ids,
                    'pages':list({page for _,page in selected_pages})}).all()
        scanned_pages = {(int(row[0]),int(row[1])) for row in checkpoints} & selected_pages
    if (request_plan.needs_visual or scanned_pages) and result.evidence:
        materials = session.exec(text('''SELECT id,file_path,mime_type,display_name,active_index_version
            FROM studymaterial WHERE owner_user_id=:owner AND course_id=:course
            AND index_status='READY' AND deleted_at IS NULL AND id=ANY(:ids)'''),
            params={'owner':owner_user_id,'course':course_id,'ids':result.source_material_ids}).all()
        by_id = {int(row[0]):row for row in materials}
        pages = set()
        # Source-wide tasks already selected a bounded coverage sample. Do not
        # arbitrarily discard most of its scans: use the shared byte budget.
        # A separate page bound still prevents tiny pages from being unlimited.
        page_limit = 32 if request_plan.scope == 'course' else 8
        for item in result.evidence:
            key = (item.material_id, item.page_start)
            if not request_plan.needs_visual and key not in scanned_pages:
                continue
            if key in pages or item.material_id not in by_id:
                continue
            pages.add(key); material = by_id[item.material_id]
            result.visual_sources.append(dict(owner_user_id=owner_user_id,
                material_id=item.material_id, page_number=item.page_start,
                reference=material[1],mime_type=material[2],display_name=material[3],
                index_version=material[4]))
            if len(pages) == page_limit:
                break
        if scanned_pages:
            result.ocr_reading_hints = [dict(material_id=item.material_id,
                page_start=item.page_start,page_end=item.page_end,text=item.text)
                for item in result.evidence if any((item.material_id,page) in scanned_pages
                    for page in range(item.page_start,item.page_end+1))]
            # OCR is a search index, not a second factual source competing
            # with the original scan. It can omit the very mark that makes a
            # printed option false. Keep evidence for retrieval/citations but
            # do not pass its lossy transcription as generation facts.
            result.note_context = [
                (f'[KANIT material_id={item.material_id} sayfa={item.page_start} '
                 f'bölüm={item.section_title or "-"} tür=SCAN]\n'
                 + ('Bilgi için ekli orijinal sayfayı incele; OCR yalnız arama için kullanıldı.'
                    if (item.material_id,item.page_start) in pages else
                    'Bu taranmış sayfanın görseli bu turda eklenmedi; bilgi kanıtı olarak kullanma.'))
                if any((item.material_id,page) in scanned_pages
                       for page in range(item.page_start,item.page_end+1)) else context
                for item,context in zip(result.evidence,result.note_context)
            ]
            result.note_context.insert(0,
                'OCR KAYNAK UYARISI: Seçilen taranmış sayfalarda metin çıkarımı işaretleri, '
                'yanlış şıkları ve el yazısı düzeltmelerini kaybedebilir. Ekli sayfa görselleri '
                'OCR metninden üstündür. Soru kökü/şık içindeki ifadeleri kendiliğinden bilgi '
                'sayma; yalnız açıkça doğrulanan cevap ve açıklamaları kullan. Görseli '
                'eklenmeyen taranmış sayfalardaki şıkları veya tartışmalı eşleştirmeleri '
                'doğrulanmış bilgi sayma.')
        logger.info('Academic source visuals scanned_pages=%s selected_pages=%s',
                    len(scanned_pages),len(result.visual_sources))
    if _source_rows is None and request_plan.scope == 'course' and request_plan.source_kind == 'notes' and result.evidence:
        originals={(v['material_id'],v['page_number']) for v in result.visual_sources}
        evidence_pages={(item.material_id,page) for item in result.evidence
                        for page in range(item.page_start,item.page_end+1)}
        totals=session.exec(text('''SELECT
            (SELECT COUNT(*) FROM studyindexchunk c JOIN studymaterial m
             ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
             AND m.course_id=c.course_id AND m.active_index_version=c.index_version
             WHERE c.owner_user_id=:owner AND c.course_id=:course
             AND m.index_status='READY' AND m.deleted_at IS NULL
             AND c.id<>ALL(:chunks) AND
             (c.page_start<1 OR c.page_end<c.page_start OR
              (SELECT COUNT(*) FROM jsonb_to_recordset(CAST(:originals AS jsonb))
               AS v(material_id integer,page_number integer)
               WHERE v.material_id=c.material_id AND v.page_number BETWEEN c.page_start AND c.page_end)
              < c.page_end-c.page_start+1)),
            (SELECT COUNT(*) FROM studyindexpage p JOIN studymaterial m
             ON m.id=p.material_id AND m.owner_user_id=p.owner_user_id
             AND m.course_id=p.course_id AND m.active_index_version=p.index_version
             WHERE p.owner_user_id=:owner AND p.course_id=:course
             AND m.index_status='READY' AND m.deleted_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM jsonb_to_recordset(CAST(:evidence_pages AS jsonb))
                 AS v(material_id integer,page_number integer)
                 WHERE v.material_id=p.material_id AND v.page_number=p.page_number)),
            (SELECT COUNT(*) FROM studyindexpage p JOIN studymaterial m
             ON m.id=p.material_id AND m.owner_user_id=p.owner_user_id
             AND m.course_id=p.course_id AND m.active_index_version=p.index_version
             WHERE p.owner_user_id=:owner AND p.course_id=:course
             AND m.index_status='READY' AND m.deleted_at IS NULL)'''),
            params={'owner':owner_user_id,'course':course_id,
                    'chunks':[item.chunk_id for item in result.evidence],
                    'originals':json.dumps([{'material_id':m,'page_number':p} for m,p in originals]),
                    'evidence_pages':json.dumps([{'material_id':m,'page_number':p} for m,p in evidence_pages])}).first()
        result.source_coverage_complete=bool(totals and int(totals[0])==0
            and int(totals[1])==0 and int(totals[2])>0
            and scanned_pages <= originals)
    return result
