# Dental AI code audit — PR #215

## Scope and tools

Baseline: `83fc5cc64b3173aa08fa191df66887cd4fdc5dd3` on
`work/voice-review-mobile-20261024`. The source tree contains 715 files.
GitHub supplied 155 nonempty Python source files; three empty package init
files contain no executable code. Bandit 1.9.4 parsed 46,169 lines with no
parser errors. Nine first-party `app/static` JavaScript files were checked for
syntax and dangerous DOM/storage patterns. Inline template scripts and the
native Android application were not comprehensively audited.

Connected GitHub and Superpowers supported source inspection and independent
review. Plugin discovery did not expose a dedicated security scanner usable
for this session. Bandit ran locally in a task-only environment; it was not
installed as a production dependency and no private source was sent to a new
external scanning service. Figma and PostHog are not source-security scanners.
No additional cloud service, paid plan or deployment was created.

## Confirmed findings and repairs

### Native consultation message adapter fails before sending — functional, P2

`mobile_send_consultation_message` called `expert_support_message` without
awaiting it. The latter is decorated with the real `execution.offload`, which
exposes an async callable. Consequently the adapter returned a coroutine that
FastAPI could not serialize, and the underlying send handler never executed.

Three exact-adapter HTTP tests reproduced status 500 before the repair. The
adapter is now async and awaits the existing handler. Tests exercise the real
offload wrapper with a synthetic persistence boundary: success remains 200;
403 and 409 remain handler refusals; the handler executes exactly once with
unchanged token, case, content, reply and idempotency arguments. No separate
message persistence, permission bypass or retry path was added.

### Private responses and clinical attachment cache policy — privacy hardening

The shared security middleware forced no-store only for cookie-authenticated
HTML. Some protected downloads/API replies lacked an explicit cache policy;
two consultation attachment handlers explicitly permitted private caching for
one year with `immutable`. This is a local browser retention concern, not
proof of public disclosure or a successful unauthorized download.

The middleware now recognizes cookie or Bearer requests without additional
DB/auth queries. It forces `private, no-store` on HTML and authenticated
clinical paths under uploads, patients, analysis, expert-support cases and
course notes, including existing long-lived clinical attachment policies.
Other nonstatic authenticated responses receive no-store only when they lack
an explicit policy. Shared static assets and explicit nonclinical runtime
configuration caching retain their existing behavior.

Thirteen middleware HTTP tests cover cookie/Bearer image, PDF, JSON and HTML,
long-lived clinical attachment policies, static caching, anonymous replies and
explicit runtime config caching. Seven baseline cases failed before repair;
the two long-lived attachment cases also failed before the clinical override.
All pass after the repair. This affects future responses; it does not erase
objects that browsers already cached under an older release.

## Automated alerts are not confirmed vulnerabilities

Bandit produced 71 raw alerts: one high, 25 medium and 45 low. The machine-readable
inventory is `code_audit_pr215.json`; these severity labels belong to the tool,
not to a verified exploit assessment.

- The high alert is default Jinja autoescaping in the local design-preview
  builder with synthetic input. It does not establish production XSS.
- Fourteen SQL-construction alerts use fixed internal fragments or generated
  bind placeholders in the examined paths. User values remain parameterized;
  no SQL injection was confirmed in those matches.
- Literature XML/URL paths use fixed hosts, bounded reads, no redirects and
  entity checks. No SSRF/XXE exploit was demonstrated in the reviewed matches.
- Apparent hardcoded-password alerts include empty defaults, schema strings,
  the Bearer scheme name and image-processing labels. No exposed API key or
  usable password was established from those alerts.
- Unpinned model downloads, predictable model-cache directories and external
  artifact read limits remain supply-chain/resource hardening items for a
  separate deployment/model review; they are not claimed as exploited bugs.
- Broad exception handling and assertion warnings require call-site context;
  this review does not declare every low alert harmless or every code path safe.

A cross-module AST check of imports from `app.main` also identified the native
message adapter's synchronous call to an async/offloaded handler. This logic
error was found through source review rather than Bandit.

## Validation and limits

- Full locally available suite from the `implementation` project root:
  **249 Python tests passed**, with 40 existing dependency deprecation warnings.
- All **10 Node test files passed**; all nine inspected JavaScript files parsed.
- Independent review ran the 16 new regression cases and found no remaining
  critical or important issues in the changed production logic.
- An initial test invocation from the scratch parent directory failed collection
  with missing `app` imports. The project-root invocation above is the valid run;
  those collection errors were not application failures.
- Source reading and static checks are not a penetration test, dependency-CVE
  assessment, full production startup, real mobile send/device test, or proof of
  60,000-user capacity. No real patient content was used, and no message was sent
  to another person during testing.
- Main and production remain unchanged. The fixes are prepared on PR #215.
