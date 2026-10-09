# Chat replies and foreground read acknowledgements

Prepared after deployment a58ed18; not deployed.

- Image replies show Görsel rather than the timestamp; text replies use the original message body, excluding its own quote and receipt.
- Server-rendered, confirmed realtime and optimistic text replies share content previews. Existing reply IDs and media uploads are preserved. Reply selection still clears after sending; the quote stays in the sent bubble.
- Hidden/unfocused/suspended rooms do not send read acknowledgements. Foreground catch-up and focus restore acknowledgements, deduplicated by rendered message ID. No polling introduced.
- Room HTML requests no longer mark messages read; background refresh/prefetch is not a viewing action.
- Server bounds reads by client cursor within the authorized case and uses that message timestamp. Later arrivals remain unread. Legacy native clients without a cursor remain compatible.
- Cached-room suspension/resumption listeners now match events dispatched on document.

Validation: Chromium behavior test covers image/text quoting, escaping, confirmed replies, background/unfocused/suspended rooms, resume and duplicate acknowledgements. SQLite test executes the production models and helper, covering outsider denial, invalid cursors, later-arrival race, older cursor replay and foreign-case isolation. Python compilation and diff whitespace checks pass. Physical device and complete signed-in socket integration remain untested. No schema migration or notification-content change.
