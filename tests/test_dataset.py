import pandas as pd
import numpy as np
from golf_interviews.dataset import build_examples, split_groups, fit_preprocessor, feature_columns


def frames():
    matches = pd.DataFrame([dict(event_id='e', player_id='1', round=1, interview_id='i', interview_date='2024-05-23')])
    rounds = pd.DataFrame([
        dict(event_id='old', player_id='1', round=1, strokes=70, relative_score=-2, end_date='2024-05-20'),
        dict(event_id='e', player_id='1', round=1, strokes=72, relative_score=1, end_date='2024-05-26'),
        dict(event_id='e', player_id='1', round=2, strokes=71, relative_score=-1, end_date='2024-05-26'),
        dict(event_id='future', player_id='1', round=1, strokes=60, relative_score=-10, end_date='2024-06-01')])
    return matches, rounds


def test_labels_history_and_future_invariance():
    m,r=frames()
    x=build_examples(m,r,[5,20])
    assert x.y_reg.tolist() == [-1]
    assert x.y_cls.tolist() == [1]
    assert x.history_5_mean.tolist() == [-2]
    assert x.history_5_count.tolist() == [1]
    r.loc[r.event_id=='future','relative_score'] = 100
    r.loc[(r.event_id=='e') & (r['round']==2),'relative_score'] = 1
    y=build_examples(m,r,[5,20])
    assert y.y_cls.tolist() == [0]  # ties do not improve
    pd.testing.assert_frame_equal(x[feature_columns([5,20])], y[feature_columns([5,20])])


def test_cold_start_and_same_day_history_excluded():
    m,r=frames()
    r.loc[r.event_id=='old','end_date'] = '2024-05-23'
    x=build_examples(m,r,[5])
    assert x.history_5_count.tolist() == [0]
    assert x.history_5_mean.isna().all()


def test_split_group_integrity_determinism_and_chronology():
    x=pd.DataFrame([dict(event_id=f'e{g:02}', year=2024, example_id=f'{g}-{i}', interview_date=f'2024-05-{g+1:02}') for g in range(10) for i in range(3)])
    s=split_groups(x,577)
    assert s.groupby('event_id').split.nunique().max() == 1
    assert s.split.value_counts().to_dict() == {'train':24,'validation':3,'test':3}
    pd.testing.assert_frame_equal(s,split_groups(x.sample(frac=1,random_state=9),577))
    c=split_groups(x,577,chronological=True)
    assert set(c.loc[c.split=='test','event_id']) == {'e09'}


def test_preprocessing_fit_never_uses_heldout_rows():
    train=pd.DataFrame({'x':[1.,3.], 'empty':[np.nan,np.nan]})
    prep=fit_preprocessor(train,['x','empty'])
    before=prep.transform(train)
    assert np.isfinite(before).all()
    prep.transform(pd.DataFrame({'x':[1e9], 'empty':[99.]}))
    np.testing.assert_equal(before,prep.transform(train))
    np.testing.assert_allclose(before[:,0],[-1,1])
