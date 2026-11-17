"""Approve unique player-name matches and exclude unmatched players.

Run from the project root: uv run python scripts/approve_players.py
All decisions and exclusion reasons remain recorded in players.csv.
"""
import argparse
from collections import Counter, defaultdict
import csv
from pathlib import Path

import pandas as pd

from golf_matching.matching import COLUMNS, index_rows, read_table
from golf_matching.preprocessing import normalize


def write_csv(path, columns, rows):
    temporary = path.with_suffix('.csv.tmp')
    with temporary.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)
    temporary.replace(path)


def approve_players(root):
    review = Path(root) / 'data/decisions'
    for name in ('players.csv', 'events.csv', 'pga_events.csv'):
        if not (review / name).is_file():
            raise FileNotFoundError(review / name)
    players = read_table(review / 'players.csv', 'players')
    events = read_table(review / 'events.csv', 'events')
    with (review / 'pga_events.csv').open(newline='') as stream:
        pga = list(csv.DictReader(stream))
    index_rows(pga, ['event_key'])
    approved_events = {(r['event_key'], r['event_id']) for r in events if r['decision'] == 'approve'}
    approved_events &= {(r['event_key'], r['event_id']) for r in pga if r['decision'] == 'approve'}

    # Check the actual event roster, not just the displayed name suggestion.
    scores = pd.read_parquet(Path(root) / 'data/processed/scores.parquet',
                             columns=['event_key', 'event_id', 'player_id', 'player_name'])
    roster = defaultdict(set)
    for key, eid, pid, name in scores.drop_duplicates().itertuples(index=False, name=None):
        roster[(str(key), str(eid), normalize(name))].add(str(pid))

    approved, excluded, unresolved = 0, 0, []
    for row in players:
        if row['decision'] in ('approve', 'reject'):
            continue
        event = (row['event_key'], row['event_id'])
        name = normalize(row['interview_name'])
        ids = roster.get((*event, name), set()) if name else set()
        if event not in approved_events:
            reason = 'event_not_approved'
        elif row['decision'] == 'needs_review':
            reason = 'source_changed'
        elif row['decision'] not in ('', 'pending'):
            reason = 'unrecognized_decision'
        elif row['player_id'] and row['player_id'] != row['suggested_player_id']:
            reason = 'manual_player_id'
        elif not ids:
            reason = 'no_name_match'
        elif len(ids) != 1:
            reason = 'ambiguous_name_match'
        else:
            pid = next(iter(ids))
            if row['player_id'] not in ('', pid):
                reason = 'manual_player_id'
            elif row['suggested_player_id'] != pid or normalize(row['scoring_name']) != name:
                reason = 'suggestion_mismatch'
            else:
                row.update(player_id=pid, decision='approve', reviewer='auto:name_match')
                row['notes'] = (row['notes'] + ' Unique normalized-name match within the event scoring roster.').strip()
                approved += 1
                continue
        if reason in ('no_name_match', 'ambiguous_name_match'):
            row.update(decision='reject', reviewer='auto:unmatched')
            row['notes'] = (row['notes'] + f' Excluded: {reason}.').strip()
            excluded += 1
        else:
            unresolved.append(dict(row, reason=reason))

    # Preserve row order, existing approvals/rejections, and human corrections.
    write_csv(review / 'players.csv', COLUMNS['players'], players)
    print(f'Newly approved: {approved}. Newly excluded: {excluded}. Unchanged unresolved: {len(unresolved)}.')
    if unresolved:
        print(f'Unresolved reasons: {dict(Counter(r["reason"] for r in unresolved))}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    approve_players(parser.parse_args().root)
