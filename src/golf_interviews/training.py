"""A small statistics-only regression check, not a test of interview usefulness."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from .dataset import feature_columns

ALPHA = 1.0  # Chosen before evaluation; no validation/test-driven tuning.
PARTITIONS = ('train', 'validation', 'test')


def run_experiment(examples, splits, features, windows=(5, 20)):
    """Validate the saved split, fit on train only, and return predictions/metrics/model."""
    # An explicit allowlist keeps targets and metadata out of the model inputs.
    if not features or len(set(features)) != len(features) or not set(features) <= set(feature_columns(windows)):
        raise ValueError('Features must be unique approved statistical inputs')
    if examples.example_id.duplicated().any() or splits.example_id.duplicated().any():
        raise ValueError('Example IDs must be unique')
    if set(examples.example_id) != set(splits.example_id):
        raise ValueError('Split manifest must cover exactly the dataset')
    keys = ['example_id', 'event_id', 'year']
    data = examples.merge(splits[keys + ['split']], on=keys, how='left', validate='one_to_one')
    if data['split'].isna().any() or set(data['split']) != set(PARTITIONS):
        raise ValueError('Split identities must match, with nonempty train/validation/test')
    if data.groupby(['event_id', 'year'])['split'].nunique().max() != 1:
        raise ValueError('A tournament-year cannot cross split boundaries')
    dates = pd.to_datetime(data.interview_date, errors='raise')
    if dates.isna().any():
        raise ValueError('Missing interview dates')
    for earlier, later in zip(PARTITIONS, PARTITIONS[1:]):
        if dates[data['split'] == earlier].max() >= dates[data['split'] == later].min():
            raise ValueError('Expected strictly chronological tournament partitions')
    if not np.isfinite(data.y_reg.to_numpy(dtype=float)).all():
        raise ValueError('Regression targets must be finite')
    if not np.isfinite(data.current_relative_score.to_numpy(dtype=float)).all():
        raise ValueError('Baseline requires finite current-round scores')
    if np.isinf(data[features].to_numpy(dtype=float)).any():
        raise ValueError('Features may be missing, but not infinite')
    data = data.sort_values('example_id').reset_index(drop=True)

    # Fit all three steps on training rows only. Held-out rows only use transform
    # and predict; they cannot affect imputation, scaling, or Ridge coefficients.
    model = make_pipeline(
        SimpleImputer(strategy='median', keep_empty_features=True),
        StandardScaler(),
        Ridge(alpha=ALPHA, solver='svd'),
    )
    train = data.loc[data['split'] == 'train']
    model.fit(train[features], train.y_reg)

    predictions = data[['example_id', 'event_id', 'year', 'player_id', 'player_name',
                        'round', 'target_round', 'interview_date', 'split']].copy()
    predictions['actual_relative_score'] = data.y_reg
    # Persistence baseline: predict the same relative performance as this round.
    predictions['baseline_prediction'] = data.current_relative_score
    predictions['ridge_prediction'] = model.predict(data[features])
    scores = []
    for name, column in [('current_round_baseline', 'baseline_prediction'), ('ridge', 'ridge_prediction')]:
        predictions[f'{name}_error'] = predictions[column] - predictions.actual_relative_score
        for partition in PARTITIONS:
            subset = predictions.loc[predictions['split'] == partition]
            scores.append(dict(model=name, split=partition, n=len(subset),
                               mae=float(mean_absolute_error(subset.actual_relative_score, subset[column])),
                               rmse=float(np.sqrt(mean_squared_error(subset.actual_relative_score, subset[column])))))
    return predictions, pd.DataFrame(scores), model


def train_pilot(config, root=Path('.')):
    """Read existing prepared files; write predictions and a short experiment report."""
    root = Path(root)
    directory = root / 'data/processed'
    examples_path = directory / 'examples.parquet'
    splits_path = directory / 'splits_chronological.parquet'
    features_path = directory / 'feature_columns.json'
    examples = pd.read_parquet(examples_path)
    splits = pd.read_parquet(splits_path)
    features = json.loads(features_path.read_text())
    predictions, metrics, model = run_experiment(examples, splits, features, config['history_windows'])
    output = root / 'reports/pilot_regression'
    output.mkdir(parents=True, exist_ok=True)
    predictions.to_csv(output / 'predictions.csv', index=False)
    metrics.to_csv(output / 'metrics.csv', index=False)

    # Keep enough provenance to repeat this specific experiment without storing
    # a serialized model: inputs, code, dependency lock, and fixed settings.
    inputs = [examples_path, splits_path, features_path, Path(__file__)]
    if (root / 'uv.lock').exists():
        inputs.append(root / 'uv.lock')
    metadata = dict(alpha=ALPHA, solver='svd', tuning='none', refit_on_validation=False,
                    features=features, sklearn_version=sklearn.__version__,
                    sha256={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},
                    training_imputation_medians=model.named_steps['simpleimputer'].statistics_.tolist(),
                    training_scaler_means=model.named_steps['standardscaler'].mean_.tolist())
    (output / 'experiment.json').write_text(json.dumps(metadata, indent=2) + '\n')

    names = {str(e['event_id']): e['name'] for e in config['events']}
    lines = ['# Statistics-only pilot regression', '',
             'This experiment checks that prepared data can flow through training and evaluation. It does not test whether interviews improve predictions.', '',
             '## Setup', '',
             '- Target: next-round strokes relative to that round’s field mean (lower is better).',
             '- Baseline: predict the golfer’s current-round field-relative score again.',
             '- Ridge: median imputation, standard scaling, then Ridge regression with fixed alpha=1 and SVD solver.',
             '- Fit on training rows only. No tuning or refitting on validation/test data. No interview text, embeddings, or classification model.', '',
             '| Split | Tournament | Examples |', '| --- | --- | ---: |']
    for partition in PARTITIONS:
        group = predictions.loc[predictions['split'] == partition]
        events = ', '.join(names.get(str(e), str(e)) for e in group.event_id.unique())
        lines.append(f'| {partition} | {events} | {len(group)} |')
    lines += ['', '## Errors (strokes; lower is better)', '',
              '| Split | Model | MAE | RMSE |', '| --- | --- | ---: | ---: |']
    for row in metrics.itertuples():
        lines.append(f'| {row.split} | {row.model} | {row.mae:.3f} | {row.rmse:.3f} |')
    test = metrics.loc[metrics['split'] == 'test'].set_index('model')
    delta = test.loc['ridge', 'mae'] - test.loc['current_round_baseline', 'mae']
    comparison = 'lower' if delta < 0 else 'higher' if delta > 0 else 'equal'
    lines += ['', f'On this test event, Ridge MAE is {abs(delta):.3f} strokes {comparison} than the baseline.' if delta != 0 else 'On this test event, Ridge and baseline MAE are equal.', '',
              '## What this establishes', '',
              'The numerical training/evaluation path runs end to end, with per-example predictions saved in `predictions.csv`. Positive prediction errors mean the predicted score was worse (higher) than the actual score.', '',
              '## Limits and next steps', '',
              '- This is a tiny, selected sample from only three tournaments. Training errors are diagnostics, not evidence of generalization; validation/test errors each represent one event.',
              '- The training tournament contributes only post-round-3 interviews, while later events include other rounds. This distribution difference further limits interpretation.',
              '- Interviewed golfers tend to have just played well. Regression toward average performance can make the current-round baseline weak; beating it would not establish language value.',
              '- Review matching and collect more tournaments before drawing research conclusions. Then compare statistics-only, language-only, and combined models on fixed splits.',
              '- Human validation of forward-looking text labels remains pending. This experiment does not consume those labels.']
    (output / 'results.md').write_text('\n'.join(lines) + '\n')
    print(metrics.to_string(index=False, float_format=lambda x: f'{x:.3f}'))
    print(f'Results saved to {output / "results.md"}')
    return predictions, metrics
