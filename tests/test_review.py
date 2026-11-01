import pandas as pd
import pytest
from golf_matching.review import sync_review, export_reviews


def candidates():
    return pd.DataFrame([dict(interview_id='asap:1', transcript_url='https://example.org/1',
        transcript_player='Jane Doe', tournament='Example 2024', year='2024',
        event_id='e', interview_date='2024-05-23', suggested_player_id='p',
        suggested_round='1', reason='unique name; date suggestion', source_fingerprint='abc')])


def scores():
    return pd.DataFrame([dict(event_id='e', player_id='p', player_name='Jane Doe', round=str(r), strokes=72, complete=True) for r in [1,2]])


def approve(path):
    r=pd.read_csv(path,dtype=str,keep_default_na=False)
    r.loc[0,['decision','post_round','timing','reviewer']]=['approve','yes','verified','Han']
    r.to_csv(path,index=False)


def test_reviews_survive_regeneration_and_stale_evidence_blocks_export(tmp_path):
    path=tmp_path/'review.csv'; c=candidates()
    sync_review(c,path);approve(path)
    before=path.read_bytes()
    sync_review(c,path)
    assert path.read_bytes()==before
    accepted,status=export_reviews(c,path,scores(),{1:'2024-05-23',2:'2024-05-24'})
    assert len(accepted)==1 and status.eligibility.tolist()==['eligible']
    c.loc[0,'source_fingerprint']='changed'
    sync_review(c,path)
    assert path.read_bytes()==before
    accepted,status=export_reviews(c,path,scores(),{1:'2024-05-23',2:'2024-05-24'})
    assert accepted.empty and status.reason.tolist()==['stale_source']


def test_pending_never_approved_and_corrections_checked(tmp_path):
    path=tmp_path/'review.csv';c=candidates();sync_review(c,path)
    assert export_reviews(c,path,scores(),{})[0].empty
    approve(path)
    r=pd.read_csv(path,dtype=str,keep_default_na=False);r.loc[0,'player_id']='wrong';r.to_csv(path,index=False)
    accepted,status=export_reviews(c,path,scores(),{})
    assert accepted.empty and status.reason.tolist()==['unknown_player_round']


def test_correct_round_and_missing_next_score_are_separate_from_identity(tmp_path):
    path=tmp_path/'review.csv';c=candidates();sync_review(c,path);approve(path)
    r=pd.read_csv(path,dtype=str,keep_default_na=False)
    r.loc[0,['round','timing']]=['2','uncertain'];r.to_csv(path,index=False)
    accepted,status=export_reviews(c,path,scores(),{2:'2024-05-23',3:'2024-05-24'})
    assert accepted['round'].tolist()==[2]
    assert status.eligibility.tolist()==['missing_next_round']


def test_duplicate_reviews_fail_and_new_year_does_not_erase_old_decisions(tmp_path):
    path=tmp_path/'review.csv';c=candidates();sync_review(c,path);approve(path)
    later=c.assign(interview_id='asap:2',year='2025',event_id='e2025')
    sync_review(later,path)
    r=pd.read_csv(path,dtype=str,keep_default_na=False)
    assert len(r)==2 and r.loc[0,'decision']=='approve' and r.loc[1,'decision']=='pending'
    pd.concat([r,r.iloc[:1]]).to_csv(path,index=False)
    with pytest.raises(ValueError,match='Duplicate'):
        export_reviews(c,path,scores(),{})
