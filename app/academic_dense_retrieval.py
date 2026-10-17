"""Optional existing-vector search; vendor calls never hold a read transaction.

New FTS-only courses incur no embedding call. Vectors must belong to the same
published owner/course/index and configured Gemini model/dimensions.
"""
from dataclasses import dataclass
import logging
import math
from sqlalchemy import text

logger=logging.getLogger('uvicorn.error.academic_dense_retrieval')


@dataclass(frozen=True)
class QueryEmbedding:
    provider: str
    model: str
    vector: tuple[float, ...]

    def __post_init__(self):
        if (self.provider != 'gemini' or not self.model or not self.vector
                or len(self.vector)>3072 or not all(math.isfinite(value) for value in self.vector)
                or not any(self.vector)):
            raise ValueError('invalid academic query embedding')


def prepare_query_embedding(understanding, *, session_factory, owner_user_id, course_id):
    plan=getattr(understanding,'plan',None)
    if not plan or getattr(plan,'export_previous_answer',False) or plan.operation=='clarify' or plan.scope!='topic' or not plan.retrieval_queries:
        return None
    from app.study_provider import GeminiStudyProvider, get_embedding_target, get_embedding_dimensions, target_available
    target=get_embedding_target()
    if target.provider!='gemini':
        return None
    dimensions=get_embedding_dimensions()
    domain="c.content_kind <> 'QUESTION'" if plan.source_kind=='notes' else "TRUE"
    with session_factory() as session:
        if session.get_bind().dialect.name!='postgresql':
            return None
        # Most newly indexed courses are FTS-only. Establish vector readiness
        # using metadata before measuring any chunk bodies across the course.
        ready=session.exec(text(f'''SELECT 1
            FROM studyindexchunk c JOIN studymaterial m
              ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
             AND m.course_id=c.course_id AND m.active_index_version=c.index_version
            WHERE c.owner_user_id=:owner AND c.course_id=:course AND {domain}
              AND m.index_status='READY' AND m.deleted_at IS NULL
              AND c.embedding_array IS NOT NULL
              AND c.embedding_provider=:provider AND c.embedding_model=:model
              AND c.embedding_dimensions=:dimensions
              AND NOT EXISTS (SELECT 1 FROM studyindexchunk pending
                WHERE pending.material_id=c.material_id AND pending.owner_user_id=c.owner_user_id
                  AND pending.course_id=c.course_id AND pending.index_version=c.index_version
                  AND (pending.embedding_array IS NULL
                       OR pending.embedding_provider IS DISTINCT FROM :provider
                       OR pending.embedding_model IS DISTINCT FROM :model
                       OR pending.embedding_dimensions IS DISTINCT FROM :dimensions))
            LIMIT 1'''),params={'owner':owner_user_id,'course':course_id,
                'provider':target.provider,'model':target.model,'dimensions':dimensions}).first()
        if not ready:
            return None
        totals=session.exec(text(f'''SELECT COUNT(*),
            COALESCE(SUM(length(coalesce(c.text_content,''))+length(coalesce(c.section_title,''))+200),0),
            COUNT(*) FILTER (WHERE c.embedding_array IS NOT NULL
              AND c.embedding_provider=:provider AND c.embedding_model=:model
              AND c.embedding_dimensions=:dimensions
              AND NOT EXISTS (SELECT 1 FROM studyindexchunk pending
                WHERE pending.material_id=c.material_id AND pending.owner_user_id=c.owner_user_id
                  AND pending.course_id=c.course_id AND pending.index_version=c.index_version
                  AND (pending.embedding_array IS NULL
                       OR pending.embedding_provider IS DISTINCT FROM :provider
                       OR pending.embedding_model IS DISTINCT FROM :model
                       OR pending.embedding_dimensions IS DISTINCT FROM :dimensions)))
            FROM studyindexchunk c JOIN studymaterial m
              ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
             AND m.course_id=c.course_id AND m.active_index_version=c.index_version
            WHERE c.owner_user_id=:owner AND c.course_id=:course AND {domain}
              AND m.index_status='READY' AND m.deleted_at IS NULL'''),params={
                'owner':owner_user_id,'course':course_id,'provider':target.provider,
                'model':target.model,'dimensions':dimensions}).first()
        if not totals or not int(totals[2]):
            return None
        from app.academic_evidence_context import MAX_CONTEXT_ROWS, MAX_CONTEXT_CHARS
        if (plan.source_kind=='notes' and not plan.needs_visual
                and int(totals[0])<=MAX_CONTEXT_ROWS and int(totals[1])<=MAX_CONTEXT_CHARS):
            return None
    # The short database session is closed before the external request.
    provider=GeminiStudyProvider()
    provider.max_attempts=1
    if not provider.api_key or not target_available(target):
        return None
    try:
        vector=tuple(provider.embed_text(model=target.model,
            text='\n'.join(plan.retrieval_queries),dimensions=dimensions))
        if len(vector)!=dimensions:
            raise ValueError('embedding dimension mismatch')
        return QueryEmbedding(target.provider,target.model,vector)
    except Exception as error:
        logger.warning('Academic dense query unavailable type=%s; retaining owned lexical search',type(error).__name__)
        return None


def hybrid_candidates(linked, ranked, searches, limit):
    """Keep literal subjects, then alternate RRF semantic hits and source links."""
    from app.academic_semantic_retrieval import SectionEvidenceRows, _balanced_candidates
    if isinstance(linked,SectionEvidenceRows):
        # Explicit source sections are complete evidence, not a top-k list.
        present={int(row[0]) for row in linked}
        return SectionEvidenceRows([*linked,*(row for row in ranked if row[10] is not None and int(row[0]) not in present)])
    picked,seen=[],set()
    def add(row):
        if int(row[0]) not in seen:
            picked.append(row);seen.add(int(row[0]))
    import re
    for phrase in searches:
        terms=set(re.findall(r'[^\W_]+',phrase.casefold()))
        matches=[row for row in linked if terms.intersection(re.findall(
            r'[^\W_]+',((row[5] or '')+' '+(row[7] or '')).casefold()))]
        if matches:
            add(_balanced_candidates(matches,(phrase,),1)[0])
        if len(picked)>=limit:
            return picked
    dense=[row for row in ranked if row[10] is not None]
    for offset in range(max(len(dense),len(linked))):
        for pool in (dense,linked):
            if offset<len(pool):
                add(pool[offset])
                if len(picked)>=limit:
                    return picked
    return picked
