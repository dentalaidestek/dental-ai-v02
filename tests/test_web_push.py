from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
BASE = (ROOT / "app" / "templates" / "base.html").read_text(encoding="utf-8")
ACCOUNT = (ROOT / "app" / "templates" / "account.html").read_text(encoding="utf-8")
SW = (ROOT / "app" / "static" / "push-sw.js").read_text(encoding="utf-8")


class WebPushContractTests(unittest.TestCase):
    def test_web_push_is_delivery_channel_of_notice_created(self):
        publish = MAIN.split("async def _publish_realtime_event", 1)[1].split("def _notify_user", 1)[0]
        self.assertIn('event.event_type == "NOTICE_CREATED"', publish)
        self.assertIn("_deliver_web_push_for_notice(event)", publish)
        self.assertIn("await user_realtime_socket_hub.send", publish)

    def test_push_failure_is_outside_domain_transaction_and_isolated(self):
        deliver = MAIN.split("async def _deliver_web_push_for_notice", 1)[1].split("async def _publish_realtime_event", 1)[0]
        self.assertIn("asyncio.to_thread", deliver)
        self.assertIn("except Exception", deliver)
        self.assertIn("logger.exception", deliver)
        notify = MAIN.split("def _notify_user", 1)[1].split("def _resolve_notifications", 1)[0]
        self.assertNotIn("webpush(", notify)

    def test_push_subscription_is_multi_device_and_expired_devices_are_disabled(self):
        self.assertIn("class WebPushSubscription", MAIN)
        self.assertIn("user_id: int = Field(index=True)", MAIN)
        self.assertIn("endpoint: str = Field(index=True, unique=True)", MAIN)
        sender = MAIN.split("def _send_web_push_sync", 1)[1].split("async def _deliver_web_push_for_notice", 1)[0]
        self.assertIn("code in {404, 410}", sender)
        self.assertIn("subscription.disabled_at", sender)

    def test_push_delivery_is_deduplicated_per_notice_and_subscription(self):
        self.assertIn("class WebPushDelivery", MAIN)
        sender = MAIN.split("def _send_web_push_sync", 1)[1].split("async def _deliver_web_push_for_notice", 1)[0]
        self.assertIn('delivery_key = f"notice:{notice.id}:subscription:{subscription.id}"', sender)
        self.assertIn("except IntegrityError:", sender)

    def test_permission_is_only_requested_from_account_button_interaction(self):
        self.assertIn("Notification.requestPermission()", ACCOUNT)
        listener = ACCOUNT.split("button.addEventListener('click'", 1)[1]
        self.assertIn("Notification.requestPermission()", listener)
        self.assertNotIn("Notification.requestPermission()", BASE)

    def test_foreground_suppression_is_process_safe_in_service_worker(self):
        self.assertIn('type:"visibility",visible:!document.hidden', BASE)
        self.assertIn('kind=="visibility"', MAIN)
        deliver = MAIN.split("async def _deliver_web_push_for_notice", 1)[1].split("async def _publish_realtime_event", 1)[0]
        self.assertNotIn("has_visible_session", deliver)
        self.assertIn('client.visibilityState === "visible"', SW)
        self.assertIn('if (visibleClients.some', SW)

    def test_notification_click_navigates_existing_window_to_exact_target(self):
        self.assertIn("client.navigate(target.href)", SW)
        self.assertIn("target.origin !== self.location.origin", SW)

    def test_subscription_endpoint_is_not_an_arbitrary_outbound_url(self):
        validator = MAIN.split("def _valid_web_push_endpoint", 1)[1].split('@app.get("/push-sw.js")', 1)[0]
        self.assertIn("fcm.googleapis.com", validator)
        self.assertIn(".push.services.mozilla.com", validator)
        self.assertIn(".push.apple.com", validator)
        subscribe = MAIN.split("async def account_push_subscribe", 1)[1].split('@app.post("/account/push/unsubscribe")', 1)[0]
        self.assertIn("_valid_web_push_endpoint(endpoint)", subscribe)

    def test_disabled_browser_subscription_can_follow_account_switch_but_active_one_cannot(self):
        subscribe = MAIN.split('async def account_push_subscribe', 1)[1].split('@app.post("/account/push/unsubscribe")', 1)[0]
        self.assertIn("subscription.user_id != user.id", subscribe)
        self.assertIn("if subscription.disabled_at is None", subscribe)
        self.assertIn("status_code=409", subscribe)
        self.assertIn("subscription.user_id = user.id", subscribe)

    def test_logout_disables_only_this_browser_subscription(self):
        logout = MAIN.split('@app.get("/logout")', 1)[1].split('app.mount("/static"', 1)[0]
        self.assertIn('request.cookies.get("dai_push_subscription_id")', logout)
        self.assertIn("subscription.user_id == user.id", logout)
        self.assertIn('response.delete_cookie("dai_push_subscription_id")', logout)
        subscribe = MAIN.split('async def account_push_subscribe', 1)[1].split('@app.post("/account/push/unsubscribe")', 1)[0]
        self.assertIn('response.set_cookie("dai_push_subscription_id"', subscribe)
        self.assertIn("httponly=True", subscribe)
        self.assertIn("secure=True", subscribe)

    def test_service_worker_payload_is_privacy_minimized_and_internal_only(self):
        self.assertIn('const title = "Dental AI"', SW)
        self.assertIn("target_url", SW)
        self.assertNotIn("patient", SW.lower())
        self.assertNotIn("clinical", SW.lower())
        self.assertIn("clients.openWindow", SW)

    def test_incoming_messages_get_push_without_becoming_admin_notices(self):
        publish = MAIN.split("async def _publish_realtime_event", 1)[1].split("def _notify_user", 1)[0]
        self.assertIn('event.event_type == "MESSAGE_CREATED"', publish)
        self.assertIn("_deliver_web_push_for_message(event)", publish)
        sender = MAIN.split("def _send_web_push_message_sync", 1)[1].split("async def _deliver_web_push_for_message", 1)[0]
        self.assertIn('if bool(data.get("is_outgoing"))', sender)
        self.assertIn('"body": "Yeni bir mesajınız var."', sender)
        self.assertIn('f"/expert-support/cases/{case_id}"', sender)
        self.assertNotIn("_notify_user(", sender)
        self.assertIn("class WebPushMessageDelivery", MAIN)
        self.assertIn('"dentalai-message-" + messageEventId', SW)

    def test_case_created_does_not_add_a_second_push_path(self):
        publish = MAIN.split("async def _publish_realtime_event", 1)[1].split("def _notify_user", 1)[0]
        self.assertNotIn('event.event_type == "CASE_CREATED"', publish)

    def test_header_startup_does_not_duplicate_unread_or_notification_fetches(self):
        startup = BASE.split("async function catchUpEvents()", 1)[1].split("</script>", 1)[0]
        self.assertIn("await refreshUnreadCount();", startup)
        self.assertIn("catchUpEvents().finally(()=>{refreshNotificationCenter();connectSync();});", startup)
        self.assertNotIn("catchUpEvents().finally(()=>{refreshUnreadCount();", startup)
        tail = startup.split("function connectSync()", 1)[1]
        before_startup = tail.split("catchUpEvents().finally", 1)[0]
        self.assertNotIn("refreshNotificationCenter();\n    catchUpEvents()", before_startup)

    def test_messages_and_bell_contract_remains_separate(self):
        self.assertIn('evt.event_type==="MESSAGE_CREATED"', BASE)
        self.assertIn('evt.event_type==="CASE_CREATED"', BASE)
        self.assertIn('evt.event_type==="NOTICE_CREATED"', BASE)
        self.assertIn("bumpMessageBadge", BASE)
        notice_branch = BASE.split('evt.event_type==="NOTICE_CREATED"', 1)[1].split("else if", 1)[0]
        self.assertNotIn("bumpMessageBadge", notice_branch)

    def test_push_copy_never_uses_notice_message_or_clinical_detail(self):
        copy = MAIN.split("def _web_push_copy", 1)[1].split("def _web_push_status_code", 1)[0]
        self.assertNotIn("notice.message", copy)
        self.assertNotIn("clinical_summary", copy)
        self.assertNotIn("patient", copy.lower())


if __name__ == "__main__":
    unittest.main()
