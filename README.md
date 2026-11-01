# Golf interview matching

This branch has one job: propose and review links between interview transcripts and scoring records. Start with Charles Schwab 2024 (19 interviews). There are no model features, text-category rules, embeddings, or training commands here.

## Start here

Open **[matching/charles-schwab-2024/review.csv](matching/charles-schwab-2024/review.csv)** and follow **[docs/REVIEW.md](docs/REVIEW.md)**. All decisions start pending; the old pilot approvals are not reused.

The CSV shows source links and suggested IDs/rounds. You edit only `decision`, `player_id`, `round`, `post_round`, `timing`, `reviewer`, and `notes`. Program-generated candidates remain separate from your edits. An approved source match is not necessarily eligible for next-round prediction.

## Commands

```bash
uv sync --extra dev --locked
uv run golf-match prepare --offline
uv run golf-match export
uv run pytest -q
```

`prepare` reuses the verified local source cache and appends only new interview IDs to the review file. It never overwrites existing review rows. On a new machine without the cache, omit `--offline` to download the public sources. `export` reads your decisions, validates the selected IDs and round, then writes approved links and a status report. No source collection happens during export.

A changed source fingerprint blocks an old approval until it is re-reviewed. Duplicate review keys fail explicitly. Changing the event/date configuration requires running prepare again. Generated input files have integrity checks and should not be edited.

## Small file structure

```text
configs/charles-schwab-2024.yaml     One event and proposed round dates
src/golf_matching/
  sources.py                       Cached downloads and source links
  candidates.py                    Collect metadata and propose matches
  review.py                        Preserve decisions; validate approvals
  cli.py                           prepare / export commands
matching/charles-schwab-2024/
  review.csv                       The file you edit; tracked in Git
  candidates.csv                   Generated suggestions (local)
  players.csv                      Scoring names and IDs (local)
  scoring_rounds.csv                Available player-rounds (local)
  approved_links.csv                Valid human-approved links (local)
  status.csv                       Reasons and next-round eligibility (local)
  inputs.json                      Generated input hashes (local)
docs/REVIEW.md                     What to check, with three examples
tests/                            Matching/review/cache checks
```

Scores come from golfastR's published Parquet files. Names are normalized for accents, punctuation, and case; only a unique exact normalized name is proposed. Round numbers are initially suggested from dates in the config. Neither suggestion proves the speaker or completed round: that is what the reviewer checks. This step checks complete 18-hole records for next-round eligibility, not full-field averages or independent score reconciliation.

For future years, use a separate config and output directory. Event IDs identify tournament editions; source interview IDs identify reviews. The code supports configuration-driven collection, but only this one event has been exercised end to end so far. Multi-person reviews should use a single assigned reviewer per row and normal Git review; conflicting duplicate decisions are not silently merged.

## Pilot reference

The full pilot is preserved on `reference/pilot`. Its local files and the verified archive live under ignored `.local/`; they are not part of the matching branch's tracked files. See [docs/pilot-reference.md](docs/pilot-reference.md) for recovery instructions. Nothing has been pushed remotely.
