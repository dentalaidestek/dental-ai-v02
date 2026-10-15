"""Representative evidence from every owned published document, without FTS bias."""
from sqlalchemy import text


def retrieve_document_samples(session, *, request_plan, owner_user_id, course_id, query,
                              recent_history=None, **unused):
    from app.academic_semantic_retrieval import retrieve_semantic_context
    from app.academic_source_batches import retrieve_row_batches
    rows=list(session.exec(text('''
        WITH owned AS (
          SELECT c.id,c.material_id,m.display_name,c.page_start,c.page_end,
                 c.section_title,c.content_kind,c.text_content,c.chunk_index,c.semantic_json
          FROM studyindexchunk c JOIN studymaterial m
            ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
           AND m.course_id=c.course_id AND m.active_index_version=c.index_version
          WHERE c.owner_user_id=:owner AND c.course_id=:course
            AND m.index_status='READY' AND m.deleted_at IS NULL
        ), pages AS (
          SELECT material_id,page_start,MAX(CASE WHEN content_kind='QUESTION' THEN 1 ELSE 0 END) AS priority
          FROM owned GROUP BY material_id,page_start
        ), chosen AS (
          SELECT material_id,page_start,ROW_NUMBER() OVER (
            PARTITION BY material_id ORDER BY priority,page_start) AS position FROM pages
        )
        SELECT c.id,c.material_id,c.display_name,c.page_start,c.page_end,
               c.section_title,c.content_kind,c.text_content,
               NULL::BIGINT,NULL::DOUBLE PRECISION,NULL::BIGINT,NULL::DOUBLE PRECISION,
               1.0::DOUBLE PRECISION,c.chunk_index,c.semantic_json
        FROM owned c JOIN chosen p ON p.material_id=c.material_id AND p.page_start=c.page_start
        WHERE p.position<=2 ORDER BY c.material_id,c.page_start,c.chunk_index,c.id
    '''),params={'owner':owner_user_id,'course':course_id}).all())
    # Let the existing complete batcher enforce byte/page budgets. The sample
    # contains every file; it makes no claim to have read every page.
    if rows:
        result=retrieve_row_batches(session,rows=rows,owner_user_id=owner_user_id,
            course_id=course_id,query=query,request_plan=request_plan,recent_history=recent_history)
    else:
        result=retrieve_semantic_context(session,owner_user_id=owner_user_id,
            course_id=course_id,query=query,request_plan=request_plan,_source_rows=[])
    names=list(dict.fromkeys(row[2] for row in rows))
    result.study_task['document_inventory']=names
    result.study_task['document_sample']=True
    result.source_coverage_complete=False
    return result
