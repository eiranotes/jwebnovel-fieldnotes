# Changelog

## 2026-09-08 — Preference harness audit remediation

- Daily Taste and Console now edit one review per work/context/scope; retries do not multiply learning.
- Memo extraction handles tested negative/mixed clauses, separates disliked quality deficits, and exposes unresolved language.
- Independent-context evidence and bounded score updates limit overreaction and pair amplification.
- New discoveries require frozen current requests, sampled feature evidence and immutable ranking traces before finalization.
- Exploration reaches the actual review budget; quality evaluation distinguishes observed ranking from discovery recall.
- Private evidence, history and revision archives survive runtime sync. Existing nine reviews migrated without changing their text or ratings.
- Validated with 84 tests, temporary HTTP correction/retry, live runtime health and model rebuild. Actual prospective improvement remains unverified.

## 2026-09-08 — Claude review follow-up

- Verified and fixed review latency amplification with an integrity-checked incremental checkpoint; full replay remains available for recovery.
- Cohort continuity now follows explicit scoring semantics, not incidental code/comment hashes.
- Enforced the implicit 300k floor, truthful length exceptions, profile identity and seen-work policy.
- Preserved length-exception buckets and frozen acquisition order; recognized common Korean inflections.
- Profile revision checks prevent stale-page overwrites; immutable sync unions disjoint files and supports backed-up CAS conflict resolution.
- Updated executable format examples and removed silent validator/lesson failures.
- 95 tests passed; live runtime includes all ten current reviews. Actual prospective improvement remains unverified.
