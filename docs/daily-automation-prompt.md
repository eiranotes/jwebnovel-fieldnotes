# Daily ChatGPT/Steroids Job Contract

You are executing the daily Japanese web-novel research pipeline in repository:
`/Users/tofu/HermesWorkspace/project/jwebnovel-fieldnotes`.

Use Chat On Steroids Core for all repository reads/writes, state mutation, git operations and validation. Use current web search for discovery. Do not scrape/download Narou/Kakuyomu public novel bodies automatically.

For this run:

1. Read `config/automation.json`, `config/search-profiles.json`, `docs/search-protocol.md`, and `data/automation-status.json`.
2. If criteria are not ready, update public status only and stop without inventing criteria.
3. For each due search profile, create a dated research entry. Same date can have multiple entries; assign next `YYYY-MM-DD-NN`.
4. Discover fresh candidates with current web/platform metadata. Apply profile constraints and default 300,000-char threshold. Keep sub-300k only as explicit high-fit length exceptions.
5. Read enough actual accessible sample text to assess the profile-specific fingerprint. Do not rank based on tags/synopsis alone.
6. Persist shortlist, rejected/deferred candidates, evidence, checked date, and paths. Update GitHub Pages archive.
7. Run `scripts/full_pipeline.py --entry ENTRY_ID --top-n N --episodes 5`. It registers targets, acquires the first five public reader episodes into the private local workspace, prepares merged source, creates the resumable chunk queue, seeds ruby/glossary evidence, and updates status. Reuse existing acquisition manifests unless a refresh is needed.
8. If automatic acquisition fails for a work, retain the manual `source_inbox/` fallback and record the blocker instead of discarding the candidate.
9. Resume translation before starting newer work according to `translation.strategy`. Use `python3 scripts/translation_queue.py next` to select the oldest pending chunk. Translate the complete Japanese chunk to Korean, preserving names/terms with metadata/ruby/furigana/glossary evidence, save the result JSON, then call `translation_queue.py complete`. Never omit source paragraphs.
10. Continue only up to the configured daily translation cap. If no cap is configured, translate one pending chunk per work to bound context/cost.
11. Regenerate local parallel views for works with completed translations.
12. Run `scripts/refresh_automation_status.py` and `scripts/validate_repo.py`.
13. Commit only public metadata/docs/code/state, never source or translated fulltext. Push main and verify GitHub Pages responds successfully.
14. Report: new entries, shortlist count, source-waiting works, translated chunks, blockers.
