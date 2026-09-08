# Project Status

## Preference harness revision — 2026-09-08

Sequential implementation and private runtime rollout complete. See [independent audit and acceptance criteria](preference-harness-audit.md) and [runtime contract](preference-learning.md). Existing translation status remains in `current-status.md`.

Completed: transactional shared reviews, conservative atomizer 2.1 with deficit semantics, immutable pre-feedback evidence, request-first ranking contracts, context-normalized pair/gate, bounded replay, exploration inside review capacity, private sync/preservation, coverage evaluation and regression tests.

Verification: 84 tests passed under runtime `/usr/bin/python3`; repository validator, JS syntax and diff whitespace checks passed. Temporary HTTP roundtrip proved cross-UI correction and retry. Live 9 reviews preserved and migrated, model deletion rebuild identical, 11 tentative atoms, 0 prospective contexts. Same launchd runtime restarted; APIs 200, private GET/HEAD 404, 12 core file hashes matched.

Remaining quality gate: independent user recall benchmark and new prospective contexts. Synthetic tests are not proof of daily search-quality improvement. Natural-language request/feature interpretation still relies on accountable worker judgments. Closed vocabulary abstains into visible unresolved clauses. Immutable archives require a future explicit retention policy.

The initial audit stopped before commit; the Claude review follow-up below supersedes that staging state. No push is implied by this document.

## Claude review verification — 2026-09-08 (supersedes initial counts above)

Verified the second review against executable counterexamples and implemented confirmed fixes.
Current suite: **95 tests passed**. Normal correction latency with 640 synthetic reviews/valid
traces: .447s; full recovery replay remains 75.983s and is an explicit maintenance path.
Checkpoint reuse preserves exact deletion-rebuild equivalence and the .5 score-step bound.
Explicit scoring cohort replaces source hashes as the gate boundary; immutable recipes replace
full model snapshots. Length, profile CAS, default dedupe, error propagation and bucket-order
contracts are enforced. Immutable runtime trees union safely; exact backed-up CAS resolution
is available for conflicts while coupled mutable state stays atomic as a group.

Live runtime migration preserved **10 reviews / 10 raw operations**, including one new review
arriving during work. 11 atoms tentative, prospective pair 0, model deletion rebuild identical.
Server restarted; APIs 200, private GET/HEAD 404 and ten core file hashes matched.
See [full review verification](pipeline-harness-review-verification.md). Actual search-quality
improvement and large-data full-replay latency remain explicitly unproven/limited.
