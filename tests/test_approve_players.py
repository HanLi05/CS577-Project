import csv
from pathlib import Path
import subprocess
import sys

import pandas as pd

from golf_matching.matching import COLUMNS


SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/approve_players.py'


def write_csv(path, columns, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, lineterminator='\n')
        writer.writeheader()
        writer.writerows(rows)


def test_approval_requires_approved_event_and_unique_roster_name_and_preserves_edits(tmp_path):
    review = tmp_path / 'data/decisions'
    event = dict(event_key='2024:Open', event_id='e', decision='approve')
    other = dict(event_key='2024:Other', event_id='other', decision='pending')
    write_csv(review / 'events.csv', COLUMNS['events'], [event, other])
    write_csv(review / 'pga_events.csv', list(event), [event, other])
    cases = [
        ('José Doe', 'p', 'pending', '', ''),
        ('Unknown Person', '', 'pending', '', ''),
        ('Alex Smith', 'a', 'pending', '', ''),
        ('Rejected Player', 'r', 'reject', 'Reviewer', 'non-player'),
        ('Manual Player', 'm', 'approve', 'Reviewer', 'checked'),
        ('Changed Source', 's', 'needs_review', 'Reviewer', 'source changed'),
        ('Corrected Player', 'corrected', 'pending', 'Reviewer', 'ID correction'),
        ('Stale Suggestion', 'stale', 'pending', '', ''),
    ]
    rows = []
    roster = []
    for name, pid, decision, reviewer, notes in cases:
        rows.append(dict(event_key='2024:Open', event_id='e', interview_name=name,
                         scoring_name='JOSE DOE' if name == 'José Doe' else name,
                         player_id=pid, suggested_player_id='original' if name == 'Corrected Player' else pid,
                         decision=decision, reviewer=reviewer, notes=notes, source_hash='unchanged'))
        if pid:
            roster.append(dict(event_key='2024:Open', event_id='e', player_name=name,
                               player_id='original' if name == 'Corrected Player' else pid))
    roster.append(dict(event_key='2024:Open', event_id='e', player_name='Alex-Smith', player_id='b'))
    # Duplicate rounds for the same player must not make the identity ambiguous.
    roster.append(dict(roster[0]))
    rows[-1]['suggested_player_id'] = 'wrong'
    rows.append(dict(rows[0], event_key='2024:Other', event_id='other'))
    roster.append(dict(roster[0], event_key='2024:Other', event_id='other'))
    # A same-named player in another event cannot supply a missing roster match.
    roster.append(dict(event_key='2024:Other', event_id='other', player_name='Unknown Person', player_id='u'))
    write_csv(review / 'players.csv', COLUMNS['players'], rows)
    processed = tmp_path / 'data/processed'
    processed.mkdir(parents=True)
    pd.DataFrame(roster).to_parquet(processed / 'scores.parquet', index=False)
    before = list(csv.DictReader((review / 'players.csv').open()))
    result = subprocess.run([sys.executable, str(SCRIPT), '--root', str(tmp_path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    after = list(csv.DictReader((review / 'players.csv').open()))
    assert after[0]['decision'] == 'approve'
    assert after[0]['reviewer'] == 'auto:name_match'
    assert after[3:] == before[3:]
    for row in after[1:3]:
        assert row['decision'] == 'reject'
        assert row['reviewer'] == 'auto:unmatched'
        assert 'Excluded: ' in row['notes']
    assert 'no_name_match' in after[1]['notes']
    assert 'ambiguous_name_match' in after[2]['notes']
    assert not (review / 'players_to_review.csv').exists()
    snapshot = {p.name: p.read_bytes() for p in review.glob('*.csv')}
    subprocess.run([sys.executable, str(SCRIPT), '--root', str(tmp_path)], check=True)
    assert snapshot == {p.name: p.read_bytes() for p in review.glob('*.csv')}
