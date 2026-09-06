# Daily ChatGPT/Steroids Job Contract

You are executing the daily Japanese web-novel research pipeline in repository:
`/Volumes/DevDrive/Projects/fieldnotes`.

Use Chat On Steroids Core for all repository reads/writes, state mutation, git operations and validation. Use current web search for discovery. Body acquisition is performed only by the repository's private local acquisition routes; never publish source or translated fulltext to GitHub Pages.

For this run:

1. Start a run log with `python3 scripts/automation_log.py --task daily_discovery --action run --status started ...` and keep the same run id for the daily discovery steps.
2. Read `config/automation.json`, `config/search-profiles.json`, `docs/search-protocol.md`, `data/automation-status.json`, and rebuild the persistent seen index with `python3 scripts/rebuild_work_index.py`.
3. Select the search groups for this run with `python3 scripts/select_search_profiles.py --commit`. If the page explicitly selected more than one group, run every selected group separately. If none is selected, obey `selection.when_none` (`round_robin`, `least_recently_run`, `random_daily`, or `all_enabled`) and `rotation_batch_size`.
4. If no enabled profile is available, update status/logs and stop without inventing criteria.
5. For each selected search profile, create one dated research entry. Same date can have multiple entries; assign next `YYYY-MM-DD-NN`.
6. Discover fresh candidates with current web/platform metadata. Apply that profile's constraints and default 300,000-char threshold. Keep sub-300k only as explicit high-fit length exceptions.
7. Before sampling/ranking, compare the harvested candidate list against `data/work-index.json` or batch it through `python3 scripts/work_index.py --unseen-only`. In strict mode, do not re-surface works already present in the index. Cross-posts are canonicalized by normalized title + author when available.
8. Read enough actual accessible sample text to assess the profile-specific fingerprint. Do not rank based on tags/synopsis alone.
9. Persist shortlist, rejected/deferred candidates, evidence, checked date, and paths. Rebuild `data/work-index.json` after each completed entry and update the archive.
10. Run `scripts/full_pipeline.py --entry ENTRY_ID --top-n N --episodes 5`. It registers targets, acquires the first five public reader episodes into the private local workspace, prepares merged source, creates the resumable chunk queue, seeds ruby/glossary evidence, and updates status. Reuse existing acquisition manifests unless a refresh is needed.
11. If automatic acquisition fails for a work, retain the manual `source_inbox/` fallback and record the blocker instead of discarding the candidate.
12. User-selected full translations have priority over normal sample translation. First run `python3 scripts/full_translation.py run-next` if a request is still `queued`; then use `python3 scripts/full_translation.py next-task`. Translate and complete these chunks with `full_translation.py complete` until the daily cap is reached or no full request is pending. A full request downloads all currently listed episodes, merges them, and produces downloadable TXT/MD/ZIP artifacts on completion.
13. If no user-selected full-translation chunk is pending, resume the standard queue with `python3 scripts/translation_queue.py next`, then `translation_queue.py complete`. Never omit source paragraphs.
14. Continue only up to the configured daily translation cap. If no cap is configured, translate one pending chunk per work to bound context/cost.
15. Run `scripts/refresh_automation_status.py`, `scripts/rebuild_work_index.py`, and `scripts/validate_repo.py`.
16. Finish the run log with done/partial/error status. Commit only public metadata/docs/code/state, never source or translated fulltext. Push main and verify GitHub Pages responds successfully.
17. Report: selected search groups, new entries, duplicates filtered, shortlist count, full-translation progress, translated chunks, blockers.
