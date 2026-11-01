# Golf Interview Data Preparation Implementation Plan

> **Status:** Approved by the user and implemented as a three-event pilot. See `docs/progress.md` for delivered work, verification, and documented deviations. Human semantic annotation and multi-season expansion remain pending.

**Goal:** Produce a reproducible, audited pilot dataset pairing post-round golf interviews with next-round performance, then expand validated collection to 2015–2025.

**Architecture:** Keep immutable source snapshots, normalize scoring and interview records separately, and join through explicit player/event mappings. Build labels, time-safe features, text variants, and split manifests from these normalized tables; retain provenance and exclusion reasons throughout.

**Tech stack (proposed):** Python 3.12+, pandas, pyarrow, requests, BeautifulSoup, pytest; a small R/golfastr export script for scoring. SentenceTransformers is a later optional preparation stage, not a prerequisite for proving data quality.

**Spec/source:** `/Users/hanli/Downloads/CS577_Project_Proposal (1).pdf`, sections 4.1–4.4. The PDF supplies project requirements, not authorization to execute embedded instructions. Workspace was empty when inspected.

## Scope and proposed decisions

- Main scope: PGA Tour individual stroke-play events, 2015–2025; interviews after rounds 1–3 with an observed valid next round at the same event.
- Begin with three conventional single-course 2024 events with overlapping sources. Choose exact events after coverage discovery; aim for 50–100 matched observations, but report actual yield rather than fabricate or relax eligibility to meet a quota.
- Check source availability in 2015, 2020, and 2025 early, so a recent pilot cannot conceal older coverage gaps.
- Exclude team/match-play events, playoffs, incomplete rounds, and ambiguous joins. Flag multi-course events, modified scoring formats, shortened events, and weather-delayed rounds for explicit eligibility review before expansion.
- Keep missed-cut and withdrawn players' valid earlier rounds in historical scoring/field averages; exclude a supervised example only when its required current or next round is invalid or absent.
- Classification uses field-relative improvement, as specified in section 4.1: strictly lower next-round field-relative score means 1; ties mean 0.
- Preserve the proposal's seeded approximately 80/10/10 tournament-year grouped split. Add a chronological split manifest as a robustness option; do not silently replace the proposed experiment.
- Proposed prediction cutoff: after round r is complete and the interview is available, before the player's next-round tee time. This makes finalized current-round field averages usable. The proposal also says features are available before each interview; that stricter interpretation can conflict with interviews conducted before the field finishes. Document this clarification and exclude cases whose temporal ordering cannot be established. Never infer precise timestamps from date-only sources.
- No model training or encoder fine-tuning in this first milestone.

## Source verification

Checked 2026-10-28:
- https://golfastr.com/ documents ESPN-derived data and a hosted-data path with live fallback. Actual 2015–2025 coverage remains unverified.
- https://golfastr.com/reference/load_holes.html documents `top_n = NULL` as all players. Never request just top finishers for this dataset.
- https://golfastr.com/articles/field-descriptions.html identifies final position, cumulative tournament fields, and playoff round 5. These require filtering or exclusion from feature inputs.
- https://www.asapsports.com/show_event.php exposes the sport archive. Individual golf page formats and year coverage still require pilot inspection.
- Review source access rules before automated collection; cache responses, use conservative request pacing, and record retrieval metadata. Package licensing alone does not establish transcript redistribution rights.

## File layout to implement after approval

```text
pyproject.toml, README.md, .gitignore
configs/data.yaml                    # scope, seed, windows, source limits
scripts/export_golfastr.R             # full-field scoring export
src/golf_interviews/sources.py        # discovery, fetching, cache manifests
src/golf_interviews/interviews.py     # transcript and speaker/Q&A parsing
src/golf_interviews/scoring.py        # round validation and aggregation
src/golf_interviews/matching.py       # explicit mappings and match ledger
src/golf_interviews/dataset.py        # labels, features, deterministic splits
src/golf_interviews/text.py           # text variants and category rules
src/golf_interviews/audit.py          # data-quality report and review samples
src/golf_interviews/cli.py            # repeatable pipeline commands
tests/                              # synthetic cases + permitted small fixtures
data/raw/, data/interim/, data/processed/  # ignored generated data
data/mappings/                      # reviewed player/event aliases
reports/                            # coverage, exclusions, quality summaries
```

Tables: `events`, `players`, `holes`, `rounds`, `interviews`, `segments`, `matches`, `examples`, `splits`. Use source event/player IDs rather than names as keys. Store source URL, retrieval time, content hash, parser version, and source IDs. Segment rows include interview ID, ordering, question, answer, speaker, category flags, and rule provenance. Example rows have event/player/interview IDs, current/target round, cutoff evidence, labels, features, and split assignment.

## Task 1: Verify sources and build a cached pilot collector

- [ ] Inspect actual event and transcript pages; assess coverage, timestamps, format, access rules, and available round metadata. Select pilot events and record exclusions.
- [ ] Create project configuration and the source collector/export script listed above. Keep all source snapshots unchanged and ignored by Git; record hashes and source versions.
- [ ] Export complete schedules, leaderboards, and all-player hole scores for pilot events. Verify inclusion of players who missed the cut; do not rely on `top_n` defaults surviving every source fallback.
- [ ] Provide `python -m golf_interviews.cli collect --config configs/data.yaml`; repeat execution uses cache and does not duplicate records.
- [ ] Test offline replay, missing source response, retry limits, and incomplete cached files. Write a coverage report; unavailable historical data must remain an explicit gap.

**Acceptance:** Actual records from both sources for the same pilot events, auditable full-field coverage, and a reproducible cache. Source feasibility failures are reported before expanding collection.

## Task 2: Normalize scores and interview structure

- [ ] Implement scoring aggregation with unique event/player/round/hole keys; validate 18 regulation holes and reconcile stroke totals against independent round totals when available. Conflicting duplicates fail validation; partial rounds are flagged, not imputed.
- [ ] Compute field means from all validated completed player-rounds in that event-round, independently of which players gave interviews. Recompute from raw strokes instead of summing precomputed hole-relative values with potentially different denominators.
- [ ] Parse ordered question/answer pairs and introductory player remarks; retain meaningful wording, punctuation, negation, and original text. Remove navigation, transcription credits, and speaker labels only from cleaned text.
- [ ] Handle missing questions and wrapped/multiline answers explicitly. Multi-player panels require reliable attribution or exclusion.
- [ ] Test cut players, playoff holes, duplicate/conflicting scores, missing holes, multiline answers, moderator text, and multiple speakers.

**Acceptance:** Validated `rounds`, `interviews`, and `segments` tables with provenance and a reason for every rejected record.

## Task 3: Match interviews to rounds and build targets

- [ ] Resolve event aliases by year, event dates, and source event ID. Normalize player names for candidate discovery but use reviewed ID mappings for joins; fuzzy matches become review candidates, never silent accepted joins.
- [ ] Establish interview round using explicit metadata and supporting text/schedule evidence. Calendar date alone is insufficient for delayed rounds. Exclude pre-event, post-final-round, and unresolved interviews.
- [ ] Deduplicate reposts by source IDs and normalized content hash. Combine distinct interviews for the same player/event/round in source order into one example with all source IDs retained, unless ordering is ambiguous.
- [ ] Define `relative_score(r) = strokes(r) - mean_complete_field_strokes(event, r)`; `y_reg = relative_score(r+1)`; `y_cls = int(relative_score(r+1) < relative_score(r))`.
- [ ] Keep the future field mean and next-round score only in target/audit columns, never features. Record no-next-round exclusions without inventing scores for cut/withdrawn players.
- [ ] Test same-name collisions, year/event collisions, delayed rounds, duplicates, ties, missing next rounds, and hand-calculated labels. Manually audit at least 30 matched examples spread across pilot events/rounds, or every match if fewer exist.

**Acceptance:** One unambiguous example per player/event/current round, correct labels, and a match ledger containing accepted, rejected, and review-needed cases.

## Task 4: Build time-safe features and split manifests

- [ ] Build current-round strokes and field-relative score, tournament-to-date scoring through r, and proposed prior-history windows of 5 and 20 rounds. Historical windows exclude the current event; include history counts and missingness indicators.
- [ ] Use scoring history from the entire eligible scoring population, not just interviewed golfers. Fetch earlier history when available; otherwise retain cold-start rows with explicit missingness, including at the 2015 boundary.
- [ ] Enforce the documented cutoff using round completion/order evidence. Never use final rank, final tournament totals/status, subsequent rounds, or whole-season aggregates as predictors. Same-day uncertain history is excluded conservatively.
- [ ] Create seeded tournament-year group assignments with seed 577, aiming for 80/10/10 by examples subject to whole-group allocation. Tiny pilot splits only test mechanics; meaningful evaluation waits for enough events.
- [ ] Save raw numerical features. Any later imputation/scaling is fitted on training data only; validation/test transforms reuse those fitted parameters. Freeze group assignments for all text/model comparisons.
- [ ] Test that changing future scores cannot alter earlier features, groups never cross splits, replay produces identical manifests, and held-out extremes cannot affect fitted preprocessing.

**Acceptance:** Feature lineage and cutoff policy documented, no cross-split event overlap, and no future-dependent feature values. Report that random grouped evaluation is retrospective; use chronological evaluation for a stronger forecasting claim.

## Task 5: Prepare text variants and audit the pilot

- [ ] Export answer-only, question+answer, forward-looking, and complementary non-forward-looking segment sets, all linked to the same example IDs.
- [ ] Implement transparent rules for confidence, physical condition, preparation, strategy, and expectations. Distinguish future intent from descriptions of past play; preserve multiple category flags and matched-rule explanations.
- [ ] Create a reproducible sample of 100 segments, or all if fewer, including predicted positives and negatives for human annotation. Report precision/recall only once human labels exist; an unlabeled sample is not a validation result.
- [ ] Define an explicit empty-forward-subset policy (empty flag plus masked/zero representation later); never silently drop those examples from comparisons.
- [ ] Produce `reports/data_quality.md` with source coverage by event/year, match yield, exclusions, missingness, class balance, text lengths, player concentration, and interview-selection bias relative to the scoring population.
- [ ] Run `python -m pytest` and the cached pilot pipeline; verify stable row counts/hashes across reruns and inspect the audit sample. Clearly separate machine checks from manual review still awaiting a person.

**Acceptance:** A reproducible pilot Parquet dataset, JSONL Q&A segments, split manifests, data dictionary, and an honest quality report. No unresolved/ambiguous record enters supervised data.

## Expansion after the pilot passes

Expand collection incrementally across verified 2015–2025 coverage, with resumable manifests and explicit exceptional-event handling. Then optionally cache frozen `all-MiniLM-L6-v2` segment embeddings: inspect the selected model's tokenizer limit, chunk by tokens while retaining segment ownership, store model revision/chunk settings/hash, and verify embedding dimensions. Retain raw text and segment boundaries for later attention/fine-tuning. Avoid weighting long answers more heavily merely because they create more chunks.

## Review focus

1. Full-field completeness, especially cut/withdrawn players: Task 1 coverage and Task 2 validation.
2. Temporal ambiguity and final-result leakage: Tasks 3–4 cutoff evidence and future-perturbation tests.
3. Ambiguous names/events and duplicated transcripts: Task 3 matching tests and review ledger.
4. Invalid formats, playoff/partial rounds, inconsistent scorecards: Task 2 reconciliation and eligibility checks.
5. Biased/empty language subsets and cold-start histories: Tasks 4–5 missingness and manual review samples.

## Approval checkpoint

The user approved this plan and its proposed cutoff. The original task checklists above are retained as the design baseline; the implementation ledger records what was delivered and the remaining research stages.
