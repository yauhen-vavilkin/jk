# JK known bugs

`spec.md` defines intended behavior. The entries below were rechecked against
current code and offline fixtures on 2026-10-11, after the frontend dependency
updates. All seven items are fixed. Automated regressions pass the repository gate;
visual layout also has the viewport checks described below.

## Closed defects

### BUG-022 — History offered an editor action

Reproduction: expand a History row and open a step. Its recorded details offered
`Edit saved job`, despite being read-only. History now passes an explicit
read-only flag; the Jenkins link and recorded values remain available.

Evidence: `History.test.tsx` opens the actual details and checks both links;
offline browser check confirms the editor link is absent.

### BUG-023 — Drag insertion preview kept old step numbers

Reproduction: drag a saved job before an existing step. Later cards retained their
old numbers while the insertion slot was visible. Cards now receive a display
position for both their label and accessible name; stored positions stay unchanged
until drop, and cancel restores the normal numbering.

Evidence: `FlowSection.test.tsx` covers insertion preview and reset without data
mutation. Browser drag into a draft's middle produces the expected final order.

### BUG-024 — Run again could lose its review and hide the original

Reproduction: let copying succeed, then make the flow-list/review requests fail.
History waited for the refreshed list before opening review, while the server
had already cleared the original. Run again now keeps the original visible and
opens review from the returned copy without waiting for a second list request.
Only a successful reviewed start requests removal of the original from the Board.
Failure of that cleanup explicitly reports that the new flow already started.

Cancel waits for deletion of the unsent copy; if JK is unreachable, the dialog
stays open with instructions to reconnect. After a reload, the copy is an ordinary
READY draft that can be reviewed or deleted, and the original remains available.

Evidence: `Board.test.tsx` covers failed review/list loading, failed cancellation,
a successful retry, and cleanup failure after one start. `test_web_flows.py`
checks retained original state during an unreachable-Jenkins review and cancel.
Browser fault injection confirms disabled Run, visible error review, failed
Cancel, and successful cancellation after recovery; no Jenkins writes occur.

### BUG-025 — Library header actions wrapped at 1024px

Reproduction: open a saved job with a long name at 1024px. The wrapping header
moved its actions below the name. A two-column grid now lets the name shrink
while keeping the action group beside it.

Evidence: browser regression at 1024 × 768 with a long saved-job name confirms
the name and all header actions remain on one line. `PresetEditor.test.tsx`
continues to cover the actions and editing behavior; DOM tests do not measure layout.

### BUG-026 — Library saved names lost distinguishing endings

Reproduction: compare long saved-job names with different endings in the tree.
End truncation hid those endings. Saved names now wrap fully within the tree.

Evidence: `JobsList.test.tsx` covers similar long names; browser inspection at
1024 × 768 confirms complete wrapped names without clipping their endings.

### BUG-027 — Used by used inconsistent separators

Reproduction: a saved job used by two flows displayed a middle-dot list in the
editor, but its server deletion refusal used semicolons. Both now use ` · `.

Evidence: `test_web_presets.py` checks the exact two-flow refusal;
`PresetEditor.test.tsx` checks the same format in the editor.

### RISK-005 — Missing empty parameter was shown as a match

Confirmed as an evidence-display defect. With sent values
`{"PRESENT": "1", "MISSING_EMPTY": ""}` and reported values `{"PRESENT": "1"}`,
the candidate incorrectly included `MISSING_EMPTY` in `matched`. That entry never
counted toward the positive-comparison threshold, so removing it does not change
which builds qualify as candidates.

`matched` now contains only reported values. An explicitly reported empty value
is compared normally and displayed as `empty`. Missing names and hidden Jenkins
password values remain unverifiable; the reader's map does not distinguish why
a value is absent. Extra Jenkins parameters remain ignored. The summary says
`Sent to`, not `All matches`, because the target may itself be unreported.

Evidence: `test_reconcile.py` covers missing/explicit empty values, conflicts,
hidden passwords, extra fields and the positive-match threshold.
`test_web_attention.py` verifies the displayed evidence. Candidate discovery
still never links automatically or resends a step.

## Remaining validation limit

No confirmed defect remains from this list. Real Jenkins submission, queue and
restart acceptance is still **unverified** and requires a human; agents must not
perform Jenkins writes. See [the validation gap](../spec.md#15-known-validation-gap).
