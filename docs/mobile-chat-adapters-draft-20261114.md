# Native consultation adapters — unverified draft, 14 November 2026

Source work follows web handlers in app/main.py. It does not replace their
participant checks, case state machine, response deadlines or completion rules.

## Draft source added
- Native camera/gallery image selection, local preview and authenticated image upload.
- Server-side sanitization of JPG/PNG/WEBP through the existing validated image path.
- Authenticated image attachment route and native full-screen viewer with zoom controls.
- Read-receipt display using the peer's canonical read timestamp.
- Expert accept/reject and start-time proposals; requester proposal decisions.
- Complete/continue/dispute actions, block/unblock, report and review.
- User-local inbox deletion, a deleted-conversation list and restore.
- Case context in the mobile JSON response for controls, blocking and peer identity.
- Six backend and four client regression tests authored and wired into CI.

The native adapters dispatch the existing web handlers with an authenticated
internal request. No clinical mutation is replayed automatically. If image upload
cannot be confirmed, the UI requires the user to inspect recent messages before
clearing the selection. It does not claim a server failure means the file was not
saved.

## Verification limits and remaining work
The execution environment is unavailable. No TypeScript, Node, Python, Expo,
Android, iOS or two-account test was run on this draft. New tests are unexecuted;
prior passing totals belong to earlier commits. Keep PR #257 draft.

The complete web workflow is NOT yet ported. Remaining:
- Native generic PDF/audio file picker, protected local opening/downloading and playback.
- Photo editing/compositing and sending the edited bitmap as a new attachment,
  matching the current web editor. The older annotate endpoint is not equivalent.
- Shared case/patient media inventory and attachment selection parity.
- Persistent/reconnect-safe handling of uncertain sends and durable server
  idempotency (the existing web sender only echoes client_message_id).
- Complete deadlines/retention/review/routing acceptance and accessible device UI.
- Web/native and native/native two-account tests, native release build, security
  regressions and capacity testing.

No main merge, live deploy or store publication. These adapters need an approved
backend deployment before new native endpoints are available in production.
