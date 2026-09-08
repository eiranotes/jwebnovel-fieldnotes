# Preference Learning v2 — audited evidence contracts

Updated: 2026-09-08. Supersedes the v0.3 description. The independent audit found a FAIL;
these changes repair the harness. They do not establish an improvement in real discovery quality.

## Review source of truth

`workspace/preference-feedback.json` schema 2 has an ordered `operations` journal. A review ID
is the hash of `(research context, canonical work, preference scope)`, independent of UI.
Corrections append a revision; `events` is the latest-revision projection, never an extra vote.
Daily Taste and Console edit the same identity. Same-content retries append no operation and
advance no model/history revision. Different research contexts remain separate reviews.
Direct preference learning uses only the latest review of each canonical work in a model, so
rediscovery cannot manufacture independent evidence. Global reviews are inherited by scoped
models, but automatic pairs require matching scopes and context. Implicit full-translation
actions are retained separately and excluded from rating metrics and taste learning.

Raw commit, model rebuild and Daily projection use a shared process lock and unique, fsynced
atomic JSON writes. The raw journal commits first; a retry/rebuild recovers interrupted derived
writes. Daily state is a projection, not a second authority. Existing raw revisions and original
memo text survive migration. Deleted derived model files can be reconstructed from the journal,
immutable ranking traces and the versioned configuration/code recipe. Raw reviews alone cannot
recreate sampled candidate features or prospective results.

## Atom semantics and uncertainty

The v2 atomizer works within clauses, separates coordinated subjects, handles the audited
negative scopes, and prevents narrow honorific complaints from voting against all prose.
Conflicting clauses and double negation abstain. Unmapped expressions are preserved as
`unresolved_clauses` and shown in the console. They are not silently treated as learned features.
This remains a conservative rule-based parser, not a general Korean semantic model. New wording
may need a rule and regression example. Every rebuild derives atoms from raw memo text; cached
atoms never override the current extractor. No 16-atom truncation is used.

Quality deficits use separate presence features: dislike of `protagonist:implausible` never
creates a negative weight for `protagonist:plausibility`. Atomizer 2.2 re-extracts old raw notes.
A candidate value describes the named trait, never the user's reward.

## Continuous learning and score bounds

A direct review has at most 1.0 total support, divided over its extracted atoms. Support decays
with a 90-day half-life relative to the most recent review operation; it does not silently change
when an unchanged state is read. `as_of` is recorded for replay. The latest review per work is
used; distinct contexts are required for maturity and stage promotion.

For atom j, signed support is D_j, its support is S_j, and total effective review support is E:

- diagnostic posterior: `D_j / (4 + S_j)`;
- confidence: `S_j / (4 + S_j) * abs(D_j)/S_j`;
- direct ranking weight: `D_j / (4 + E)` (shared denominator preserves memo-splitting budget);
- tentative: fewer than 2 independent works/contexts;
- reinforced: at least 2 works and 2 contexts;
- stable: at least 5 works and 5 contexts, support >= 3, consistency >= .8;
- mixed: both signs with consistency < .8.

Pair learning compares only jointly measured dimensions in valid pre-feedback traces. Unknown
measurements are not zero. Duplicate pairs are collapsed; pair gradients are normalized within
context and averaged across contexts. L2 is applied once per batch epoch, not once per pair.
Pair influence is bounded to a 0.3 normalized contribution. Confidence uses contexts / 6.

Let n be effective independent evidence contexts, m = `1-exp(-n/12)`, and g the quality gate.
The target score vector has L1 norm <= `4*m*g`. Initially g=.5, so targets are bounded by +/-2
points; validated targets may reach +/-4. A verified checkpoint processes only appended raw revisions; deleting or invalidating it
replays the journal deterministically. The applied
score vector moves at most **0.5 in L1 per review revision**, including changes in gate, pair
learning, maturity, correction and decay. Actual rank score is base + dot(applied weights,
feature value * confidence), clipped to 0–100. Thus a fixed candidate/request cannot move more
than 0.5 points from one review operation. A code/config rollout is a separate model revision;
this per-review bound is not a claim about arbitrary implementation changes.

A gate reduction changes the target immediately; an already higher applied vector approaches
it under the same 0.5-step protection. No absolute rank-position limit is claimed: arbitrarily
close base scores can change many positions from a small score change.

Independent consistent single-atom simulation (no prospective evidence):

| Reviews / contexts | Applied score shift |
|---:|---:|
| 1 | 0.032 |
| 3 | 0.190 |
| 5 | 0.379 |
| 10 | 0.808 |
| 20 | 1.352 |
| 50 | 1.823 |
| 100 | 1.923 |

Reason/tag suggestions share their own bounded explicit-evidence budget and require at least
5 independent contexts. They require user approval to update profile soft preferences. They
never mutate MUST/MUST NOT. Approved records are suppressed from repeated suggestions and are
not automatically injected into request-only discovery. Console shows actual applied score budget, not a fictitious 72/28
absolute blend.

## Prospective online policy evaluation

Ranking traces contain an immutable model revision/recipe reference, request, candidate pool, exact
sample hashes, features, base/rerank scores, selected order and every candidate's inclusion
probability. A context trace is create-only; identical retries return the existing hash. A
changed trace or trace created after feedback is rejected. Content-addressed sample copies are
retained privately. Only selected works, matching scope, valid content hash, and review creation
timestamps after the trace can enter prospective learning/evaluation. The explicit `SCORING_COHORT_ID` must match for gate and pair training. Full code hashes remain
provenance, not cohort boundaries: a comment or unrelated evaluator change does not erase evidence.
Incompatible score/feature meaning changes require a deliberate cohort bump. Other cohorts remain
visible in `cohort_pair_counts`; no trace is deleted or retroactively relabeled.

Base and rerank use the same unequal-user-rating pair population; score ties receive 0.5.
Metrics are averaged per context, then across contexts in actual trace creation-time order. Individual model revisions remain
visible. This evaluates an online policy through frozen predictions; it is not a claim that a
single unchanged model was A/B tested. NDCG based on original editorial ranks remains a separate
historical diagnostic.

- <20 contexts or <60 pairs: calibrating, g=.5.
- >=10 contexts and delta <= -.05: guarded g=.25; delta <= -.10: degraded g=.125.
- Improvement needs >=20 contexts/60 pairs, delta >= .05, a positive lower 90% context-bootstrap
  bound, and confirmation after at least 5 additional contexts.
- First confirmed promotion at 25 contexts: g=.55; +.05 per additional context, maximum 1.
- Otherwise stable/calibrating stays at .5. No promotion from a single 40-pair entry.

## Discovery/entry contract

1. Create a draft with `new_entry.py --profile PROFILE --date DATE --title TITLE`.
2. Prepare a request JSON containing `context_id`, `profile_id`, `intent`, `hard_filters`,
   `reference_works`, `soft_preferences`, `explicit_dimensions`, `analysis_confirmed:true`, and
   `review_budget` (normally 5). Explicit dimensions must cover the request and fingerprint;
   `pacing` protects the whole pacing family. This analysis is a worker judgment and must be
   evidenced, not inferred from accumulated taste.
3. Draft/request profile identity must match. Freeze it before discovery: `new_entry.py --freeze-request ENTRY --request REQUEST.json`.
4. Rebuild `data/work-index.json`, then harvest, deduplicate, and acquire accessible body samples for the candidate pool privately.
   Generate request-neutral core features as well as learned dimensions; do not restrict feature
   extraction to the current preference vocabulary. Keep unsupported dimensions unmeasured.
   The ranker also checks the index before inspecting samples. `strict_seen_index` excludes every
   seen work; `cooldown` allows a repeat after configured days (default 30). An explicitly frozen
   `revisit:{enabled:true,reason:...}` with a sourced `revisit:pass` receipt allows an intentional revisit.
5. Each candidate needs `base_score` explicitly in 0–100, `eligible:true`, platform/genre/length
   metadata as applicable, and `eligibility_receipt` with request hash, canonical candidate key,
   and source-backed checks. Missing min_chars uses the 300,000-character global floor. List conditions use IDs like `must:0`, `must_not:0`, `platforms:0`;
   scalar conditions use the field name (`min_chars`). Each check contains `status:pass`,
   `evidence`, `source_url`. The default length-exception lane requires a truthful failed
   `min_chars` receipt, `length_exception_fit:pass` with evidence/source, and explicit authorization
   `length_exception:{enabled:true,explicit_minimum:false}`. Other failed checks are excluded. Semantic checks remain accountable worker judgments.
6. Samples: `samples[{sample_id,path,sha256,source_url}]`, paths under private `workspace/`.
   Features: `preference_features[{atom,value,confidence,sample_id,start,end,evidence}]`.
   Values are -1..1, confidence 0..1, no duplicate atoms. Evidence is an EXACT source-text span,
   not the worker's explanation. Hash/offset/quotation mismatches reject ranking.
7. Run `preference_rank.py --profile PROFILE --context ENTRY --request REQUEST.json --input
   CANDIDATES.json --count N --seed DATE:PROFILE:ENTRY`. The command rebuilds/locks model state
   and saves the immutable trace. Request-explicit dimensions contribute zero learned shift.
8. Run `new_entry.py --finalize ENTRY`. Only safe selected metadata enters the public entry; length exceptions retain their own bucket.
   `selected_candidates(entry)` merges both buckets in frozen preference_rank order for acquisition.
   Validators and target registration reject a missing trace or reordered/different slate.
   Archive HTML/Markdown/index must be generated from that finalized entry, not alternate picks.

All new scaffolds require the trace contract. Existing pre-v2 entries remain legacy, explicitly
without prospective proof; historical scores are never fabricated. A new context is required
when a frozen request or candidate slate needs changing.

Exploration reserves approximately one slot per five reviewable works, restricted to candidates
at least 60 base points and within 5 points of the current cutoff. The minimum score is an initial
policy value, not a calibrated universal relevance threshold. Selection is uniform without
replacement on the qualified frontier, giving exact marginal inclusion probability k/N.
Slots are placed inside the actual acquisition/review budget even with a longer displayed slate.
No qualifying explore candidate means abstention, not a garbage slot. Novelty and measurement
uncertainty are recorded separately; selection diversity and actual explore-review coverage can
be inspected with `preference_evaluate.py`.

## Privacy, history and evaluation limits

Feedback, model, Daily projection, traces, history, sample evidence and revision recipes are
private, ignored and included in runtime reconciliation. Mutable sync locks both roots and
reports two-sided conflict rather than choosing a winner. Immutable archive trees merge disjoint
files by union; same-path/different-content files are conflicts. Coupled mutable state remains
all-or-nothing. `runtime_sync.py resolve --path PATH --prefer canonical|runtime --expected-canonical
HASH --expected-runtime HASH` requires both inspected hashes and backs up both old versions before
resolving exactly one path. Stale hashes fail. Unchanged immutable files are not recopied. Revision recipes preserve raw review
operation references, profile config, code source and trace hashes. Sources/config/operations are
content-addressed once under `preference-revisions/`; recipes retain the scoring weights. Trace
files reference recipes instead of multiplying full models across contexts. Replay loads and
validates the trace set once per transaction, and a digest-verified checkpoint resumes only when
its operation prefix, config, source revision and relevant trace dependencies match.
History's summary view retains 200 distinct content revisions; immutable evidence is not
silently pruned. No-op retries create no revision.

`preference_evaluate.py` reports selected/reviewed/explored coverage and zero-propensity candidates.
`--benchmark FILE` accepts independent user relevance labels per intent and reports recall@20;
it rejects model-generated/unspecified label sources. No real discovery benchmark is fabricated.
Observed user ratings still do not give unbiased quality over unexposed/unread candidates.
Future prospective contexts and independent recall judgments remain necessary for a quality PASS.

## Profile writer discipline

Console profile/selection updates, daily selection consumption and preference approvals share the
workspace lock and atomic unique-temp JSON save. Console writes include the last read config
revision; stale edits are rejected with a reload instruction. Request-only profile selection does
not rebuild/write the preference model. Operational learning read errors and local-stage validator
failures surface as failures rather than silently returning empty data or success.
