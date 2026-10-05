# Continuity investigation, 2026-10-05

This is a partial repair, not a claim of complete conversation understanding.
The original 50,000 rows and scorer were preserved for paired local comparison.
See `continuity-20261005.json` for exact counts and the frozen input SHA-256.

## Runtime causes repaired

- Retrieval lexical fallback was being used as discourse identity. Operations
  such as “10 soru hazırla”, acknowledgements, and reported historical requests
  could replace the active subject. Subject ownership now uses explicit spans
  or a user noun phrase governed by a request, shared by current/history turns.
- The ordinal parser accepted an ordinary cardinal count. “20 soru hazırla”
  could select question 20. Ordinals now require the dot or possessive reference.
- Later turns used fresh assistant prose as their antecedent. Replay now binds
  the selected list item at the user's selection turn; subsequent assistant
  prose and answer-option distractors cannot replace that referent.
- Latest explicit user topics supersede older selections. Qualifier replacements
  update the retained phrase as well as its qualifier tuple. Plain continuation
  resumes the active task; a new subject resets previous task slots.

The implementation remains bounded to eight input messages, with no provider,
DB, or network calls. It does not persist a conversation memory beyond that
window. It is not a general language reasoner; comparisons, ambiguous reference,
heavy misspellings, and semantic gold validation still require work.

`resolve_followup_query` is called by live retrieval before study-task routing.
This does not establish that the separate semantic decomposer/planner is fully
integrated into answer generation or that answers have been validated end to end.

## Why the 50K score is not a reliable completion gate

The audit preserves every row and reports necessary lexical conditions only.
4,758 rows require and forbid the same normalized term. Another check finds
16,866 rows where required terms do not appear in the supplied history/query;
the union is 20,457. Absence alone is not proof of semantic impossibility (for
example aliases and spelling variants need review), but the contradictory
require/forbid cases cannot pass the original substring scorer.

Examples from the frozen set:

- `b182802f752d`: “adeziv” is both required and forbidden.
- `e94d6b8d20f2`: expects perikoronitis, but the provided history contains only
  acknowledgements and a quoted Wilson question; perikoronitis is absent.
- `92bbcd94606d`: expects detailed length after the generator replaced the
  current request with “aynı konudan devam et”; no detailed request is visible.
- `7743793da1a5`: history requests acute alveolitis and query says continue;
  gold nevertheless forbids “akut”.

The generator mutates the query for later axes without consistently replacing
older expectations. History trimming also removes anchors. Thus “multi_hop”
metadata does not guarantee the final case actually expresses that operation.
The reported 98.838% signature uniqueness does not validate these contracts.

No benchmark thresholds, cases, gold labels, or scorer conditions were changed.
The current branch's 50K generator still correctly fails its existing
invisible-context validation before scoring. That check must not be disabled to
obtain a green badge. Paired local scores are reported separately from CI.

## Test contract corrections

The continuity module was absent from the main test runner; it is now included.
Two assertions in that previously unrun module contradicted the resolver's job:

1. Regenerating questions about the explicitly selected periodontal topic must
   retain that topic. The old test demanded its disappearance and therefore
   rewarded the ordinal/cardinal bug.
2. A text resolver must preserve “500 soru” as the user's requested count. It
   neither schedules nor authorizes 500 generations; execution budgets belong
   to generation orchestration. Removing the literal silently changes intent.
   The regression now checks that the number is preserved and not misread as a
   selected question.

The static invariant's exact old guard string rejected the expanded follow-up
syntax. It was replaced with behavior checks for independent questions, empty
history, empty input, valid continuation, and explicit topic switching.
Adversarial checks cover selected-item chains, unrelated assistant text, missing
ordinals, count overrides, qualifier replacement, and topic/slot resets.
