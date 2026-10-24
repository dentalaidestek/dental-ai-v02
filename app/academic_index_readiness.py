"""Owned current-generation readiness and bounded recovery; no job mutation."""
from collections import OrderedDict
from datetime import datetime, timezone
import threading
import time

from sqlalchemy import text

_wake_lock = threading.Lock()
_wake_times = OrderedDict()
RECOVERY_COOLDOWN_SECONDS = 60


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def course_has_failed_build(session, *, owner_user_id, course_id):
    # Material status alone remains PROCESSING (or READY for an upgrade) when
    # a worker terminates its job. Never mistake that terminal job for progress.
    return bool(session.execute(text('''
        SELECT 1 FROM studymaterial m LEFT JOIN studyindexjob j
          ON j.material_id=m.id AND j.owner_user_id=m.owner_user_id
         AND j.course_id=m.course_id AND j.index_version=m.building_index_version
        WHERE m.owner_user_id=:owner AND m.course_id=:course
          AND m.deleted_at IS NULL AND m.building_index_version IS NOT NULL
          AND (j.id IS NULL OR j.status IN ('FAILED','CANCELLED')) LIMIT 1
    '''), {'owner': owner_user_id, 'course': course_id}).first())


def course_has_due_build(session, *, owner_user_id, course_id):
    # Workers already reclaim expired leases. A wake must not requeue failed,
    # deleted, superseded, future-retry or actively leased work.
    return bool(session.execute(text('''
        SELECT 1 FROM studymaterial m JOIN studyindexjob j
          ON j.material_id=m.id AND j.owner_user_id=m.owner_user_id
         AND j.course_id=m.course_id AND j.index_version=m.building_index_version
        WHERE m.owner_user_id=:owner AND m.course_id=:course
          AND m.deleted_at IS NULL
          AND ((j.status='QUEUED' AND (j.next_retry_at IS NULL OR j.next_retry_at<=:now))
            OR (j.status='RUNNING' AND j.lease_until IS NOT NULL AND j.lease_until<=:now))
        LIMIT 1
    '''), {'owner': owner_user_id, 'course': course_id, 'now': _now()}).first())


def allow_recovery_poll_wake(*, owner_user_id, course_id):
    """Coalesce 15-second UI probes; upload dispatch remains immediate."""
    stamp = time.monotonic()
    key = (owner_user_id, course_id)
    with _wake_lock:
        previous = _wake_times.get(key)
        if previous is not None and stamp - previous < RECOVERY_COOLDOWN_SECONDS:
            return False
        _wake_times[key] = stamp
        _wake_times.move_to_end(key)
        while len(_wake_times) > 2048:
            _wake_times.popitem(last=False)
        return True
