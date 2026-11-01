import numpy as np
import pandas as pd
import pytest

from golf_interviews.training import run_experiment


def fixture():
    rows = []
    for event, split, date in [('a', 'train', '2024-03-16'), ('b', 'validation', '2024-05-23'), ('c', 'test', '2024-06-06')]:
        for i in range(2):
            rows.append(dict(example_id=f'{event}{i}', event_id=event, year=2024,
                             player_name=f'Player {i}', player_id=str(i), round=1,
                             target_round=2, interview_date=date,
                             current_relative_score=float(i), y_reg=2.0*i,
                             history_5_mean=np.nan if i == 0 else 2.0))
    data = pd.DataFrame(rows)
    splits = data[['example_id', 'event_id', 'year']].copy()
    splits['split'] = ['train', 'train', 'validation', 'validation', 'test', 'test']
    return data, splits


def test_baseline_metrics_and_training_only_preprocessing():
    data, splits = fixture()
    predictions, metrics, model = run_experiment(data, splits, ['current_relative_score', 'history_5_mean'])
    baseline = metrics[(metrics.model == 'current_round_baseline') & (metrics.split == 'test')].iloc[0]
    assert baseline.mae == .5
    assert baseline.rmse == pytest.approx(np.sqrt(.5))
    assert np.isfinite(predictions.ridge_prediction).all()
    assert model.named_steps['simpleimputer'].statistics_.tolist() == [.5, 2.]
    assert model.named_steps['standardscaler'].mean_.tolist() == [.5, 2.]


def test_heldout_targets_do_not_change_predictions_and_future_features_do_not_change_fit():
    data, splits = fixture()
    before, _, model = run_experiment(data, splits, ['current_relative_score'])
    data.loc[data.event_id != 'a', 'y_reg'] = 1000.
    after, _, _ = run_experiment(data, splits, ['current_relative_score'])
    pd.testing.assert_series_equal(before.ridge_prediction, after.ridge_prediction)
    data.loc[data.event_id != 'a', 'current_relative_score'] = 1e9
    _, _, changed = run_experiment(data, splits, ['current_relative_score'])
    np.testing.assert_equal(model.named_steps['ridge'].coef_, changed.named_steps['ridge'].coef_)
    np.testing.assert_equal(model.named_steps['standardscaler'].mean_, changed.named_steps['standardscaler'].mean_)


@pytest.mark.parametrize('problem', ['missing', 'duplicate', 'identity', 'group_overlap', 'reverse_dates', 'target_feature'])
def test_rejects_invalid_splits_and_feature_leakage(problem):
    data, splits = fixture()
    features = ['current_relative_score']
    if problem == 'missing': splits = splits.iloc[:-1]
    if problem == 'duplicate': splits = pd.concat([splits, splits.iloc[:1]])
    if problem == 'identity': splits.loc[0, 'event_id'] = 'wrong'
    if problem == 'group_overlap': splits.loc[0, 'split'] = 'test'
    if problem == 'reverse_dates': data.loc[data.event_id == 'a', 'interview_date'] = '2025-01-01'
    if problem == 'target_feature': features = ['y_reg']
    with pytest.raises(ValueError):
        run_experiment(data, splits, features)


def test_training_command_saves_reproducible_outputs_without_changing_inputs(tmp_path, monkeypatch):
    import hashlib
    import json
    import yaml
    from golf_interviews.cli import main

    data, splits = fixture()
    directory = tmp_path / 'data/processed'
    directory.mkdir(parents=True)
    data.to_parquet(directory / 'examples.parquet', index=False)
    splits.to_parquet(directory / 'splits_chronological.parquet', index=False)
    (directory / 'feature_columns.json').write_text(json.dumps(['current_relative_score', 'history_5_mean']))
    config = dict(history_windows=[5, 20], events=[dict(event_id=e, name=e) for e in 'abc'])
    (tmp_path / 'settings.yaml').write_text(yaml.safe_dump(config))
    original = {p.name: p.read_bytes() for p in directory.iterdir()}
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr('sys.argv', ['golf-data', 'train', '--config', 'settings.yaml'])
    main()
    output = tmp_path / 'reports/pilot_regression'
    first = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
    assert set(first) == {'predictions.csv', 'metrics.csv', 'experiment.json', 'results.md'}
    assert len(pd.read_csv(output / 'predictions.csv')) == 6
    assert len(pd.read_csv(output / 'metrics.csv')) == 6
    main()
    assert first == {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in output.iterdir()}
    assert original == {p.name: p.read_bytes() for p in directory.iterdir()}
