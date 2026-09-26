from pathlib import Path

from app import main


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
BASE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
ACCOUNT = (ROOT / "app" / "templates" / "account.html").read_text(encoding="utf-8")
SW = (ROOT / "app" / "static" / "push-sw.js").read_text(encoding="utf-8")


def test_web_push_is_delivery_channel_of_notice_created():
    publish = MAIN.split("async def _publish_realtime_event", 1)[1].split("def _notify_user", 1)[0]
    assert 'event.event_type == "NOTICE_CREATED"' in publish
    assert "_deliver_web_push_for_notice(event)" in publish
    assert "await user_realtime_socket_hub.send" in publish


def test_push_failure_is_outside_domain_transaction_and_isolated():
    deliver = MAIN.split("async def _deliver_web_push_for_notice", 1)[1].split("async def _publish_realtime_event", 1)[0]
    assert "asyncio.to_thread" in deliver
    assert "except Exception" in deliver
    assert "logger.exception" in deliver
    notify = MAIN.split("def _notify_user", 1)[1].split("def _resolve_notifications", 1)[0]
    assert "webpush(" not in notify


def test_push_subscription_is_multi_device_and_expired_devices_are_disabled():
    assert "class WebPushSubscription" in MAIN
    assert "user_id: int = Field(index=True)" in MAIN
    assert "endpoint: str = Field(index=True, unique=True)" in MAIN
    sender = MAIN.split("def _send_web_push_sync", 1)[1].split("async def _deliver_web_push_for_notice", 1)[0]
    assert "code in {404, 410}" in sender
    assert "subscription.disabled_at" in sender


def test_push_delivery_is_deduplicated_per_notice_and_subscription():
    assert "class WebPushDelivery" in MAIN
    sender = MAIN.split("def _send_web_push_sync", 1)[1].split("async def _deliver_web_push_for_notice", 1)[0]
    assert 'delivery_key = f"notice:{notice.id}:subscription:{subscription.id}"' in sender
    assert "except IntegrityError:" in sender


def test_permission_is_only_requested_from_account_button_interaction():
    assert "Notification.requestPermission()" in ACCOUNT
    listener = ACCOUNT.split("button.addEventListener('click'", 1)[1]
    assert "Notification.requestPermission()" in listener
    assert "Notification.requestPermission()" not in BASE


def test_foreground_uses_existing_sync_socket_instead_of_general_push():
    assert 'type:"visibility",visible:!document.hidden' in BASE
    assert 'kind=="visibility"' in MAIN
    deliver = MAIN.split("async def _deliver_web_push_for_notice", 1)[1].split("async def _publish_realtime_event", 1)[0]
    assert "has_visible_session" in deliver


def test_service_worker_payload_is_privacy_minimized_and_internal_only():
    assert 'const title = "Dental AI"' in SW
    assert "target_url" in SW
    assert "patient" not in SW.lower()
    assert "clinical" not in SW.lower()
    assert "clients.openWindow" in SW


def test_messages_and_bell_contract_remains_separate():
    assert 'evt.event_type==="MESSAGE_CREATED"' in BASE
    assert 'evt.event_type==="CASE_CREATED"' in BASE
    assert 'evt.event_type==="NOTICE_CREATED"' in BASE
    assert "bumpMessageBadge" in BASE
    notice_branch = BASE.split('evt.event_type==="NOTICE_CREATED"', 1)[1].split("else if", 1)[0]
    assert "bumpMessageBadge" not in notice_branch


def test_push_copy_never_uses_notice_message_or_clinical_detail():
    copy = MAIN.split("def _web_push_copy", 1)[1].split("def _web_push_status_code", 1)[0]
    assert "notice.message" not in copy
    assert "clinical_summary" not in copy
    assert "patient" not in copy.lower()
