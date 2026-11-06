"""Failure diagnostics expose bounded metadata, never patient/provider messages."""
import logging
import pytest
from app import voice_exam_final as final, voice_exam_core as core

def test_final_failure_logs_stage_and_type_without_private_exception_text(monkeypatch,caplog):
    monkeypatch.setattr(final,'retrieve',lambda *a,**k:{'references':[],'unavailable':[],'coverage':'limited','notice':'limited'})
    def fail(*args,**kwargs):
        raise ValueError('PRIVATE_PROVIDER_BODY_AND_PATIENT')
    monkeypatch.setattr(final,'review',fail)
    with caplog.at_level(logging.WARNING),pytest.raises(core.VoiceError):
        final.finalize({'fields':{'plan':{'value':'İnceleme planı','quote':'Önce bakalım.'}}},[])
    assert 'voice_final_failed stage=provider kind=ValueError' in caplog.text
    assert 'PRIVATE_PROVIDER_BODY_AND_PATIENT' not in caplog.text

def test_checklist_overflow_has_count_diagnostics_and_preserves_draft_error(monkeypatch,caplog):
    monkeypatch.setattr(final,'retrieve',lambda *a,**k:{'references':[],'unavailable':[],'coverage':'limited','notice':'limited'})
    monkeypatch.setattr(final,'review',lambda *a,**k:{'questions':[{}]*13,'contradictions':[],'clinical_items':[]})
    with caplog.at_level(logging.WARNING),pytest.raises(core.VoiceError,match='Taslak korunuyor'):
        final.finalize({'fields':{'plan':{'value':'İnceleme planı','quote':'Önce bakalım.'}}},[])
    assert 'stage=checklist' in caplog.text and 'questions=13' in caplog.text
