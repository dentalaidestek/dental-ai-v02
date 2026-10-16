"""Private recovery review dataset; never automatically promoted into rules."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import Column, ForeignKey, Integer, Text, text
from sqlmodel import Field, SQLModel

from app.academic_recovery import PLANNER_SYSTEM, recover_once


class AcademicRecoveryEvent(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    owner_user_id: int = Field(sa_column=Column(Integer, ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False))
    course_id: int = Field(sa_column=Column(Integer, ForeignKey("studycourse.id", ondelete="CASCADE"), index=True, nullable=False))
    outcome: str = Field(index=True)
    error_class: str = Field(default="unknown", index=True)
    review_status: str = Field(default="UNREVIEWED", index=True)
    # Private query/plan/evidence identifiers, never public application logs.
    details_json: str = Field(sa_column=Column(Text, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None), index=True)


def recover_course_context(*, session_factory, owner_user_id: int, course_id: int,
                           question: str, history: list[dict], initial):
    if initial.clarification or initial.evidence_sufficient or getattr(initial, "semantic_planner_attempted", False):
        return initial
    from copy import copy
    from app.academic_provider_config import academic_target
    from app.study_provider import get_provider, target_available
    from app.study_retrieval_v2 import retrieve_course_context_v2

    def load_catalog():
        with session_factory() as session:
            session.exec(text("SET LOCAL statement_timeout = '1200ms'"))
            rows = session.exec(text("""
                SELECT m.display_name, headings.titles
                FROM studymaterial m
                LEFT JOIN LATERAL (
                    SELECT string_agg(s.section_title, ' | ') AS titles FROM (
                        SELECT DISTINCT left(c.section_title, 100) AS section_title
                        FROM studyindexchunk c
                        WHERE c.material_id=m.id AND c.owner_user_id=:owner
                          AND c.course_id=:course AND c.index_version=m.active_index_version
                          AND c.section_title IS NOT NULL
                        ORDER BY section_title LIMIT 4
                    ) s
                ) headings ON TRUE
                WHERE m.owner_user_id=:owner AND m.course_id=:course
                  AND m.index_status='READY' AND m.deleted_at IS NULL
                ORDER BY m.id LIMIT 32
            """), params={"owner": owner_user_id, "course": course_id}).all()
            return [{"name": str(row[0] or "")[:120], "headings": str(row[1] or "")[:420]}
                    for row in rows]

    def plan_call(prompt):
        target = academic_target('planner')
        if not target_available(target):
            return None
        # Dedicated adapter: never alter the cached generation provider's
        # timeout/retries. One transport attempt, small output, no retry chain.
        provider = copy(get_provider(target.provider))
        provider.capacity_retry = False
        provider.response_schema = None
        provider.timeout = 4
        provider.max_attempts = 1
        if not provider.api_key:
            return None
        return provider.generate(model=target.model,
            system_prompt=PLANNER_SYSTEM, history=[], prompt=prompt,
            temperature=0, max_output_tokens=700)

    def retrieve(terms):
        # The planner call has completed; only now open a new short Session.
        with session_factory() as session:
            session.exec(text("SET LOCAL statement_timeout = '1500ms'"))
            return retrieve_course_context_v2(session, owner_user_id=owner_user_id,
                course_id=course_id, query=question, recent_history=history,
                recovery_terms=terms)

    def record(event):
        with session_factory() as session:
            session.exec(text("SET LOCAL statement_timeout = '1200ms'"))
            # Lock the owned course while saving; cascading FKs handle deletion.
            owned = session.exec(text("SELECT id FROM studycourse WHERE id=:course AND owner_user_id=:owner FOR UPDATE"),
                                 params={"course": course_id, "owner": owner_user_id}).first()
            if not owned:
                return
            plan = event.get("plan") or {}
            session.add(AcademicRecoveryEvent(owner_user_id=owner_user_id,
                course_id=course_id, outcome=event["outcome"],
                error_class=plan.get("error_class", "unknown"),
                details_json=json.dumps(event, ensure_ascii=False)))
            session.commit()

    return recover_once(question=question, history=history, initial=initial,
        load_catalog=load_catalog, plan_call=plan_call, retrieve=retrieve, record=record)
