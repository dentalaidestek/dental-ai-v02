# Profile and document flow follow-up

## Findings and changes

- Membership submission previously redirected immediately into profile settings. Successful uploads now open the document status page, explicitly confirm receipt and explain that pending applications cannot be resubmitted. The uploaded document remains available to its owner and admins.
- Selecting a file is distinct from sending it. The upload step says to continue to review and explicitly send. AJAX submission keeps the selected file after an HTTP/network error and prevents duplicate sends. Realtime membership events no longer reload a form containing a selected file.
- The profile hero exposes a photo add/change button. Cancelling the crop dialog clears the file input so the same photo can be selected again. The existing private photo upload/crop endpoint is retained.
- Accounts without an eligible expert title now see the eligibility explanation and a link to professional settings. Hash navigation opens the collapsed section. Eligible titles remain specialist/academic titles; generic membership approval grants no expert authority. Expert applications still require their own manual document review.
- Expert management button text is explicitly white on navy.
- Chat bottom scrolling no longer uses scrollIntoView after scrolling to the bottom. That alignment previously discarded the padding needed for the fixed composer. The visible composer overlap determines bottom padding and is recalculated after viewport/composer size changes, including attachment/reply previews. Observers are disconnected on room cleanup and reattached after dynamic composer replacement.

## Validation

- 47 focused Python tests passed: profile hub, membership uploads, consultation lifecycle and private profile photo/realtime behavior. Includes actual PDF submission/download and denial of other-user document access.
- 7 Node tests passed, including four UI regressions for chooser reopening, selection preservation, duplicate/error/success submission handling and chat overlap.
- Syntax and whitespace checks passed. Security CI now includes the UI regressions.
- Actual Android gallery/PDF picker and visual layout are not verified in this environment. Chromium installation failed, so the JavaScript tests execute production functions with mocked DOM/viewport inputs rather than a rendering browser.
- No deployment as part of this follow-up. Production remains the already validated e97ba5b release until this branch is merged/deployed.
