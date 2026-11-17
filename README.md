# Golf interviews and round performance

This repository implements the **data preparation stage** of the research in
[proposal.md](proposal.md): testing whether pre-tournament and post-round
interview language helps predict a golfer's next-round performance beyond scoring statistics.

## Current pipeline

The current work builds an interview dataset with tournament timing and scores
for selected tournaments from **2015–2025**:

1. **Select tournaments:** use the saved 325-event shortlist linking ASAP Sports
   tournament listings to golfastR scoring events.
2. **Collect and parse:** download transcripts and hole scores, extract ordered
   Q&A, and aggregate complete 18-hole scores for all golfers in each event.
3. **Match golfers:** compare interviewee names with the event's scoring roster
   and approve unique matches.
4. **Assign interview stages:** dates before the scheduled start are
   `pre_round_1`; dates on tournament days 1–4 are `post_round_1` through
   `post_round_4`. Check explicit round headings and require a complete score
   for post-round interviews. Conversation wording does not affect matching.
5. **Export:** save included interviews with their Q&A, stage, and completed-round
   score when applicable. Save an outcome for every collected interview so
   unresolved matches and exclusions can be traced.

**Current result:** 17,398 collected interviews → **15,876 included interviews**
(2,341 pre-tournament and 13,535 post-round) across 315 events and 791 player IDs
(local snapshot checked 2026-11-16).
Matches rely on the schedule and timing assumptions described below.

Each included row represents **one interview**. `interview_stage` records when it
occurred relative to tournament play. A `post_round_2` interview contains round-2
strokes; a `pre_round_1` interview has no completed round or score. Next-round
targets, features, and models have not been built yet.

## Important files

Start with `dataset.parquet` for the matched interviews and `scores.parquet` for
full-field scoring. Use `matches.csv` and the decision tables to trace a match or
understand why an interview was left out.

| Path | What it contains / when to use it |
| --- | --- |
| `data/processed/dataset.parquet` | Included interviews: player/event IDs, interview stage, completed round/score when applicable, ordered Q&A, and matching metadata |
| `data/processed/scores.parquet` | All available player-round scores in selected events, including golfers without interviews; needed for field averages and next-round joins |
| `data/processed/matches.csv` | One outcome and reason for every collected interview, including exclusions |
| `data/processed/interviews.jsonl` | Parsed transcripts, parse status, source URLs, and hashes |
| `data/decisions/pga_events.csv` | Saved tournament shortlist, mapping provenance, and scoring-format flags |
| `data/decisions/events.csv` | Event inventory; `collect=yes` selects downloads and `decision` controls inclusion |
| `data/decisions/players.csv` | Player identity decisions, keyed by event and interviewee name |
| `data/decisions/rounds.csv` | Accepted event-round date ranges and supporting evidence |
| `data/decisions/interviews.csv` | Per-interview context, round assignment, decision, and evidence |
| `data/raw/` | Cached downloads and metadata for reproducing prepared inputs |
| `src/golf_matching/`, `scripts/approve_players.py` | Pipeline implementation and player approval script; module guide below |

Decision CSVs are intended for version control. **Raw downloads and processed
outputs are ignored by Git**, so teammates need to generate them locally using
the commands below.

## Next steps

1. **Check the matching quality:** evaluate a sample of date-based assignments
   under the [current matching policy](#interview-stage-assignment).
   Resolve scoring-format eligibility and multiple interviews per player-stage.
2. **Build the prediction datasets:** for regression, pair pre-tournament
   interviews with round 1 and post-round 1–3 interviews with round `r + 1`.
   Require a complete target score at this step. Classification uses only
   post-round 1–3 interviews to compare consecutive rounds in the same event.
   Calculate field-relative scores using all complete player-rounds in
   `scores.parquet`.
3. **Build features:** derive answer-only, Q&A, and forward-looking text variants
   plus scoring features available before the predicted round. The selected-event
   score corpus does not provide complete career histories.
4. **Run the proposed experiments:** create tournament-year grouped splits, then
   implement the statistical/language baselines and neural models in
   [proposal.md](proposal.md).

## Decisions and assumptions

### Tournament scope and player matching

The saved shortlist contains 325 tournament-years from 2015–2025: 274 exact-name
mappings and 51 approved name variants. Discovery only suggests exact normalized
matches; it does not recreate the earlier name-variant selection.
`events.csv` controls collection through `collect=yes`. New player approvals
require the event key and scoring ID to be approved in both `events.csv` and
`pga_events.csv`; those files do not synchronize automatically. `prepare`, `align`,
and `build` use `events.csv` and do not independently enforce the shortlist or
its format flags. Tour Championship and Barracuda entries still need a research
eligibility decision.

Player names are compared within each event's scoring roster, ignoring case,
accents, whitespace, and punctuation. A unique ID with an agreeing stored
suggestion is approved. No match or multiple matching IDs produces a rejection.
There is no fuzzy or nickname matching. Changed evidence or conflicting edits
remain unresolved.

### Transcript parsing and score totals

The archive's named golfer is the answer speaker. The parser supports paragraph
and older line-break transcripts, matching speaker labels to that golfer's name.
Other labeled speakers supply interviewer/context text and do not cause rejection.
Their labels are recorded in `other_speaker_names` in `interviews.jsonl`; their
speech never becomes the golfer's answer. No moderator name list or introductory
phrase is required. If no answers from the named golfer can be extracted, the
record retains `parse_status=no_player_answers`.

The parser normalizes a known double-encoded nonbreaking-space sequence that can
obscure speaker/question labels in older transcripts. Original downloaded bytes
and their hashes are preserved. Other encoding artifacts may remain.

Scores cover the full available field in selected events. A complete round
requires 18 distinct holes numbered 1–18, each with a positive integer score.
Identical hole records are deduplicated; partial or conflicting records have
null `strokes`. Only rounds 1–4 are retained. Totals do not include leaderboard
starting bonuses or Stableford points.

### Interview-stage assignment

Dates before the scheduled tournament start receive `interview_stage=pre_round_1`
and `context=pre_tournament`. They require a matched player in the event roster,
but no completed-round score. `round` is empty and `strokes` is null. An explicit
round heading conflicts with this assignment and keeps the interview ambiguous.

On tournament days, automatic matching uses:

```text
round = 1 + (interview_date - scheduled_start_date), for rounds 1–4
```

Matching uses the interview's date, identity, explicit HTML round heading (when
present), and scoring record. A heading that disagrees with the scheduled round
stays ambiguous; a complete score is required for post-round inclusion. Successful
assignments receive `interview_stage=post_round_1` through `post_round_4`.

**Q&A wording is not used to accept, reject, or label an interview.** There are
no conversational timing checks, score/round extraction from answers or questions,
or historical/future/playoff phrase filters. The parsed Q&A is retained for
subsequent language analysis.

Every automatic post-round match has `context=post_round_assumed`. Both pre- and
post-round automatic matches have `verification_status=schedule_assumed`.
A matching round heading corroborates the round number, but does not prove that the interview happened after completion.
Manual review can still establish `context=post_round` or exclude an interview.

Pre-tournament timing assumes the scheduled start date is correct. Post-round
timing assumes one completed round per day from that start,
with the interview following that day's round. Weather delays, multiple rounds on
one date, shortened events, and Monday finishes can break that assumption. A
pre-round, mid-round, or playoff interview can be included if its date, identity,
heading, and complete regulation score pass these checks. No automatic exception
calendar or player-specific finish-date input is implemented.

Matching accuracy has not been measured across the corpus. Interview availability
and parsing also affect which golfers and events appear in the dataset.

### Unit of observation and prediction targets

We retain one row per interview, including pre-tournament and final-round
interviews, regardless of whether a future target score is available. The snapshot
has 2,978 round-4 interviews and 816 rows beyond one per
`(event_key, player_id, interview_stage)` (744 of those are post-round duplicates).
These need task-specific filtering or an explicit handling policy before modeling.

The planned targets are:

| Interview stage | Regression target | Improvement classification |
| --- | --- | --- |
| `pre_round_1` | Round-1 field-relative score | Not used: no prior round in this event |
| `post_round_1`–`post_round_3` | Next-round field-relative score | Is the next round better than the completed round? |
| `post_round_4` | Not used for within-event prediction | Not used |

`field_relative_score = strokes - field_mean`; lower is better. Field means must
use all complete scores in an event-round, including golfers without interviews.
The stored `strokes` is the completed round's raw total, never a prediction target.
Pre-tournament rows have no current-event performance statistics; historical
features can still be used. Missing current-event features must be handled during
model preparation, rather than treated as zero scores.

## Running the pipeline

Requirements: **Python 3.12+** and **uv**. Run from the repository root:

```bash
# Install dependencies and test tools.
uv sync --extra dev --locked

# Download/cache sources, parse interviews, and calculate round totals.
uv run golf-match prepare

# Approve unique player-name matches within each event.
uv run python scripts/approve_players.py

# Assign interview stages and export the dataset.
uv run golf-match align
```

The event selection is supplied in `data/decisions/`. Raw downloads and generated
outputs are **not included in Git**. The first collection can take hours;
subsequent runs reuse cached downloads.

If `prepare` ends with **“run align before build,”** its prepared inputs have
already been saved. Continue with the player script and `align` above. Other
preparation failures require resolving the reported problem and rerunning `prepare`.

### Other commands and reproducibility

| Task | Command |
| --- | --- |
| Reparse/aggregate an existing cache | `uv run golf-match prepare --offline`, then the player script and `align` |
| Recalculate automatic stage/round decisions | `uv run golf-match align` |
| Apply interview/round edits to unchanged prepared inputs | `uv run golf-match build` |
| Discover inventory entries for a year range | `uv run golf-match prepare --years 2015:2025` |
| Run tests | `uv run pytest -q` |

All commands, including the player script, accept `--root PATH`. `--offline`
requires every requested source to be cached. `align` and `build` always run
locally and do not accept `--offline` or `--years`.

**Discovery:** new entries start with `decision=pending`, `collect=no`. Discovery
suggests exact normalized tournament-name matches; it does not reconstruct the
shortlist's historical name-variant approvals. `--years` selects discovery years,
not a subset of already selected collection events. To expand scope, verify the
mapping, update both event files, set `collect=yes`, and rerun the pipeline.
The shortlist's scoring-format flags are metadata, not enforced filters.

**Caching:** raw bytes and URL/hash metadata live in `data/raw/http/`. Cached
bytes are verified when fetched and reused indefinitely; rerunning `prepare`
does not refresh an already cached URL. Decision tables are saved after each
completed event; combined prepared outputs are written after collection finishes.
After an interrupted collection, rerun `prepare`.

**Rebuilding:** `prepare` and `align` both finish by calling `build`.
`data/raw/prepared.json` records the selected events and prepared-input hashes.
`build` checks those inputs, decision consistency, dates, and complete post-round
scores; it does not reread the raw HTTP cache. Automatic alignment hashes bind decisions
to schedules, prepared inputs, player mappings/decisions, and a declared policy
version. Relevant input changes require `align`; selection/source-ID changes
require `prepare`. Python source files are not hashed, so code changes may need
recomputation even without a stale-state error.

## Dataset fields

`dataset.parquet` contains only rows with `status=matched`:

| Fields | Meaning |
| --- | --- |
| `interview_id`, `transcript_url`, `source_hash` | ASAP identity, source URL, and SHA-256 of downloaded transcript bytes |
| `event_key`, `event_id`, `year`, `tournament` | ASAP tournament-year key, scoring event ID, archive year, and transcript tournament heading |
| `interview_name`, `player_id`, `player_name` | Archive speaker name and matched scoring identity |
| `interview_date` | Transcript date |
| `interview_stage` | `pre_round_1` or `post_round_1` through `post_round_4`; derived from the validated assignment |
| `round`, `strokes` | Completed round and raw total; empty round and null strokes for pre-tournament interviews |
| `segments` | Ordered records containing `order`, `question`, and `answer`; opening remarks may have no question |
| `context` | `pre_tournament`, `post_round_assumed` for automatic post-round timing, or `post_round` for manually reviewed timing |
| `status`, `reason` | Both `matched` in this file |
| `matching_method` | `scheduled_date`, `scheduled_date+transcript_heading`, or `manual_review` |
| `verification_status`, `schedule_source` | Schedule assumption and event reference, or manual status and round evidence |

```python
import pandas as pd

dataset = pd.read_parquet("data/processed/dataset.parquet")
print(dataset[["player_name", "interview_stage", "round", "strokes"]].head())
print(dataset.iloc[0]["segments"])  # Ordered question–answer records
```

`interview_stage` also appears in `matches.csv`, populated only for matched rows.
It is derived during export, not edited in `data/decisions/interviews.csv`.

## Tracing exclusions and manual review

To investigate an omitted interview, find its `interview_id` in `matches.csv`
and read `status` and `reason`. Then inspect the relevant decision record.
The reason is the first blocking result, with explicit rejections taking
priority; it does not enumerate every possible problem.

| Status | Meaning |
| --- | --- |
| `matched` | Passed the implemented inclusion checks |
| `excluded` | Explicit rejection, including automatic exclusions |
| `pending` | Missing approval, date assignment, or complete score |
| `ambiguous` | Explicit round heading or accepted round dates conflict with the date-based assignment |
| `identity_only` | Approved `other` context with no assigned round; not included in the dataset |

Keep identifiers as text when editing decision CSVs. Manual recovery is optional.
To recover a valid completed-round interview:

1. Verify and approve the player ID.
2. Approve the round's date range with an `evidence_url`.
3. Approve the interview with `context=post_round`, its completed `round`, and
   supporting `evidence`. Put your name in `reviewer` on edited records.
4. Run `align` if player mappings or event schedule dates changed; otherwise run
   `build`. Check the resulting row in `matches.csv`.

For a pre-tournament interview, approve the player and interview with
`context=pre_tournament`, an empty `round`, supporting `evidence`, and your name
in `reviewer`. Its date must precede the scheduled start and it must have no
explicit round heading; no round-date approval is needed.

`align` preserves named manual decisions. `prepare` can still mark changed source
evidence `needs_review`. Changing a round date range alone does not change the
automatic assignment formula; disrupted schedules need explicit manual interview
decisions. Parser failures require a parser correction and `prepare` before
approval can succeed.

## Coverage

Local snapshot checked on **2026-11-16**:

| Measure | Count |
| --- | ---: |
| Selected tournament-years / events with hole scores | 325 / 315 |
| Collected / successfully parsed interviews | 17,398 / 16,870 |
| Full-field / complete player-round rows | 124,913 / 122,426 |
| Included interviews | 15,876 |
| Included pre-tournament interviews | 2,341 |
| Included with assumed post-round timing | 13,535 |
| Excluded / pending / ambiguous interviews | 1,216 / 292 / 14 |
| Included events / distinct player IDs | 315 / 791 |

Ten selected entries have no hole scores: Barracuda 2015–2020 and the 2020 John
Deere, Sanderson Farms, Shriners, and THE PLAYERS entries. Missing scores are not
filled in.

For the current exclusion breakdown:

```python
import pandas as pd

matches = pd.read_csv("data/processed/matches.csv", dtype=str, keep_default_na=False)
print(matches.groupby(["status", "reason"]).size().sort_values(ascending=False))
```

## Repository layout

| Path | Responsibility |
| --- | --- |
| `src/golf_matching/sources.py` | Source discovery and HTTP cache |
| `src/golf_matching/preprocessing.py` | Transcript parsing, round totals, `prepare`, and `build` |
| `src/golf_matching/matching.py` | Decision tables and interview-to-score joins |
| `src/golf_matching/alignment.py` | Automatic stage/round assignment and manual-decision preservation |
| `src/golf_matching/cli.py` | Command-line interface |
| `scripts/approve_players.py` | Within-event player-name approvals and exclusions |
| `data/decisions/` | Saved event, player, round, and interview decisions |
| `tests/` | Parser, scoring, cache, matching, CLI, and offline pipeline tests |
| `proposal.md` | Research plan |

Runtime dependencies are pandas, PyArrow, Requests, and Beautiful Soup; pytest
is a dev extra. `pyproject.toml` and `uv.lock` define the environment.
