# Step 1 integration checkpoint — 2026-09-13

Request: add existing Step 1 model, download weights; preserve accepted 13 + FDI.

Verified public project: https://universe.roboflow.com/prime-snf1v/step-1-o18pv
Advertised API model: step-1-o18pv/6 (Roboflow 2.0 Object Detection Fast).
The project lists 59 classes, 6 models. Project-level labels do not establish
version-6 checkpoint metadata or class-level accuracy. Published metrics are
not our independent benchmark.

Implemented: named prediction adapter, bbox conversion, malformed-output
rejection, explicit threshold, helper separation, candidate-only status, tests.
Not activated in the clinical pipeline. No baseline engine modified.

Blocked: no downloaded weight, no checksum, no checkpoint class metadata,
no real inference, no deployment. Roboflow API key absent in local environment;
public project UI remains on Cloudflare human verification in cloud browser.
Do not convert this into a claim that weights cannot ever be obtained.

Resume here: resolve authorized Roboflow access; verify version-6 download or
local Roboflow Inference entitlement and actual runtime labels; download/cache
and hash assets; run independent annotated panoramas; only then activate.
Do not start training or restart the previous V7 experiment to solve access.

Existing V7 archive contains exported best.pt; that work must be preserved.
This adapter does not establish any additional canonical PASS.
