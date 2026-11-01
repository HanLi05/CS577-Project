# Golf interviews → next-round performance

CS577 data-preparation pilot based on the project proposal. The pipeline collects public ASAP Sports transcripts and golfastR's published full-field Parquet scores, checks scores against ESPN event/season scoreboards, and produces reviewed interview/next-round pairs. A small statistics-only regression experiment checks that the prepared data can be used for training and evaluation.

## Run

Python 3.12 or newer and [uv](https://docs.astral.sh/uv/) are required for this setup. R is not needed: the scoring source publishes Parquet directly.

```bash
uv sync --extra dev --locked
uv run pytest -q

# Rebuild the existing pilot entirely from cached sources:
uv run golf-data run --config configs/data.yaml --offline

# On a fresh checkout, fetch sources before building:
uv run golf-data run --config configs/data.yaml
```

`collect` fetches or replays sources; `build` processes collected data without network access; `run` does both. Downloads are paced, retried for transient failures, and cached with hashes. A corrupted cache fails loudly rather than silently replacing the snapshot. Source servers can change; cached snapshots and `uv.lock` are the basis for reproducibility.

## Small training check

After the prepared dataset exists, run:

```bash
uv run golf-data train
```

This command only reads the prepared data; it does not collect or rebuild anything. `training.py` uses the saved chronological split: THE PLAYERS trains (12 examples), Charles Schwab validates (14), and the Memorial tests (24). It compares predicting the current-round field-relative score again with Ridge regression (`alpha=1`, fixed before evaluation). Imputation and scaling are fitted only on training rows. There is no tuning or refitting on held-out data.

Outputs in `reports/pilot_regression/`:

- `results.md`: setup, MAE/RMSE, and limitations.
- `predictions.csv`: actual scores, both predictions, and errors for every example; filter `split` to separate train/validation/test.
- `metrics.csv`: errors for each method and split (in strokes).
- `experiment.json`: feature list, settings, training preprocessing statistics, and input/code/dependency hashes.

The first run's test MAE was **3.543 strokes for the baseline versus 13.133 for Ridge**. This is an end-to-end smoke test, not a successful predictive result. Training has just 12 post-round-3 examples from one event; later events include other rounds and different conditions. More reviewed data is the next priority. No interview text or forward-looking labels enter this model.

## Pilot scope

- THE PLAYERS Championship, Charles Schwab Challenge, and the Memorial Tournament, 2024.
- 88 collected transcript references; 87 single-speaker transcripts parsed; 50 supervised examples in the initial verified build.
- Interviews after rounds 1–3 paired with the following valid round. Final-round interviews, panels, unresolved identities, and uncertain timing are excluded or quarantined with reasons.
- THE PLAYERS rounds 1–2 are conservatively quarantined because rounds continued the following morning. The completed first-round field average was unavailable before some second-round tee times. A future extension can compare official completion times against each player's next tee time.
- Historical features use validated ordinary single-course individual events in the collected 2024 season. Multi-course, team, modified scoring, and unmatched event formats are excluded. Scores from golfers without interviews remain in the population.
- Probes for 2015, 2020, and 2025 establish source presence, not complete usable overlap. Full 2015–2025 collection is a later stage.

## Outputs

| Path | Contents |
| --- | --- |
| `data/processed/examples.parquet` | IDs, raw numerical features, labels, four text views |
| `data/processed/segments.jsonl` | Ordered Q&A segments, category flags, rule explanations; includes all parsed transcripts |
| `data/processed/splits.parquet` | Seeded tournament-year grouped assignments |
| `data/processed/splits_chronological.parquet` | Earlier events train, later events validation/test |
| `data/processed/feature_columns.json` | Explicit numerical feature allowlist; all other fields are metadata, text, or targets |
| `data/processed/build_manifest.json` | Input/output/config/code hashes |
| `data/interim/rounds.parquet` | Complete, reconciled player-round scores and full-field means |
| `reports/data_quality.md` | Counts, exclusions, completeness, selection bias, limitations |
| `reports/field_coverage.csv` | Expected vs validated player sets by event-round |
| `reports/match_ledger.csv` | Decision for every collected interview |
| `reports/review_segments.csv` | Sample awaiting human forward-looking annotations |
| `reports/review_matches.jsonl` | Stratified sample for inspecting joins, labels, and text |

Raw and derived datasets are ignored by Git. No transcripts or embeddings are uploaded or published. Cache sidecars record URLs, retrieval dates, response status, and content hashes. The generated build manifest makes changes detectable; it is not a substitute for retaining the source snapshots.

## Definitions and leakage controls

`relative_score(r) = strokes(r) - mean(strokes for all valid completed player-rounds in the same event and round)`.

Regression predicts `relative_score(r+1)`. Classification is 1 when that value is strictly lower than `relative_score(r)`; ties are 0. A golfer can therefore improve by this definition despite a worse raw stroke count.

The cutoff is after the interview and the complete current round, before the next round. For the accepted pilot observations, official round notes and next-day local tee dates support an end-of-day cutoff. ASAP supplies interview dates, not precise publication timestamps: this is a retrospective alignment assumption, not proof that a production system could have retrieved each transcript in real time.

History windows contain the most recent 5 or 20 available eligible rounds from **earlier events whose end dates precede the interview date**. The current event and same-day uncertainty are excluded. Window counts and missingness are explicit; pre-2024 history is absent. Current-event summaries use only rounds through the interview round. Future score, future field mean, final rank, final tournament status, and final totals are not numerical inputs.

Features are exported unscaled. `fit_preprocessor(training_features, columns)` fits median imputation and standardization only on the training partition supplied by the caller. Keep the feature allowlist when loading examples—do not train on every numeric column.

Three events cannot produce useful 80/10/10 evaluation partitions. The split implementation minimizes size deviation subject to whole event groups and nonempty partitions; the pilot splits only demonstrate mechanics. Do not report pilot model comparisons as reliable evaluation.

## Review and extend

Reviewed mappings live in `data/mappings/`: player IDs, transcript/round decisions tied to content hashes, and round timing with primary-source links. These were inspected by the implementing AI agent, not by a human annotator. New transcripts cannot become examples merely because their dates match: they require reviewed identity and post-round evidence. The matcher also validates unique tee-time identity and next-day timing without treating PGA Tour and ESPN IDs as interchangeable.

Forward-looking categories are transparent, overlapping rules for confidence, physical condition, preparation, strategy, and expectations. Current physical/confidence states can be relevant without explicit future tense. Rules are intentionally labeled unvalidated; they can overmatch words such as “back.” Annotate `reports/review_segments.csv`, inspecting both predicted positives and negatives, before using these subsets to make research claims. The pipeline never fabricates human labels. Keep completed annotations elsewhere before rebuilding: review exports are regenerated.

For a new event: add explicit source ID mappings to `configs/data.yaml`, collect it, inspect candidate records and timing, and extend reviewed CSVs. For another season, use a separate snapshot/output workspace or archive the existing data first: this pilot configuration collects one main season at a time. Full multi-season orchestration and embeddings are not implemented yet.

See [the approved plan](docs/superpowers/plans/2026-10-28-data-preparation.md), [data dictionary](docs/data_dictionary.md), and [implementation ledger](docs/progress.md).
