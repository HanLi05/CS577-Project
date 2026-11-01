# Data dictionary

## Keys and provenance

- `event_id`: ESPN event ID, stored as text. In this source it identifies a particular event edition; split grouping also includes `year`.
- `player_id`: ESPN player ID, stored as text. PGA Tour IDs in tee-time data use a different namespace.
- `interview_id`: ASAP transcript ID; `source_url` links to the original.
- `segment_id`: interview ID plus zero-based segment order.
- `example_id`: `event_id:player_id:current_round`.
- `interview_date`: source calendar date, never an invented publication timestamp.
- `content_hash`: hash of normalized Q&A; binds reviewed decisions to parsed content.
- `raw_sha256`: hash of the source HTML, checked before parsing.
- Cache `.json` sidecars: original/resolved URL, UTC retrieval time, HTTP status, content type, byte length, SHA-256, collector version.
- `cutoff_evidence`: primary round-notes URL used by the timing review.

## Scoring and targets

- `round`: current regulation round, 1–3 in examples, 1–4 in scoring tables. Playoff holes are excluded.
- `strokes`: sum of 18 unique valid regulation holes.
- `field_size`, `field_mean`: all completed validated rounds in that event-round, independent of interviews and eventual cut/withdrawal status.
- `relative_score`: strokes minus the field mean; lower is better.
- `target_round`: `round + 1`.
- `y_reg`: next-round relative score.
- `y_cls`: 1 for strict relative-score improvement; 0 for worse or equal.
- `expected_strokes`, `holes_completed`, `final_status`: source-validation fields from ESPN. Never predictors.

Incomplete individual rounds are excluded; they are not zero-filled or extrapolated. A discrepancy between the expected complete-player set and validated hole records quarantines the entire event-round before features or labels are formed.

## Numerical feature allowlist

| Column | Definition |
| --- | --- |
| `current_strokes` | Current round's stroke total |
| `current_relative_score` | Current round's field-relative score |
| `tournament_mean_relative` | Mean relative score across this golfer's rounds 1 through r |
| `tournament_strokes` | Sum of strokes across rounds 1 through r |
| `completed_rounds` | Number of observed rounds through r |
| `history_{5,20}_mean` | Mean relative score in the last up-to-N eligible rounds at prior completed events |
| `history_{5,20}_count` | Number of observations actually available (0 through N) |
| `history_{5,20}_missing` | 1 when count is zero, otherwise 0 |

Missing means remain null. Scores are not imputed during preparation. Historical availability uses event end dates as conservative bounds. Features can use known earlier scores from an event that happens to belong to a different retrospective random split; no future information or target-derived preprocessing is permitted. Use the chronological split to evaluate forecasting.

## Text

Segment rows contain `question`, `answer`, `speaker`, `order`, `forward_looking`, overlapping `categories`, `rule_matches`, and `rule_version`. Unprompted player remarks have an empty question. Moderator prompts may appear as questions; moderator responses never appear as golfer answers. Multispeaker panels are excluded.

Example text views: `answers_only`, `question_answer`, `forward_answers`, `non_forward_answers`; `forward_segment_ids` and `non_forward_segment_ids` partition the ordered segments. `forward_empty` preserves examples with no matched forward-looking content, allowing the same cohort across ablations. No stopword removal, stemming, or negation deletion is applied.

`segments.jsonl` includes unmatched/final-round parsed interviews for auditing. Join to accepted example interview IDs before using it for modeling.

## Splits and audits

Split rows contain `example_id`, `event_id`, `year`, `split` (`train`, `validation`, `test`). Seed 577 is fixed in configuration; allocation is deterministic for a fixed dataset. Adding events can change assignments, so archive each dataset version and its split files.

Match ledger status is `accepted`, `excluded`, or `review_needed`, with a reason. Both excluded and review-needed rows are absent from supervised examples. `reports/review_segments.csv` contains blank human-label fields intentionally; it is an annotation worksheet, not measured accuracy.
