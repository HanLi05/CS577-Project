"""Targets, strictly past-only raw features, and grouped split manifests."""
import random
import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler


def feature_columns(windows=(5, 20)):
    return ['current_strokes', 'current_relative_score', 'tournament_mean_relative', 'tournament_strokes', 'completed_rounds'] + [f'history_{w}_{suffix}' for w in windows for suffix in ('mean','count','missing')]


def build_examples(matches, rounds, windows=(5,20)):
    result = []
    lookup = rounds.set_index(['event_id','player_id','round'])
    if not lookup.index.is_unique:
        raise ValueError('duplicate round keys')
    for row in matches.to_dict('records'):
        eid, pid, rnd = row['event_id'], row['player_id'], row['round']
        current, target = lookup.loc[(eid,pid,rnd)], lookup.loc[(eid,pid,rnd+1)]
        tournament = rounds.loc[(rounds.event_id == eid) & (rounds.player_id == pid) & (rounds['round'] <= rnd)]
        if set(tournament['round']) != set(range(1, rnd+1)):
            raise ValueError(f'incomplete tournament history: {eid}/{pid}/{rnd}')
        # End-date is a conservative availability bound, even for delayed rounds.
        history = rounds.loc[(rounds.player_id == pid) & (rounds.event_id != eid) & (rounds.end_date < row['interview_date'])].sort_values(['end_date','event_id','round'])
        out = dict(row, example_id=f'{eid}:{pid}:{rnd}', year=int(row['interview_date'][:4]),
                   target_round=rnd+1, y_reg=float(target.relative_score),
                   y_cls=int(target.relative_score < current.relative_score),
                   current_strokes=int(current.strokes), current_relative_score=float(current.relative_score),
                   tournament_mean_relative=float(tournament.relative_score.mean()),
                   tournament_strokes=int(tournament.strokes.sum()), completed_rounds=rnd)
        for window in windows:
            past = history.tail(window)
            out.update({f'history_{window}_mean': float(past.relative_score.mean()) if len(past) else np.nan,
                        f'history_{window}_count': len(past), f'history_{window}_missing': int(past.empty)})
        result.append(out)
    return pd.DataFrame(result, columns=list(matches.columns) + ['example_id','year','target_round','y_reg','y_cls'] + feature_columns(windows))


def split_groups(examples, seed=577, chronological=False):
    columns = ['example_id','event_id','year','split']
    if examples.empty:
        return pd.DataFrame(columns=columns)
    groups = examples.groupby(['event_id','year'], sort=True).agg(size=('example_id','size'), date=('interview_date','min')).reset_index()
    if len(groups) < 3:
        raise ValueError('At least three tournament-year groups are required for three splits')
    if chronological:
        groups = groups.sort_values(['date','event_id'])
        ordered = list(groups.index)
    else:
        ordered = list(groups.index)
        random.Random(seed).shuffle(ordered)
    # Choose two boundaries closest to 80/10/10 by examples, while keeping all sets nonempty.
    counts = [int(groups.loc[i,'size']) for i in ordered]
    cumulative = np.cumsum([0] + counts)
    n, total = len(counts), sum(counts)
    a, b = min(((a,b) for a in range(1,n-1) for b in range(a+1,n)),
               key=lambda pair: sum((v-target)**2 for v,target in zip(
                   [cumulative[pair[0]]/total,(cumulative[pair[1]]-cumulative[pair[0]])/total,(total-cumulative[pair[1]])/total], [.8,.1,.1])))
    mapping = {}
    for position, index in enumerate(ordered):
        group = groups.loc[index]
        mapping[(group.event_id,int(group.year))] = 'train' if position < a else 'validation' if position < b else 'test'
    result = examples[['example_id','event_id','year']].copy()
    result['split'] = [mapping[(r.event_id,int(r.year))] for r in result.itertuples()]
    return result.sort_values('example_id').reset_index(drop=True)


def fit_preprocessor(training_features, columns):
    """Caller passes only the training partition; preserve all-missing columns."""
    return make_pipeline(SimpleImputer(strategy='median', keep_empty_features=True), StandardScaler()).fit(training_features[columns])
