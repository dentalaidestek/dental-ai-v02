# Native tooth chart extracted-state visual parity — 2026-11-18

## Web-first reference

Reviewed `app/templates/tooth_chart.html` before changing native code. The web chart renders all permanent and primary teeth from the shared four-column enamel atlas. For an extracted tooth it applies:

```css
.tooth-btn.extracted .tooth-visual {
  filter: grayscale(1) brightness(.7);
}
```

The extracted-state X mark is inside the same visual element, so the atlas and its status overlay are both desaturated and dimmed. Implant rendering remains a separate asset path.

## Native gap found

`mobile/src/NativeToothVisual.tsx` used the same atlas and drew the extracted X, but reduced the atlas container to `opacity: .6`. That dims the original cream/brown colors instead of removing saturation. It therefore did not match the web's extracted-tooth appearance. The gap was also recorded in the parity tracker as an outstanding screenshot-fidelity item.

## Change

- Reuse the already installed `react-native-svg@15.12.1` filter primitives; no package or native-module dependency was added.
- Render the same bundled four-column atlas inside SVG with the existing 9% horizontal / 5% vertical inset.
- Apply one `FeColorMatrix` to the atlas and status overlay group only for `EXTRACTED`.
- Use Rec. 709 luminance coefficients scaled by 0.7, matching the web's full grayscale plus 70% brightness treatment. Alpha remains unchanged.
- Keep healthy, caries, filling, crown, root-canal and other colors unchanged. Keep the canonical implant SVG branch separate.
- Preserve lower-quadrant rotation, FDI atlas-column mapping and per-surface status-mark transforms.

No network image, AI request, patient record, database schema or production configuration is involved.

## Regression coverage

`mobile/tests/toothVisual.cjs` now checks:
- the extracted-only filter selector;
- the 20-value color matrix, equal RGB rows, 0.7 luminance scale and unchanged alpha;
- the web CSS reference string;
- native renderer filter attachment to the complete extracted visual group;
- the atlas clip region and X overlay;
- no grayscale filter for healthy/caries states;
- implant rendering remains on its existing SVG path.

The file is already included by `npm run test:beta`; no extra workflow command is needed.

## Validation and remaining acceptance

- GitHub source review confirmed the web CSS, bundled atlas, existing `react-native-svg` version and changed native component/test files.
- The repository could not be cloned in this runtime because `github.com` DNS resolution failed, so the Node component tests and full TypeScript typecheck were not executed here.
- The current PR head had no associated workflow runs or combined status. The latest available Android typecheck/APK and Security Recovery jobs from the prior code-bearing head failed with empty step arrays; job-log retrieval returned `BlobNotFound 404`. Those jobs did not reach npm, TypeScript, Gradle or pytest.
- Physical Android/iOS screenshot comparison, especially extracted primary teeth and small-screen scaling, remains an acceptance gate. The SVG filter is implemented using the existing cross-platform filter primitives, but this is not a device-test claim.

No main merge, production deploy, migration, APK/IPA publication or patient-record mutation.
