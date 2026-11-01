import pandas as pd
from golf_interviews.matching import match_interviews, verify_tee_dates


def fixture():
    interviews = pd.DataFrame([dict(interview_id='i', event_id='e', player_name='José Doe',
                                    interview_date='2024-05-23', explicit_round=None, content_hash='h')])
    rounds = pd.DataFrame([dict(event_id='e', player_id='1', round=r) for r in (1, 2)])
    aliases = pd.DataFrame([dict(event_id='e', name='Jose Doe', player_id='1')])
    reviews = pd.DataFrame([dict(interview_id='i', event_id='e', round=1, post_round=True, evidence='Reviewed completed-round discussion', content_hash='h')])
    timing = pd.DataFrame([dict(event_id='e', round=1, round_date='2024-05-23', next_round_date='2024-05-24', verified=True, evidence_url='https://example.org/round-notes')])
    return interviews, rounds, aliases, reviews, timing


def test_reviewed_identity_and_round_required():
    args = fixture()
    matched, ledger = match_interviews(*args)
    assert matched.player_id.tolist() == ['1']
    assert ledger.status.tolist() == ['accepted']
    args[3].loc[0, 'content_hash'] = 'outdated'
    assert match_interviews(*args)[0].empty


def test_ambiguous_name_and_next_round_are_not_guessed():
    i, r, a, v, t = fixture()
    a = pd.concat([a, pd.DataFrame([dict(event_id='e', name='José Doe', player_id='2')])])
    assert match_interviews(i,r,a,v,t)[1].reason.tolist() == ['ambiguous_player']
    assert match_interviews(i,r.iloc[:1],a.iloc[:1],v,t)[1].reason.tolist() == ['missing_next_round']


def test_delay_and_conflicting_round_are_excluded():
    i,r,a,v,t = fixture()
    t.loc[0,'verified'] = False
    assert match_interviews(i,r,a,v,t)[1].reason.tolist() == ['unverified_timing']
    t.loc[0,'verified'] = True
    i.loc[0,'explicit_round'] = 2
    assert match_interviews(i,r,a,v,t)[1].reason.tolist() == ['round_conflict']


def test_duplicate_repost_deduplicates_but_distinct_unordered_interviews_exclude():
    i,r,a,v,t = fixture()
    i = pd.concat([i, i.assign(interview_id='j')], ignore_index=True)
    v = pd.concat([v, v.assign(interview_id='j')], ignore_index=True)
    m,l = match_interviews(i,r,a,v,t)
    assert len(m) == 1
    assert set(l.reason) == {'matched', 'duplicate_content'}
    i.loc[1,'content_hash'] = 'other'
    v.loc[1,'content_hash'] = 'other'
    m,l = match_interviews(i,r,a,v,t)
    assert m.empty
    assert set(l.reason) == {'ambiguous_interview_order'}


def test_tee_dates_validate_person_and_both_rounds_without_joining_id_namespaces():
    i,r,a,v,t=fixture()
    m,_=match_interviews(i,r,a,v,t)
    tees=pd.DataFrame([dict(tournament_id='pga-e',player_id='different-id',player_name='Jose Doe',round=r,tee_time=pd.Timestamp(f'2024-05-{22+r}T12:00:00Z'),timezone='UTC') for r in (1,2)])
    config={'events':[dict(event_id='e',tee_event_id='pga-e')]}
    good,bad=verify_tee_dates(m,tees,config)
    assert len(good)==1 and not bad
    tees.loc[1,'tee_time']=pd.Timestamp('2024-05-23T18:00:00Z')
    good,bad=verify_tee_dates(m,tees,config)
    assert good.empty and bad[0]['reason']=='tee_timing_conflict'


def test_missing_earlier_tournament_round_is_logged_before_feature_build():
    i,r,a,v,t=fixture()
    r=pd.DataFrame([dict(event_id='e',player_id='1',round=n) for n in (2,3,4)])
    v['round']=3
    t['round']=3
    matched,ledger=match_interviews(i,r,a,v,t)
    assert matched.empty
    assert ledger.reason.tolist()==['incomplete_tournament_history']
