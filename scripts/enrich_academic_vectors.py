"""Dry-run or bounded Gemini vector enrichment of published source chunks.

Requires DATABASE_URL and explicit --owner/--course. --run authorizes at most
--max-chunks external embedding calls. Completed vectors are reused on resume.
This changes derived vectors only, never source text, OCR, active index version,
readiness or user permissions. No periodic jobs or automatic backfill.
"""
import argparse
import json
import os
from pathlib import Path
import sys
from sqlalchemy import text
from sqlmodel import Session, create_engine

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.academic_dense_retrieval import QueryEmbedding
from app.study_provider import GeminiStudyProvider, get_embedding_target, get_embedding_dimensions


def enrich(session_factory, *, owner_user_id, course_id, max_chunks=32, run=False):
    if owner_user_id<1 or course_id<1 or not 1<=max_chunks<=256:
        raise ValueError('invalid bounded source selection')
    target=get_embedding_target()
    if target.provider!='gemini':
        raise ValueError('Academic vector enrichment requires the configured Gemini provider')
    dimensions=get_embedding_dimensions()
    params=dict(owner=owner_user_id,course=course_id,provider=target.provider,
                model=target.model,dimensions=dimensions,limit=max_chunks)
    scope='''FROM studyindexchunk c JOIN studymaterial m
        ON m.id=c.material_id AND m.owner_user_id=c.owner_user_id
       AND m.course_id=c.course_id AND m.active_index_version=c.index_version
        WHERE c.owner_user_id=:owner AND c.course_id=:course
          AND m.index_status='READY' AND m.deleted_at IS NULL
          AND (c.embedding_array IS NULL OR c.embedding_provider IS DISTINCT FROM :provider
               OR c.embedding_model IS DISTINCT FROM :model
               OR c.embedding_dimensions IS DISTINCT FROM :dimensions)'''
    with session_factory() as session:
        if session.get_bind().dialect.name!='postgresql':
            raise ValueError('a PostgreSQL source database is required')
        pending=session.exec(text('SELECT COUNT(*) '+scope),params=params).first()[0]
        rows=session.exec(text('''SELECT c.id,c.index_version,c.text_sha256,c.text_content,
            c.section_title,m.display_name '''+scope+
            ' ORDER BY c.material_id,c.page_start,c.chunk_index,c.id LIMIT :limit'),params=params).all()
    report=dict(provider=target.provider,model=target.model,dimensions=dimensions,
                pending=int(pending),selected=len(rows),updated=0,skipped_changed=0,
                max_calls=max_chunks,external_calls=0,run=run,
                selected_source_characters=sum(len(row[3] or '')+len(row[4] or '')+len(row[5] or '') for row in rows))
    if not run or not rows:
        return report
    provider=GeminiStudyProvider();provider.max_attempts=1
    for ident,version,sha,body,heading,name in rows:
        # Literal source context improves embeddings without a contextualizer
        # LLM, invented definitions or regenerated OCR.
        document=f'Dosya: {name}\nBaşlık: {heading or "-"}\nKaynak metni:\n{body}'
        report['external_calls']+=1
        vector=tuple(provider.embed_text(model=target.model,text=document,dimensions=dimensions))
        if len(vector)!=dimensions:
            raise ValueError('embedding dimension mismatch')
        embedding=QueryEmbedding(target.provider,target.model,vector)
        with session_factory() as session:
            result=session.exec(text('''UPDATE studyindexchunk c SET
                embedding_provider=:provider,embedding_model=:model,embedding_dimensions=:dimensions,
                embedding_json=:vector_json,embedding_array=:vector,updated_at=CURRENT_TIMESTAMP
                FROM studymaterial m WHERE c.id=:id AND c.owner_user_id=:owner AND c.course_id=:course
                  AND c.index_version=:version AND c.text_sha256=:sha AND c.text_content=:body
                  AND c.section_title IS NOT DISTINCT FROM :heading
                  AND m.id=c.material_id AND m.owner_user_id=c.owner_user_id AND m.course_id=c.course_id
                  AND m.active_index_version=c.index_version AND m.index_status='READY' AND m.deleted_at IS NULL
                  AND m.display_name IS NOT DISTINCT FROM :name'''),params={**params,
                    'id':ident,'version':version,'sha':sha,'body':body,'heading':heading,'name':name,
                    'vector_json':json.dumps(embedding.vector,separators=(',',':')),'vector':list(embedding.vector)})
            if result.rowcount!=1:
                session.rollback();report['skipped_changed']+=1
                continue
            from app.study_retrieval_v2 import _pgvector_available
            if _pgvector_available(session,dimensions):
                session.exec(text('UPDATE studyindexchunk SET embedding_vector=CAST(:vector AS vector) WHERE id=:id'),
                    params={'id':ident,'vector':'['+','.join(str(value) for value in embedding.vector)+']'})
            session.commit();report['updated']+=1
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--owner',type=int,required=True)
    parser.add_argument('--course',type=int,required=True)
    parser.add_argument('--max-chunks',type=int,default=32)
    parser.add_argument('--run',action='store_true')
    args=parser.parse_args()
    if not os.getenv('DATABASE_URL'):
        parser.exit(2,'DATABASE_URL is required. No external calls made.\n')
    engine=create_engine(os.environ['DATABASE_URL'])
    try:
        report=enrich(lambda:Session(engine),owner_user_id=args.owner,course_id=args.course,
                      max_chunks=args.max_chunks,run=args.run)
        print(json.dumps(report,ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'complete':False,'error_type':type(error).__name__,
                          'resume':'Completed vectors are retained; resume with the same bounded selection.'}))
        return 1
    finally:
        engine.dispose()
    return 0


if __name__=='__main__':
    raise SystemExit(main())
