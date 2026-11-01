"""Regulation-round scoring; never filter the field to interviewed players."""
import pandas as pd

ROUND_KEY = ['event_id', 'player_id', 'round']
ROUND_COLUMNS = ROUND_KEY + ['player_name', 'strokes', 'field_size', 'field_mean', 'relative_score']


def aggregate_rounds(holes, expected=None):
    data = holes.copy()
    key = ROUND_KEY + ['hole']
    if data[key].isna().any().any():
        raise ValueError('missing scoring key')
    # Ignore irrelevant derived columns when deciding whether a duplicate conflicts.
    data = data[key + ['player_name', 'par', 'score']].drop_duplicates()
    if data.duplicated(key).any():
        raise ValueError('conflicting hole records')
    totals = {} if expected is None else {
        (str(r.event_id), str(r.player_id), int(r.round)): r.expected_strokes
        for r in expected.itertuples() if pd.notna(r.expected_strokes)
    }
    records, issues = [], []
    for (event, player, rnd), group in data.groupby(ROUND_KEY, sort=True):
        item = dict(event_id=str(event), player_id=str(player), round=int(rnd))
        reason = None
        if rnd not in (1, 2, 3, 4):
            reason = 'non_regulation_round'
        elif len(group) != 18 or set(group.hole) != set(range(1, 19)):
            reason = 'incomplete_round'
        elif group.score.isna().any() or not ((group.score > 0) & (group.score % 1 == 0)).all():
            reason = 'invalid_score'
        elif (str(event), str(player), int(rnd)) in totals and group.score.sum() != totals[(str(event), str(player), int(rnd))]:
            reason = 'round_total_mismatch'
        if reason:
            issues.append(dict(item, reason=reason, hole_count=len(group)))
        else:
            records.append(dict(item, player_name=group.player_name.iloc[0], strokes=int(group.score.sum())))
    result = pd.DataFrame(records, columns=ROUND_KEY + ['player_name', 'strokes'])
    if not result.empty:
        fields = result.groupby(['event_id', 'round']).strokes
        result['field_size'] = fields.transform('size')
        result['field_mean'] = fields.transform('mean')
        result['relative_score'] = result.strokes - result.field_mean
    return result.reindex(columns=ROUND_COLUMNS), pd.DataFrame(issues, columns=ROUND_KEY + ['reason', 'hole_count'])


def reconcile_fields(rounds, reference, observed):
    """Quarantine whole fields and explain every observed/reference regulation group."""
    columns=['event_id','round','expected_players','valid_players','missing_players','extra_players','verified','reason']
    keys=set()
    for frame in (observed,reference):
        keys.update((r.event_id,r.round) for r in frame[['event_id','round']].drop_duplicates().itertuples() if r.round in (1,2,3,4))
    coverage=[];valid=set()
    for eid,rnd in sorted(keys):
        ref=reference.loc[(reference.event_id==eid)&(reference['round']==rnd)]
        expected=set(ref.loc[ref.holes_completed==18,'player_id'])
        actual=set(rounds.loc[(rounds.event_id==eid)&(rounds['round']==rnd),'player_id'])
        missing,extra=expected-actual,actual-expected
        reason=('missing_reference_group' if ref.empty else 'player_set_mismatch' if missing or extra
                else 'no_complete_rounds' if not actual else 'verified')
        verified=reason=='verified'
        coverage.append(dict(event_id=eid,round=rnd,expected_players=len(expected),valid_players=len(actual),
                             missing_players=','.join(sorted(missing)),extra_players=','.join(sorted(extra)),
                             verified=verified,reason=reason))
        if verified:
            valid.add((eid,rnd))
    mask=[(r.event_id,r.round) in valid for r in rounds.itertuples()]
    return rounds.loc[mask].reset_index(drop=True),pd.DataFrame(coverage,columns=columns)
