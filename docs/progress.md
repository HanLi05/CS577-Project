# Implementation ledger — 2026-10-28 data preparation

## Approved extension: small regression pilot

- User approved a statistics-only regression smoke test after the file-by-file walkthrough.
- Added `training.py`, `golf-data train`, and focused tests. Uses the existing chronological manifest: THE PLAYERS train (12), Charles Schwab validation (14), Memorial test (24).
- Fixed Ridge alpha=1 with SVD before observing results; no tuning or train+validation refit. Median imputation/scaling fitted only on train. Persistence baseline predicts current-round relative score.
- Results, row-level predictions, metrics, and provenance are saved under `reports/pilot_regression/`. No model serialization or language features added.
- Initial test MAE: baseline 3.543, Ridge 13.133. Poor performance is retained honestly; expanding and reviewing the data is preferable to adjusting the model against this test event.
- Verification: all 40 tests pass; two real-data training runs produced identical output hashes and left all prepared input files unchanged. Independent read-only review found no actionable issues in training, split validation, leakage protections, metrics, or CLI outputs.
- The original preparation milestone and its limitations below remain unchanged. The regression check is a separately authorized extension, not evidence that interview language is predictive.

## Original preparation milestone

User approved the plan and the after-round / before-next-round cutoff.

- Workspace: implementation stays in the requested folder. It is not a Git repository, so no worktree or commits are created.
- Source discovery: R is absent; golfastR publishes Parquet assets, so use those directly through Python. This preserves the proposed source and removes the R runtime requirement. Retain source hashes because release assets are mutable.
- Preflight interfaces: raw source cache → normalized tables → explicit matches → features/labels → text views and audit outputs. Target-only columns must not enter the explicit feature allowlist.
- Tasks 1–5: pilot implementation complete. Human semantic annotation and full historical expansion remain downstream work.

## Delivered

- Cached, paced collection with verified raw hashes, offline replay, source probes for 2015/2020/2025, and a 2024 pilot across three events.
- 88 transcript references; 87 parsed transcripts; 790 Q&A segments; 50 accepted examples containing 462 segments across 32 golfers.
- 14,215 complete player-rounds from 37 eligible 2024 events, reconciled against ESPN scoreboards, supporting historical features and full-field labels.
- Explicit reviewed player/event/round mappings, forward-looking rule outputs, two split manifests, numerical feature allowlist, data dictionary, and quality reports.
- Python environment and `uv.lock`; direct package CLI works without setting PYTHONPATH.

## Decisions and limits

- Ruling: use golfastR's published Parquet assets directly instead of an R export script. This avoids an unnecessary runtime; data-source fidelity is retained and hashes pin mutable releases.
- Ruling: exclude THE PLAYERS rounds 1–2 under the pilot's date-level cutoff because they continued the next morning. This sacrifices 20 candidate observations; future recovery requires completion-time versus individual tee-time comparisons.
- Ruling: use 2024 validated eligible scoring history, leaving missing histories explicit. Broader season orchestration is outside this pilot and results must not be presented as the full 2015–2025 study.
- Ruling: match inspection is AI-agent review, not human annotation. Human forward-looking labels remain blank; no extraction precision/recall is reported.
- Three-event splits demonstrate mechanics only. The pilot has 42 non-improvements and 8 improvements and substantial interview-selection bias.
- Exact transcript publication times remain unknown. The documented retrospective availability assumption cannot establish deployable real-time forecasting.

## Review and verification — 2026-10-29

- Independent read-only code review found no critical issues and two important quarantine-path gaps.
- Fixed missing earlier tournament rounds: matcher now logs `incomplete_tournament_history` instead of passing a bad example to a whole-build assertion. Regression test observed failing, then passing.
- Fixed absent reference event/round groups: coverage enumerates all observed/reference regulation groups and explicitly reports `missing_reference_group`. Regression tests cover missing events, missing rounds, and missing complete players; failing tests were observed before the fix.
- Reviewer scope exclusions (multi-season orchestration, embeddings/models, human semantic accuracy, precise publication times) remain explicitly documented downstream work or limitations; none are claimed complete.
- All 31 tests pass. An offline full-pipeline rebuild and a second rebuild produced identical hashes before the review fixes; final rerun verification is recorded below.
- No deferred code-review minors remain; the stale progress ledger was updated. No Git repository, commits, branches, or remote publishing were created.
- Final verification: `uv run --offline --locked golf-data run --config configs/data.yaml --offline` followed by a separate `build` succeeded; all input/output/config/code hashes were identical. The final dataset remains 50 examples, 14,215 historical player-rounds, and 148 fully reconciled event-round groups. PyArrow emitted sandbox CPU-cache discovery warnings; commands completed successfully and outputs matched.
