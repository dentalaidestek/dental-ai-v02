"""Literal appointment anchors resolve locally, with approximate times unconfirmed."""
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app import voice_exam_core as core


ISTANBUL = ZoneInfo('Europe/Istanbul')
SUNDAY = datetime(2026, 11, 8, 12, tzinfo=ISTANBUL)
PROPOSAL = 'Haftaya pazartesi saat 11.00 gibi sabah saatlerine gelebilir misiniz?'
ACCEPTANCE = 'Evet, gelebilirim.'


@pytest.mark.parametrize('now,proposal,acceptance,expected', [
    (SUNDAY, 'Haftaya pazartesi saat 11.00 gelin.', ACCEPTANCE, '2026-11-09T11:00'),
    (datetime(2026, 11, 11, 12, tzinfo=ISTANBUL), 'Haftaya pazartesi saat 11.00 gelin.', ACCEPTANCE, '2026-11-16T11:00'),
    (datetime(2026, 11, 9, 9, tzinfo=ISTANBUL), 'Haftaya pazartesi saat 11.00 gelin.', ACCEPTANCE, '2026-11-16T11:00'),
    (SUNDAY, 'Gelecek hafta salı saat 14:30 gelin.', 'Gelecek hafta salı 14:30 gelirim.', '2026-11-10T14:30'),
    (SUNDAY, 'Haftaya pazartesi saat 11.00 gelin.', 'Pazartesi 11.00 gelirim.', '2026-11-09T11:00'),
    (SUNDAY, 'Pazartesi 11:00 gelin.', ACCEPTANCE, '2026-11-09T11:00'),
    (datetime(2026, 11, 9, 9, tzinfo=ISTANBUL), 'Pazartesi 11:00 gelin.', ACCEPTANCE, None),
    # Local Monday has already begun even though UTC is still Sunday.
    (datetime(2026, 11, 8, 22, 30, tzinfo=ZoneInfo('UTC')), 'Haftaya pazartesi 11:00 gelin.', ACCEPTANCE, '2026-11-16T11:00'),
])
def test_calendar_week_resolution_and_repeated_acceptance_day(now, proposal, acceptance, expected):
    assert core.resolve_appointment(proposal, acceptance, now) == expected


@pytest.mark.parametrize('proposal,acceptance', [
    ('Haftaya pazartesi 11:00 gelin.', ''),
    ('Haftaya pazartesi 11:00 gelin.', 'Belki gelebilirim.'),
    ('Haftaya pazartesi 11:00 gelin.', 'Salı 11:00 gelirim.'),
    ('Haftaya pazartesi 11:00 gelin.', 'Pazartesi 12:00 gelirim.'),
    ('Haftaya pazartesi 11:00 gelin.', 'Evet, gelebilirim. Ama iptal edelim.'),
    ('Haftaya pazartesi veya salı 11:00 gelin.', ACCEPTANCE),
    ('Haftaya pazartesi sabah akşam 11:00 gelin.', ACCEPTANCE),
    ('Haftaya pazartesi 11:00 veya 12:00 gibi gelin.', ACCEPTANCE),
    ('Haftaya pazartesi 11:00 gibi gelmeyin, iptal.', ACCEPTANCE),
    ('Bu hafta pazartesi 11:00 gelin.', ACCEPTANCE),
    ('07.11.2026 11:00 gibi gelin.', ACCEPTANCE),
    ('Haftaya pazartesi salı 11:00 gibi gelin.', ACCEPTANCE),
])
def test_approximate_candidate_preserves_rejection_of_uncertain_or_conflicting_anchors(proposal, acceptance):
    assert core.resolve_appointment(proposal, acceptance, SUNDAY, allow_approximate=True) is None


def test_approximate_accepted_time_requires_confirmation():
    assert core.resolve_appointment(PROPOSAL, ACCEPTANCE, SUNDAY) is None
    assert core.resolve_appointment(PROPOSAL, ACCEPTANCE, SUNDAY, allow_approximate=True) == '2026-11-09T11:00'


@pytest.fixture
def frozen_sunday(monkeypatch):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return SUNDAY.astimezone(tz) if tz else SUNDAY.replace(tzinfo=None)
    monkeypatch.setattr(core, 'datetime', FrozenDateTime)


@pytest.mark.parametrize('approximate,status,agreed', [
    (True, 'time_confirmation_required', False),
    (False, 'agreed', True),
])
def test_normalize_prefills_only_grounded_local_calendar_time(frozen_sunday, approximate, status, agreed):
    proposal = PROPOSAL if approximate else PROPOSAL.replace(' gibi', '')
    result = core.normalize({'transcript': 'Hekim: ' + proposal + '\nHasta: ' + ACCEPTANCE,
                             'appointment': {'quote': proposal, 'acceptance_quote': ACCEPTANCE,
                                             'start_at': '2099-01-01T00:00', 'agreed': True}})
    assert result['appointment'] == {'quote': proposal, 'acceptance_quote': ACCEPTANCE,
                                     'start_at': '2026-11-09T11:00', 'agreed': agreed,
                                     'resolution_status': status}


@pytest.mark.parametrize('acceptance', ['', ACCEPTANCE])
def test_unanchored_or_missing_acceptance_never_prefills_candidate(frozen_sunday, acceptance):
    result = core.normalize({'transcript': PROPOSAL,
                             'appointment': {'quote': PROPOSAL, 'acceptance_quote': acceptance}})
    assert 'start_at' not in result['appointment']
    assert not result['appointment'].get('agreed')
