"""Gemini-directed owned retrieval, without the legacy language/reranking engine.

Search ranking is lexical, not a claim that the retrieved candidates answer the
question. Gemini assesses support in the final grounded response.
"""
from __future__ import annotations

import re
import logging
from sqlalchemy import text
from app.academic_request_understanding import StudyRequest
from app.academic_chunk_links import get_course_links, source_nodes
from app.study_retrieval_v2 import (
    Evidence, RetrievalResult, _fts_rows, _semantic_fts_query,
    _semantic_fts_fallback, _question_rows, _academic_question_rows,
    _coverage_evidence_rows, _coverage_hydration_ids, get_or_build_coverage_plan,
)

logger = logging.getLogger('uvicorn.error.academic_semantic_retrieval')


def _linked_candidates(session, rows, searches, *, owner_user_id, course_id, limit):
    """Keep Gemini's independent subjects balanced while following source links."""
    pools = [_balanced_candidates(rows, (phrase,), limit) for phrase in searches]
    seeds = []
    for phrase, pool in zip(searches, pools):
        wanted = set(re.findall(r'[^\W_]+', phrase.casefold()))
        aligned = [row for row in pool if wanted.intersection(
            re.findall(r'[^\W_]+', ((row[5] or '') + ' ' + (row[7] or '')).casefold()))]
        seeds.append(aligned[:2])
    if not any(source_nodes(row) or row[5] and len(str(row[5]).strip()) >= 6
               for group in seeds for row in group):
        return _balanced_candidates(rows, searches, limit)
    links = get_course_links(session, owner_user_id=owner_user_id, course_id=course_id)
    linked_ids = [links.related_ids(group, max(2, limit // len(pools))) for group in seeds]
    ids = list(dict.fromkeys(cid for group in linked_ids for cid in group))
    hydrated = _coverage_evidence_rows(session, owner_user_id=owner_user_id,
        course_id=course_id, chunk_ids=ids, limit=min(48, len(ids))) if ids else []
    by_id = {int(row[0]): row for row in hydrated}
    combined = []
    for pool, group in zip(pools, linked_ids):
        related = [by_id[cid] for cid in group if cid in by_id]
        merged = pool[:2]
        for offset in range(max(len(pool)-2, len(related))):
            if offset < len(related):
                merged.append(related[offset])
            if offset + 2 < len(pool):
                merged.append(pool[offset + 2])
        combined.append(merged)
    selected, seen = [], set()
    for offset in range(max((len(p) for p in combined), default=0)):
        for pool in combined:
            if offset < len(pool) and int(pool[offset][0]) not in seen:
                row = pool[offset]
                seen.add(int(row[0])); selected.append(row)
                if len(selected) == limit:
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
                              request_plan, recent_history=None, limit=16):
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
    if request_plan.scope == 'course' and request_plan.source_kind == 'questions':
        rows = _question_rows(session, owner_user_id=owner_user_id, course_id=course_id,
                              limit=17, after_cursor=_source_cursor(recent_history) if request_plan.continue_source else None)
        result.has_more = len(rows) > 16
        rows = rows[:16]
        result.retrieval_mode = 'questions_exhaustive'
    elif request_plan.scope == 'course':
        count = min(48, max(24, request_plan.count or 0,
                           48 if request_plan.depth == 'detailed' else 24))
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
                if request_plan.source_kind == 'questions' or not rows else
                _linked_candidates(session, rows, searches, owner_user_id=owner_user_id,
                                   course_id=course_id, limit=limit))
        result.retrieval_mode = 'semantic_candidates'
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
    return result
