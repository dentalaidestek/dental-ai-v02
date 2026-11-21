"""Cookie-session, owner-scoped bounded paging for the web patient profile."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import and_, or_
from sqlmodel import select

from app.patient_history_pagination import (
    HISTORY_PAGE_SIZE,
    decode_history_cursor,
    history_page_slice,
)

router = APIRouter()


def _private_json(payload: dict, status_code: int = 200) -> JSONResponse:
    response = JSONResponse(payload, status_code=status_code)
    response.headers.update({
        "Cache-Control": "private, no-store",
        "Pragma": "no-cache",
        "Vary": "Cookie",
        "X-Content-Type-Options": "nosniff",
    })
    return response


def _authenticated_main_user(request: Request):
    from app import main as main_module

    user = main_module.get_current_user(request)
    if not user:
        return main_module, None, _private_json({"ok": False, "error": "Oturum gerekli."}, 401)
    return main_module, user, None


def _patient_owner(main_module, session, user, patient_id: int):
    patient = session.get(main_module.Patient, patient_id)
    if not patient:
        return None, _private_json({"ok": False, "error": "Hasta bulunamadı."}, 404)
    if user.role != "ADMIN" and patient.owner_user_id != user.id:
        return None, _private_json({"ok": False, "error": "Bu hastaya erişim yetkiniz yok."}, 403)
    return patient.owner_user_id if patient.owner_user_id is not None else user.id, None


def _cursor_or_error(before: Optional[str]):
    try:
        return decode_history_cursor(before), None
    except ValueError:
        return None, _private_json({"ok": False, "error": "Geçersiz geçmiş imleci."}, 400)


def _analysis_page_html(main_module, session, user, patient_id: int, owner_id: int, cursor):
    query = select(main_module.Analysis).where(main_module.Analysis.patient_id == patient_id)
    if user.role != "ADMIN":
        query = query.join(
            main_module.Patient,
            main_module.Analysis.patient_id == main_module.Patient.id,
        ).where(main_module.Patient.owner_user_id == user.id)
    if cursor:
        created_at, record_id = cursor
        query = query.where(or_(
            main_module.Analysis.created_at < created_at,
            and_(
                main_module.Analysis.created_at == created_at,
                main_module.Analysis.id < record_id,
            ),
        ))
    rows = session.exec(
        query.order_by(
            main_module.Analysis.created_at.desc(),
            main_module.Analysis.id.desc(),
        ).limit(HISTORY_PAGE_SIZE + 1)
    ).all()
    page, next_cursor = history_page_slice(rows)
    analysis_ids = [item.id for item in page if item.id is not None]
    voice_review_ids = set()
    analysis_assets = {analysis_id: [] for analysis_id in analysis_ids}
    if analysis_ids:
        voice_review_ids = set(session.exec(
            select(main_module.work_jobs.WorkJob.resource_id).distinct().where(
                main_module.work_jobs.WorkJob.resource_id.in_(analysis_ids),
                main_module.work_jobs.WorkJob.owner_user_id == owner_id,
                main_module.work_jobs.WorkJob.resource_type == "ANALYSIS",
                main_module.work_jobs.WorkJob.kind == "VOICE_REVIEW",
                main_module.work_jobs.WorkJob.status == "DONE",
            )
        ).all())
        for asset in session.exec(
            select(main_module.ImageAsset).where(
                main_module.ImageAsset.analysis_id.in_(analysis_ids)
            )
        ).all():
            analysis_assets.setdefault(asset.analysis_id, []).append(asset)
    html = main_module.templates.env.get_template(
        "patient_analysis_history_items.html"
    ).render(
        analyses=page,
        voice_review_ids=voice_review_ids,
        analysis_assets=analysis_assets,
    )
    return html, next_cursor


def _treatment_page_html(main_module, session, user, patient_id: int, cursor, expanded: bool):
    query = select(main_module.Treatment).where(main_module.Treatment.patient_id == patient_id)
    if user.role != "ADMIN":
        query = query.join(
            main_module.Patient,
            main_module.Treatment.patient_id == main_module.Patient.id,
        ).where(main_module.Patient.owner_user_id == user.id)
    if cursor:
        created_at, record_id = cursor
        query = query.where(or_(
            main_module.Treatment.created_at < created_at,
            and_(
                main_module.Treatment.created_at == created_at,
                main_module.Treatment.id < record_id,
            ),
        ))
    rows = session.exec(
        query.order_by(
            main_module.Treatment.created_at.desc(),
            main_module.Treatment.id.desc(),
        ).limit(HISTORY_PAGE_SIZE + 1)
    ).all()
    page, next_cursor = history_page_slice(rows)
    html = main_module.templates.env.get_template(
        "patient_treatment_history_items.html"
    ).render(
        treatments=page,
        expanded=expanded,
        first_page=False,
    )
    return html, next_cursor


@router.get("/patients/{patient_id}/history/analyses/page")
def patient_analysis_history_page(
    request: Request,
    patient_id: int,
    before: Optional[str] = None,
):
    main_module, user, auth_error = _authenticated_main_user(request)
    if auth_error:
        return auth_error
    cursor, cursor_error = _cursor_or_error(before)
    if cursor_error:
        return cursor_error
    with main_module.Session(main_module.engine, expire_on_commit=False) as session:
        owner_id, access_error = _patient_owner(main_module, session, user, patient_id)
        if access_error:
            return access_error
        html, next_cursor = _analysis_page_html(
            main_module, session, user, patient_id, owner_id, cursor
        )
    return _private_json({
        "ok": True,
        "html": html,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
    })


@router.get("/patients/{patient_id}/history/treatments/page")
def patient_treatment_history_page(
    request: Request,
    patient_id: int,
    before: Optional[str] = None,
    expanded: bool = False,
):
    main_module, user, auth_error = _authenticated_main_user(request)
    if auth_error:
        return auth_error
    cursor, cursor_error = _cursor_or_error(before)
    if cursor_error:
        return cursor_error
    with main_module.Session(main_module.engine, expire_on_commit=False) as session:
        _owner_id, access_error = _patient_owner(main_module, session, user, patient_id)
        if access_error:
            return access_error
        html, next_cursor = _treatment_page_html(
            main_module, session, user, patient_id, cursor, expanded
        )
    return _private_json({
        "ok": True,
        "html": html,
        "next_cursor": next_cursor,
        "has_more": next_cursor is not None,
    })
