import pandas as pd
from golf_matching.candidates import suggest, round_records


def test_unique_name_with_accents_and_date_is_only_a_suggestion():
    roster=pd.DataFrame([dict(player_name='J.T. Poston',player_id='1')])
    pid,rnd,reason=suggest('JT Poston','2024-05-24',roster,{1:'2024-05-23',2:'2024-05-24'})
    assert (pid,rnd)==('1','2')
    assert 'review' in reason
    assert suggest('unknown','2024-05-24',roster,{2:'2024-05-24'})[0]==''
    roster=pd.concat([roster,roster.assign(player_id='2')])
    assert suggest('JT Poston','2024-05-24',roster,{2:'2024-05-24'})[0]==''


def test_partial_rounds_and_duplicate_holes_are_not_complete():
    rows=[dict(player_id='p',player_name='A',round=1,hole=h,score=4,par=4) for h in range(1,19)]
    assert round_records(pd.DataFrame(rows),'e').iloc[0].strokes==72
    assert not round_records(pd.DataFrame(rows[:-1]),'e').iloc[0].complete
    assert not round_records(pd.DataFrame(rows+[dict(rows[0],score=5)]),'e').iloc[0].complete
