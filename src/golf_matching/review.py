"""Preserve human decisions and export only valid, explicit approvals."""
from pathlib import Path
import pandas as pd

EDITABLE = ['decision', 'player_id', 'round', 'post_round', 'timing', 'reviewer', 'notes']


def read_csv(path):
    frame = pd.read_csv(path, dtype=str, keep_default_na=False)
    if frame.interview_id.duplicated().any():
        raise ValueError(f'Duplicate interview review keys: {path}')
    return frame


def sync_review(candidates, path):
    """Append new interviews only. Never refresh or overwrite existing review rows."""
    path = Path(path)
    if candidates.interview_id.duplicated().any():
        raise ValueError('Duplicate candidate interview keys')
    old = read_csv(path) if path.exists() else pd.DataFrame()
    new = candidates.loc[~candidates.interview_id.isin(old.interview_id if len(old) else [])].copy()
    if new.empty and path.exists():
        return
    new['decision'] = 'pending'
    new['player_id'] = new.suggested_player_id
    new['round'] = new.suggested_round
    new['post_round'] = 'pending'
    new['timing'] = 'pending'
    new['reviewer'] = ''
    new['notes'] = ''
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.concat([old, new], ignore_index=True).to_csv(path, index=False)


def export_reviews(candidates, path, scores, round_dates):
    """A correct identity/round link can still be ineligible for prediction."""
    reviews = read_csv(path)
    if candidates.interview_id.duplicated().any():
        raise ValueError('Duplicate candidate interview keys')
    current = candidates.set_index('interview_id')
    accepted, status = [], []
    for row in reviews.to_dict('records'):
        iid = row['interview_id']
        reason, eligibility, rnd = '', 'not_approved', None
        if iid not in current.index:
            reason = 'not_in_current_candidates'
        elif row['source_fingerprint'] != current.loc[iid, 'source_fingerprint']:
            reason = 'stale_source'
        elif row['event_id'] != current.loc[iid, 'event_id']:
            reason = 'event_conflict'
        elif row['decision'] == 'reject':
            reason = 'rejected'
        elif row['decision'] in ('pending', 'needs_review', ''):
            reason = 'pending_review'
        elif row['decision'] != 'approve':
            reason = 'invalid_decision'
        elif not row['reviewer'].strip():
            reason = 'missing_reviewer'
        elif row['post_round'] != 'yes':
            reason = 'post_round_not_confirmed'
        elif row['timing'] not in ('pending', 'verified', 'uncertain'):
            reason = 'invalid_timing'
        elif row['round'] not in ('1', '2', '3', '4'):
            reason = 'invalid_round'
        else:
            rnd = int(row['round'])
            # Corrected values must identify a real record in this event's scores.
            player = scores.loc[(scores.event_id == row['event_id']) & (scores.player_id == row['player_id'])]
            matching = player.loc[player['round'].astype(str) == str(rnd)]
            if len(matching) != 1:
                reason = 'unknown_player_round'
            else:
                reason = 'approved'
                nxt = player.loc[player['round'].astype(str) == str(rnd + 1)]
                if not bool(matching.iloc[0].complete):
                    eligibility = 'incomplete_current_round'
                elif rnd == 4:
                    eligibility = 'final_round'
                elif len(nxt) != 1 or not bool(nxt.iloc[0].complete):
                    eligibility = 'missing_next_round'
                elif row['timing'] != 'verified':
                    eligibility = 'timing_unverified'
                elif (round_dates.get(rnd) != current.loc[iid, 'interview_date']
                      or round_dates.get(rnd + 1, '') <= current.loc[iid, 'interview_date']):
                    eligibility = 'timing_conflict'
                else:
                    eligibility = 'eligible'
                accepted.append(dict(interview_id=iid, event_id=row['event_id'], player_id=row['player_id'],
                    round=rnd, target_round=rnd+1 if rnd<4 else None, year=current.loc[iid,'year'],
                    transcript_url=current.loc[iid,'transcript_url'], reviewer=row['reviewer'],
                    source_fingerprint=row['source_fingerprint'], eligibility=eligibility, notes=row['notes']))
        status.append(dict(interview_id=iid, reason=reason, eligibility=eligibility))
    columns=['interview_id','event_id','player_id','round','target_round','year','transcript_url',
             'reviewer','source_fingerprint','eligibility','notes']
    return pd.DataFrame(accepted,columns=columns),pd.DataFrame(status,columns=['interview_id','reason','eligibility'])
