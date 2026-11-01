import pandas as pd
import pytest
from golf_interviews.scoring import aggregate_rounds, reconcile_fields


def holes(player='1', round=1, strokes=4):
    return [dict(event_id='e', player_id=player, player_name=player, round=round,
                 hole=h, par=4, score=strokes) for h in range(1, 19)]


def test_full_field_includes_cut_players_and_ignores_playoffs():
    raw = pd.DataFrame(holes('1') + holes('2', strokes=5) + holes('1', 2) + holes('1', 5))
    rounds, issues = aggregate_rounds(raw)
    r = rounds.query('round == 1')
    assert r.field_mean.tolist() == [81, 81]
    assert r.relative_score.tolist() == [-9, 9]
    assert set(rounds['round']) == {1, 2}
    assert 'non_regulation_round' in issues.reason.tolist()


def test_partial_conflicting_and_invalid_scores_never_enter_mean():
    raw = pd.DataFrame(holes('1') + holes('2')[:-1] + holes('3'))
    raw.loc[(raw.player_id == '3') & (raw.hole == 1), 'score'] = 0
    rounds, issues = aggregate_rounds(raw)
    assert rounds.player_id.tolist() == ['1']
    assert rounds.field_mean.tolist() == [72]
    assert set(issues.reason) == {'incomplete_round', 'invalid_score'}
    conflict = pd.DataFrame(holes() + [dict(holes()[0], score=6)])
    with pytest.raises(ValueError, match='conflicting'):
        aggregate_rounds(conflict)


def test_exact_duplicate_is_idempotent_and_totals_reconcile():
    raw = pd.DataFrame(holes() * 2)
    expected = pd.DataFrame([dict(event_id='e', player_id='1', round=1, expected_strokes=72)])
    rounds, _ = aggregate_rounds(raw, expected)
    assert rounds.strokes.tolist() == [72]
    expected['expected_strokes'] = 71
    rounds, issues = aggregate_rounds(raw, expected)
    assert rounds.empty
    assert issues.reason.tolist() == ['round_total_mismatch']


def test_missing_reference_round_and_event_are_reported_and_quarantined():
    raw=pd.DataFrame(holes('1',1)+holes('1',2)+[dict(h,event_id='other') for h in holes('1',1)])
    rounds,_=aggregate_rounds(raw)
    ref=pd.DataFrame([dict(event_id='e',player_id='1',round=1,holes_completed=18)])
    kept,coverage=reconcile_fields(rounds,ref,raw)
    assert list(zip(kept.event_id,kept['round']))==[('e',1)]
    missing=coverage[coverage.reason=='missing_reference_group']
    assert set(zip(missing.event_id,missing['round']))=={('e',2),('other',1)}
    assert not missing.verified.any()


def test_missing_complete_player_quarantines_entire_field():
    raw=pd.DataFrame(holes('1')+holes('2')[:-1])
    rounds,_=aggregate_rounds(raw)
    ref=pd.DataFrame([dict(event_id='e',player_id=p,round=1,holes_completed=18) for p in ['1','2']])
    kept,coverage=reconcile_fields(rounds,ref,raw)
    assert kept.empty
    assert coverage.missing_players.tolist()==['2']
    assert coverage.reason.tolist()==['player_set_mismatch']

