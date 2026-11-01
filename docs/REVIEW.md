# Review the first three rows by interview ID

Open `matching/charles-schwab-2024/review.csv` in a CSV viewer or spreadsheet editor. Do not start by approving all 19 rows. First try these three cases, then review the others the same way.

## What to check for every interview

1. Open `transcript_url`. Is this the named golfer, at Charles Schwab in 2024? Are they the only speaker relevant to this record?
2. Check their scoring identity against `players.csv`. The editable `player_id` starts with the suggestion; correct it only if you can identify the intended golfer in that roster. A name with no unique match needs review, not a guess.
3. Read enough of the interview to establish that the golfer has **finished** the proposed `round`. Look for discussion of their completed score/round and the upcoming round. The date alone is only a suggestion. Correct `round` if needed; set `post_round=yes` only when confirmed.
4. Check timing separately using `round_notes_url` (the official media page's round Notes/Tee Times links). For `timing=verified`, the round must have finished on the interview date and the next round must be on a later local date. An overnight suspension or uncertain availability means `timing=uncertain` or leave `pending`. This remains a date-level retrospective assumption; transcript publication timestamps are not provided.
5. Enter your decision, your name in `reviewer`, and notes for any correction/rejection/uncertainty. Save the CSV.

## Edit only these columns

| Column | What to enter |
| --- | --- |
| `decision` | `approve`, `reject`, or `needs_review`; leave untouched rows `pending` |
| `player_id` | Confirm/correct the suggested scoring ID using `players.csv` |
| `round` | Confirm/correct the completed interview round, 1–4 |
| `post_round` | `yes` only when you have confirmed it follows a completed round |
| `timing` | `verified`, `uncertain`, or `pending` |
| `reviewer` | Your name, required for approval |
| `notes` | Why you corrected, rejected, or remain uncertain |

During normal review, do not edit the source interview ID, event ID, source dates/links, suggestion columns, or fingerprint. The explicit stale-row procedure below is the only exception. If the event itself is wrong, mark `needs_review`; correct the source configuration instead of forcing the row through. All current suggestions were generated automatically and are not human approvals.

## Three examples to inspect yourself

- **`asap:197432` — Gary Woodland, May 24.** Suggested player `3550`, round `2`. Read the discussion comparing rounds 1 and 2. Check the official second-round notes: a weather suspension occurred, so confirm whether play resumed and completed that day. If you agree with the identity, completed round, and timing, approve with `post_round=yes`, `timing=verified`, and your name. This is a suggestion for your inspection, not a decision already made for you.
- **`asap:197470` — Jay Monahan, May 25.** No scoring player suggested. Check who is speaking: the commissioner is not a competing golfer. If confirmed, reject and note “not a player interview.”
- **`asap:197504` — Davis Riley, May 26.** Suggested player `10058`, round `4`. Check that it follows the final round. You can approve a correct source match with `post_round=yes` and your name; leave timing pending. Export will mark it `final_round`, not eligible for next-round prediction.

## After saving

```bash
uv run golf-match export
```

Read `status.csv`. Pending rows stay out of the approved export. Unknown IDs/rounds, missing reviewer, unconfirmed post-round context, or changed source evidence block approval. `approved_links.csv` contains valid approved matches, including ones with `final_round`, `missing_next_round`, or `timing_unverified` eligibility. **Only rows marked `eligible` are candidates for the later prediction dataset.** No training dataset is built here.

Rerunning `prepare` appends new rows without changing your old decisions, corrections, or notes. A `stale_source` status means the evidence changed; use the procedure below. Do not simply change the fingerprint to make the error disappear.

## If a row becomes stale later

No delivered rows are stale. For future source changes, refresh only the affected interview:

1. Save the current `review.csv` to a new dated file under `.local/review-history/` (or commit your decisions in Git). Never overwrite an earlier history copy.
2. Locate the same `interview_id` in the newly generated `candidates.csv`. Compare its transcript and scoring evidence with the old review. If it is absent, keep the old row and leave it out of export.
3. In `review.csv`, replace that row's **generated columns** with the current candidate values, including the new fingerprint. Keep its prior notes for context, but set `decision=pending`, `post_round=pending`, `timing=pending`, and clear `reviewer`. Reset `player_id` and `round` to the new suggestions. Keep exactly one row for this interview ID.
4. Review the refreshed row from scratch using the checklist above. Re-enter any justified correction and your fresh decision. An old approval is not carried over merely because the name looks the same.
5. Run `export` again. The archived review preserves the previous decision; the live row now refers to the new evidence.
