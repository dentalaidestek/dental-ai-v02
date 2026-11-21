# FDI tooth-surface parity — 20 November 2026

## Web-first inspection

Reviewed \`app/templates/tooth_chart.html\`, including its FDI tooth arrays, surface grid, preview pins, hidden surface selector, CSS marker placement and \`selectTooth\` / \`setSurface\` handlers. Then compared \`mobile/src/NativeToothChart.tsx\`, \`mobile/src/toothSurfaceOptions.ts\` and the native tooth visual.

## Finding

The native chart already used the correct tooth-specific contract:
- Permanent and primary anterior teeth (FDI units 1–3) expose \`INCISAL\`.
- Permanent premolars/molars and primary molars (units 4–8, within the valid FDI ranges) expose \`OCCLUSAL\`.
- Both groups retain MESIAL, DISTAL, BUCCAL and LINGUAL.

The web chart instead rendered one static surface grid for every tooth. It always exposed OCCLUSAL and never exposed INCISAL. Its top preview pin also stayed labelled \`O\` for anterior teeth. This was a clinical input mismatch, not merely a visual difference.

## Change

- Added \`static/tooth-chart/surface-options.js\` as the browser/CommonJS FDI surface contract.
- Web chart now creates only the five anatomically applicable buttons for the selected tooth, using DOM node creation and \`textContent\` rather than interpolated HTML.
- The top preview pin changes from O to İ and carries the matching surface code/accessible label for anterior teeth.
- INCISAL preview marker alignment now matches OCCLUSAL and the native preview.
- Existing hidden selector values, revision lookup, save handlers and backend routes remain unchanged.
- No patient data, clinical record, API, database schema, provider call or migration was added.

## Regression coverage

Added \`mobile/tests/webToothSurfaceParity.cjs\` and registered it in \`npm run test:beta\`. It compares web and native contracts for permanent/primary anterior and posterior teeth, rejects invalid FDI values, and checks that the web template loads the helper before initialization and uses safe dynamic controls.

## Validation limits

The new Node regression file is committed but was not executed in this environment. The latest branch head before this work (\`e7f0962\`) had zero associated workflow runs and zero commit status checks. GitHub Actions therefore provides no current test result. The previous Android \`TS2554\` source cause was separately rechecked: the obsolete \`ModernScreens.MediaGallery\` export and its old \`uploadPatientMedia\` call are absent; \`App.tsx\` routes \`MediaGallery\` to the canonical owner-scoped \`NativePatientMedia\` screen. This source inspection is not a full Android typecheck. Earlier Security Recovery jobs failed before step 1 (\`runner_id=0\`, empty steps and unavailable logs); they do not establish a Python regression failure.

Full Expo typecheck, \`npm run test:beta\`, Android Gradle/device tests, Python security tests and real 60,000-user load tests remain open.

No main merge, production deploy, migration, APK/IPA publication or patient-record mutation was performed.
