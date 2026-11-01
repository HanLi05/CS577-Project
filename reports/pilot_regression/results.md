# Statistics-only pilot regression

This experiment checks that prepared data can flow through training and evaluation. It does not test whether interviews improve predictions.

## Setup

- Target: next-round strokes relative to that round’s field mean (lower is better).
- Baseline: predict the golfer’s current-round field-relative score again.
- Ridge: median imputation, standard scaling, then Ridge regression with fixed alpha=1 and SVD solver.
- Fit on training rows only. No tuning or refitting on validation/test data. No interview text, embeddings, or classification model.

| Split | Tournament | Examples |
| --- | --- | ---: |
| train | THE PLAYERS Championship | 12 |
| validation | Charles Schwab Challenge | 14 |
| test | the Memorial Tournament pres. by Workday | 24 |

## Errors (strokes; lower is better)

| Split | Model | MAE | RMSE |
| --- | --- | ---: | ---: |
| train | current_round_baseline | 4.263 | 5.770 |
| validation | current_round_baseline | 4.932 | 5.439 |
| test | current_round_baseline | 3.543 | 4.511 |
| train | ridge | 1.952 | 2.485 |
| validation | ridge | 11.599 | 13.247 |
| test | ridge | 13.133 | 14.522 |

On this test event, Ridge MAE is 9.590 strokes higher than the baseline.

## What this establishes

The numerical training/evaluation path runs end to end, with per-example predictions saved in `predictions.csv`. Positive prediction errors mean the predicted score was worse (higher) than the actual score.

## Limits and next steps

- This is a tiny, selected sample from only three tournaments. Training errors are diagnostics, not evidence of generalization; validation/test errors each represent one event.
- The training tournament contributes only post-round-3 interviews, while later events include other rounds. This distribution difference further limits interpretation.
- Interviewed golfers tend to have just played well. Regression toward average performance can make the current-round baseline weak; beating it would not establish language value.
- Review matching and collect more tournaments before drawing research conclusions. Then compare statistics-only, language-only, and combined models on fixed splits.
- Human validation of forward-looking text labels remains pending. This experiment does not consume those labels.
