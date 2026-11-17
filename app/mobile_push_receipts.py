"""Durable, owner-scoped Expo ticket/receipt lifecycle.

Only event/device identifiers, a one-way token fingerprint and Expo ticket IDs are
stored. Notification text, route payloads, patient identifiers and raw tokens are
never persisted by this module.
"""
from __future__ import annotations

import logging
import secrets
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, or_, update
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.mobile_push import _safe_error_code, get_push_receipts, is_valid_expo_push_token, token_fingerprint

logger = logging.getLogger(__name__)

RECEIPT_FIRST_CHECK = timedelta(minutes=15)
RECEIPT_TTL = timedelta(hours=24)
RECEIPT_MAX_ATTEMPTS = 8
RECEIPT_BATCH_LIMIT = 100
SENDING_LEASE = timedelta(minutes=2)
RECEIPT_LEASE = timedelta(seconds=45)
TERMINAL_RETENTION = timedelta(days=30)

_last_poll_at = 0.0
_last_maintenance_at = 0.0


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def reserve_mobile_push_deliveries(engine, *, event_id: int, user_id: int, devices):
    """Atomically reserve one send per event/device; duplicate event replay is a no-op."""
    from app.main import MobilePushDelivery

    stamp = _now()
    reserved = []
    with Session(engine, expire_on_commit=False) as session:
        for device in devices:
            token = getattr(device, "expo_push_token", None)
            if (
                getattr(device, "user_id", None) != user_id
                or not getattr(device, "enabled", False)
                or not is_valid_expo_push_token(token)
            ):
                continue
            lease_token = secrets.token_hex(24)
            row = MobilePushDelivery(
                event_id=event_id,
                user_id=user_id,
                device_id=device.device_id,
                token_fingerprint=token_fingerprint(token),
                status="SENDING",
                lease_token=lease_token,
                lease_until=stamp + SENDING_LEASE,
                created_at=stamp,
                updated_at=stamp,
            )
            try:
                with session.begin_nested():
                    session.add(row)
                    session.flush()
            except IntegrityError:
                # The unique event/device key is the cross-process duplicate guard.
                continue
            reserved.append({
                "id": row.id,
                "device_id": device.device_id,
                "token": token,
                "token_fingerprint": row.token_fingerprint,
                "lease_token": lease_token,
            })
        session.commit()
    return reserved


def _disable_device_if_current(session, delivery) -> bool:
    from app.main import MobilePushDevice

    device = session.exec(select(MobilePushDevice).where(
        MobilePushDevice.user_id == delivery.user_id,
        MobilePushDevice.device_id == delivery.device_id,
    ).with_for_update()).first()
    if device is None or token_fingerprint(device.expo_push_token) != delivery.token_fingerprint:
        return False
    device.enabled = False
    device.updated_at = _now()
    return True


def complete_mobile_push_deliveries(engine, reserved, result) -> int:
    """Persist safe ticket metadata and immediately disable ticket-level dead tokens."""
    from app.main import MobilePushDelivery

    ticket_map = {
        item.get("token_fingerprint"): item
        for item in (result or {}).get("tickets", [])
        if isinstance(item, dict) and isinstance(item.get("token_fingerprint"), str)
    }
    first_error = next(iter((result or {}).get("errors", [])), {})
    fallback_error = first_error.get("error_code") if isinstance(first_error, dict) else None
    completed = 0
    stamp = _now()
    with Session(engine, expire_on_commit=False) as session:
        for item in reserved:
            row = session.get(MobilePushDelivery, item["id"])
            if (
                row is None or row.status != "SENDING"
                or row.lease_token != item["lease_token"]
            ):
                continue
            ticket = ticket_map.get(item["token_fingerprint"])
            if ticket and ticket.get("status") == "ok" and ticket.get("ticket_id"):
                row.ticket_id = ticket["ticket_id"]
                row.status = "PENDING_RECEIPT"
                row.next_check_at = stamp + RECEIPT_FIRST_CHECK
                row.error_code = None
            elif ticket and ticket.get("error_code") == "DeviceNotRegistered":
                row.status = "DEVICE_NOT_REGISTERED"
                row.error_code = "DeviceNotRegistered"
                _disable_device_if_current(session, row)
            elif ticket:
                row.status = "TICKET_ERROR"
                row.error_code = _safe_error_code(ticket.get("error_code"))
            else:
                # A timeout may occur after Expo accepted the batch. Do not resend
                # automatically because doing so could duplicate the notification.
                row.status = "SEND_UNCERTAIN"
                row.error_code = _safe_error_code(fallback_error) if fallback_error else "NO_TICKET"
            row.updated_at = stamp
            row.lease_token = None
            row.lease_until = None
            completed += 1
        session.commit()
    return completed


def _schedule_receipt_retry(row, stamp: datetime, error_code: str) -> None:
    age = stamp - row.created_at
    if age >= RECEIPT_TTL or row.attempts >= RECEIPT_MAX_ATTEMPTS:
        row.status = "RECEIPT_EXPIRED"
        row.checked_at = stamp
        row.error_code = error_code
        return
    delay_minutes = min(15 * (2 ** max(0, row.attempts - 1)), 240)
    row.status = "PENDING_RECEIPT"
    row.next_check_at = stamp + timedelta(minutes=delay_minutes)
    row.error_code = error_code


def poll_due_mobile_push_receipts(engine, *, limit: int = RECEIPT_BATCH_LIMIT) -> int:
    """Claim at most 100 due tickets, fetch receipts outside the DB transaction, then reconcile."""
    from app.main import MobilePushDelivery

    if not isinstance(limit, int) or limit < 1 or limit > RECEIPT_BATCH_LIMIT:
        raise ValueError("Receipt polling limit must be between 1 and 100")
    stamp = _now()
    claimed = []
    with Session(engine, expire_on_commit=False) as session:
        rows = session.exec(
            select(MobilePushDelivery)
            .where(
                MobilePushDelivery.status == "PENDING_RECEIPT",
                MobilePushDelivery.next_check_at <= stamp,
                or_(MobilePushDelivery.lease_until == None, MobilePushDelivery.lease_until <= stamp),
            )
            .order_by(MobilePushDelivery.next_check_at, MobilePushDelivery.id)
            .limit(limit)
            .with_for_update(skip_locked=True)
        ).all()
        for row in rows:
            lease_token = secrets.token_hex(24)
            row.status = "CHECKING"
            row.lease_token = lease_token
            row.lease_until = stamp + RECEIPT_LEASE
            row.attempts += 1
            row.updated_at = stamp
            claimed.append({"id": row.id, "ticket_id": row.ticket_id, "lease_token": lease_token})
        session.commit()

    if not claimed:
        return 0

    try:
        response = get_push_receipts([item["ticket_id"] for item in claimed if item["ticket_id"]])
    except Exception as exc:
        logger.warning("Expo receipt lookup failed: %s", type(exc).__name__)
        response = {"ok": False, "receipts": {}, "error_code": "TRANSPORT"}

    receipts = response.get("receipts", {}) if response.get("ok") else {}
    result_error = _safe_error_code(response.get("error_code")) if not response.get("ok") else "RECEIPT_NOT_READY"
    processed = 0
    checked_at = _now()
    with Session(engine, expire_on_commit=False) as session:
        for item in claimed:
            row = session.get(MobilePushDelivery, item["id"])
            if (
                row is None or row.status != "CHECKING"
                or row.lease_token != item["lease_token"]
            ):
                continue
            receipt = receipts.get(item["ticket_id"]) if isinstance(receipts, dict) else None
            if not response.get("ok") or receipt is None:
                _schedule_receipt_retry(row, checked_at, result_error)
            elif receipt.get("status") == "ok":
                # Expo's receipt confirms FCM/APNs accepted the handoff, not device display.
                row.status = "PROVIDER_ACCEPTED"
                row.checked_at = checked_at
                row.error_code = None
            elif receipt.get("status") == "error":
                details = receipt.get("details") if isinstance(receipt.get("details"), dict) else {}
                code = _safe_error_code(details.get("error"))
                row.status = "DEVICE_NOT_REGISTERED" if code == "DeviceNotRegistered" else "RECEIPT_ERROR"
                row.error_code = code
                row.checked_at = checked_at
                if code == "DeviceNotRegistered":
                    _disable_device_if_current(session, row)
            else:
                row.status = "RECEIPT_ERROR"
                row.error_code = "INVALID_RECEIPT"
                row.checked_at = checked_at
            row.updated_at = checked_at
            row.lease_token = None
            row.lease_until = None
            processed += 1
        session.commit()
    return processed


def _maintain_receipt_rows(engine, *, limit: int = 100) -> int:
    from app.main import MobilePushDelivery

    stamp = _now()
    changed = 0
    with Session(engine) as session:
        stale_sending = session.exec(
            select(MobilePushDelivery.id)
            .where(MobilePushDelivery.status == "SENDING", MobilePushDelivery.lease_until <= stamp)
            .order_by(MobilePushDelivery.id).limit(limit)
        ).all()
        if stale_sending:
            changed += session.exec(update(MobilePushDelivery).where(
                MobilePushDelivery.id.in_(stale_sending),
                MobilePushDelivery.status == "SENDING",
            ).values(
                status="SEND_UNCERTAIN", error_code="SENDER_LEASE_EXPIRED",
                lease_token=None, lease_until=None, updated_at=stamp,
            )).rowcount or 0

        stale_checking = session.exec(
            select(MobilePushDelivery.id)
            .where(MobilePushDelivery.status == "CHECKING", MobilePushDelivery.lease_until <= stamp)
            .order_by(MobilePushDelivery.id).limit(limit)
        ).all()
        if stale_checking:
            changed += session.exec(update(MobilePushDelivery).where(
                MobilePushDelivery.id.in_(stale_checking),
                MobilePushDelivery.status == "CHECKING",
            ).values(
                status="PENDING_RECEIPT", error_code="CHECK_LEASE_EXPIRED",
                next_check_at=stamp + timedelta(minutes=5),
                lease_token=None, lease_until=None, updated_at=stamp,
            )).rowcount or 0

        expired = session.exec(
            select(MobilePushDelivery.id)
            .where(
                MobilePushDelivery.status == "PENDING_RECEIPT",
                MobilePushDelivery.created_at <= stamp - RECEIPT_TTL,
            ).order_by(MobilePushDelivery.id).limit(limit)
        ).all()
        if expired:
            changed += session.exec(update(MobilePushDelivery).where(
                MobilePushDelivery.id.in_(expired),
                MobilePushDelivery.status == "PENDING_RECEIPT",
            ).values(
                status="RECEIPT_EXPIRED", error_code="RECEIPT_TTL_EXPIRED",
                checked_at=stamp, updated_at=stamp,
            )).rowcount or 0

        terminal = [
            "PROVIDER_ACCEPTED", "DEVICE_NOT_REGISTERED", "TICKET_ERROR",
            "RECEIPT_ERROR", "RECEIPT_EXPIRED", "SEND_UNCERTAIN",
        ]
        old_ids = session.exec(
            select(MobilePushDelivery.id)
            .where(
                MobilePushDelivery.status.in_(terminal),
                MobilePushDelivery.updated_at <= stamp - TERMINAL_RETENTION,
            ).order_by(MobilePushDelivery.id).limit(limit)
        ).all()
        if old_ids:
            changed += session.exec(delete(MobilePushDelivery).where(
                MobilePushDelivery.id.in_(old_ids),
            )).rowcount or 0
        session.commit()
    return changed


def run_mobile_push_receipt_maintenance(engine) -> bool:
    """Worker hook: bounded polling and cleanup without adding another timer/service."""
    global _last_poll_at, _last_maintenance_at
    monotonic_now = time.monotonic()
    did_work = False
    if monotonic_now - _last_poll_at >= 60:
        _last_poll_at = monotonic_now
        did_work = poll_due_mobile_push_receipts(engine) > 0 or did_work
    if monotonic_now - _last_maintenance_at >= 300:
        _last_maintenance_at = monotonic_now
        did_work = _maintain_receipt_rows(engine) > 0 or did_work
    return did_work
