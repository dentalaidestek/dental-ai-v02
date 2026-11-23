# Native dashboard web-parity and privacy pass — 2026-11-21

## Web-first trace

Before changing the native home screen, the active web route and rendered flow were traced:

- `app/main.py` `home()` loads the three most recent owner-scoped patients, three guest analyses, one local-time dashboard program occurrence and the professional title.
- `app/templates/dashboard.html` renders the welcome area, patient search, feature cards, today's program, recent patients, recent analyses and the research/prototype notice.
- `app/templates/base.html` supplies the shared navigation, notification center and mobile navigation.
- `app/static/dashboard-v2.css` and the dashboard rules in `app/static/style.css` define the responsive visual treatment.
- `_program_dashboard_realtime_payload()` is the web dashboard's versioned, owner-scoped program snapshot. Program realtime events already carry this payload so the web page patches its program card without another dashboard request.

The native screen already had the same six primary feature destinations and a bounded three-patient display, but the review found four concrete gaps:

1. The welcome area used a fixed greeting and omitted the web professional-title prefix.
2. The “Son Analizler” section was only a generic link card; it did not display any recent analysis.
3. Every PROGRAM_* realtime event caused a full dashboard GET even though the event already carried the web's compact snapshot.
4. `GET /api/mobile/v1/dashboard` returned patient names and schedule data without the private/no-store response policy already used by the mobile patient and consultation APIs.

## Changes

- Added `mobile/src/dashboardPresentation.ts` for the web greeting/title contract and strict parsing of the version-1 program snapshot.
- Updated `mobile/App.tsx` so the web's core content order is preserved on native: welcome, search, primary features, program, recent patients and recent analyses. The mobile-only stats and quick links remain available below the web-equivalent content rather than interrupting it.
- Replaced the empty recent-analysis placeholder with up to three owner-scoped clinical-analysis rows. Each row opens the existing native `AnalysisResult` route.
- Valid PROGRAM_CREATED / UPDATED / COMPLETED / DELETED events now patch the program card locally. An unrecognized or malformed snapshot falls back to a normal refresh; patient and analysis events still refresh their relevant dashboard data.
- Updated `mobile_api.mobile_dashboard` to set `Cache-Control: private, no-store`, `Pragma: no-cache` and `Vary: Authorization`.
- The dashboard API now returns at most three recent analyses from one owner-scoped Analysis/Patient join. The response deliberately excludes clinical notes, file paths, phone numbers and TCKN; the full result remains behind the existing patient-scoped analysis endpoint.
- The same timezone- and recurrence-aware dashboard program snapshot used by the web route is returned on initial native dashboard load.
- Selecting the dashboard program row now passes its event ID to the native Program screen, opens the existing event editor (paging only if the event is outside the first result page), and consumes the one-shot route parameter. Auto-open waits for the existing pending-action recovery gate, so it cannot bypass an uncertain Program mutation.
- Added native presentation/API tests and a backend privacy, owner-isolation and bounded-query regression. Wired them into the normal mobile beta suite and Security Recovery.

## Validation boundary

Starting HEAD was `d07e7578bf7f9949ce63a153f1ff7b6e434be942`. Before this pass, its Android typecheck, session/auth, realtime/pagination, beta suite, Android/iOS Expo export and internal APK workflow had succeeded. Its Security Recovery native jobs and Python/PostgreSQL job had also completed successfully.

The new commits require fresh CI on the final HEAD. The new test results are not considered passed until those hosted jobs finish. No real patient record was created or modified, no database schema or migration was changed, and no production deployment or main merge was performed.

## Remaining parity boundary

The web home currently labels its last-analysis rows from the separate guest-analysis collection. The native app's existing result viewer is patient-linked, so this pass deliberately shows the latest patient-linked clinical analyses and routes them to the native result screen rather than introducing a browser/webview dependency or weakening the analysis ownership contract. Exact guest-analysis viewer parity remains a separate native feature.
