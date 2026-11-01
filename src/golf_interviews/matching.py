"""Connect interviews to scoring records using player, tournament, and round.

Reviewed CSVs supply player IDs and interview round numbers. This file checks
those assignments and confirms a next-round record exists; dataset.py later
reads that record's score to create the prediction target.
"""
import pandas as pd
from .interviews import normalize_name


def match_interviews(interviews, rounds, aliases, reviews, timing):
    # These inputs come from data/mappings/players.csv, interview_reviews.csv,
    # and round_timing.csv. The pilot assignments were inspected by the AI agent.
    aliases = aliases.copy()
    aliases['normalized'] = aliases.name.map(normalize_name)
    # Each scoring record is identified by (tournament ID, player ID, round).
    round_keys = set(zip(rounds.event_id, rounds.player_id, rounds['round']))
    accepted, ledger, seen = [], [], set()
    for row in interviews.sort_values('interview_id').to_dict('records'):
        iid, eid = row['interview_id'], row['event_id']
        reason, status = 'matched', 'accepted'
        # Look up the transcript name within this tournament, not across all golf.
        ids = aliases.loc[(aliases.event_id == eid) & (aliases.normalized == normalize_name(row['player_name'])), 'player_id'].unique()
        # Look up the reviewed round assignment for this particular interview.
        # We do not automatically assume that a Friday interview means round 2.
        review = reviews.loc[(reviews.interview_id == iid) & (reviews.event_id == eid)]
        pid, rnd = None, None
        if len(ids) != 1:
            reason = 'ambiguous_player' if len(ids) > 1 else 'unmapped_player'
        # The review must confirm a post-round interview and match the text's hash,
        # so a decision about an older version cannot silently apply to new text.
        elif len(review) != 1 or not bool(review.iloc[0].post_round) or not review.iloc[0].evidence or review.iloc[0].content_hash != row['content_hash']:
            reason = 'unreviewed_interview'
        else:
            pid, rnd = str(ids[0]), int(review.iloc[0]['round'])
            # Cross-check the assigned round against reviewed event dates and any
            # explicit round number in the transcript header. Delays can invalidate
            # a simple date-based match, so uncertain timing is kept out.
            period = timing.loc[(timing.event_id == eid) & (timing['round'] == rnd)]
            if rnd not in (1, 2, 3):
                reason = 'ineligible_round'
            elif pd.notna(row['explicit_round']) and int(row['explicit_round']) != rnd:
                reason = 'round_conflict'
            elif len(period) != 1 or not bool(period.iloc[0].verified) or not period.iloc[0].evidence_url:
                reason = 'unverified_timing'
            elif row['interview_date'] != period.iloc[0].round_date or period.iloc[0].next_round_date <= row['interview_date']:
                reason = 'ambiguous_timing'
            # Require scores for this golfer in the SAME tournament at rounds
            # rnd and rnd + 1. For an interview after round 2, the target is round 3.
            elif (eid, pid, rnd) not in round_keys:
                reason = 'missing_current_round'
            elif (eid, pid, rnd + 1) not in round_keys:
                reason = 'missing_next_round'
            # Earlier rounds are also needed for tournament-to-date features.
            elif any((eid, pid, prior) not in round_keys for prior in range(1, rnd)):
                reason = 'incomplete_tournament_history'
            elif (eid, pid, rnd, row['content_hash']) in seen:
                reason = 'duplicate_content'
            else:
                seen.add((eid, pid, rnd, row['content_hash']))
                accepted.append(dict(row, player_id=pid, round=rnd,
                                     cutoff_evidence=period.iloc[0].evidence_url,
                                     cutoff_policy='end_of_verified_round_day_before_next_round'))
        if reason != 'matched':
            status = 'review_needed' if reason in ('ambiguous_player','unmapped_player','unreviewed_interview','unverified_timing','ambiguous_timing','round_conflict') else 'excluded'
        # Keep a decision for every interview, including why it was left out.
        ledger.append(dict(interview_id=iid, event_id=eid, player_id=pid, round=rnd, status=status, reason=reason))
    matched = pd.DataFrame(accepted, columns=list(interviews.columns) + ['player_id','round','cutoff_evidence','cutoff_policy'])
    log = pd.DataFrame(ledger)
    if not matched.empty:
        # Date-only transcripts cannot establish order between different interviews.
        multiple = matched.duplicated(['event_id','player_id','round'], keep=False)
        bad = set(matched.loc[multiple,'interview_id'])
        log.loc[log.interview_id.isin(bad), ['status','reason']] = ['review_needed','ambiguous_interview_order']
        matched = matched.loc[~multiple].reset_index(drop=True)
    return matched, log


def verify_tee_dates(matches, tees, config):
    """IDs are different namespaces; require unique normalized names within event."""
    # Final date check against tee times. PGA Tour tee-time IDs differ from ESPN
    # scoring IDs, so use the configured event mapping and a unique player name.
    event_ids={e['event_id']:e['tee_event_id'] for e in config['events']}
    rejected=[]; keep=[]
    for row in matches.to_dict('records'):
        event=tees.loc[tees.tournament_id.astype(str)==event_ids[row['event_id']]]
        player=event.loc[event.player_name.map(normalize_name)==normalize_name(row['player_name'])]
        reason=None
        if player.player_id.nunique()!=1:
            reason='ambiguous_tee_identity'
        else:
            current=player.loc[player['round']==row['round']]
            nxt=player.loc[player['round']==row['round']+1]
            if len(current)!=1 or len(nxt)!=1:
                reason='missing_tee_time'
            else:
                def local_date(record):
                    ts=pd.Timestamp(record.tee_time)
                    if ts.tzinfo is None:
                        raise ValueError('tee_time must include timezone')
                    return ts.tz_convert(record.timezone).date().isoformat()
                # This pilot accepts same-day post-round interviews with the next
                # round on a later local date; it does not infer publication times.
                if local_date(current.iloc[0])!=row['interview_date'] or local_date(nxt.iloc[0])<=row['interview_date']:
                    reason='tee_timing_conflict'
        if reason:
            rejected.append(dict(interview_id=row['interview_id'],reason=reason))
        else:
            keep.append(row['interview_id'])
    return matches.loc[matches.interview_id.isin(keep)].reset_index(drop=True), rejected
