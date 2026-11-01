"""Summaries separate verified checks from annotation still awaiting humans."""
import json
from pathlib import Path
import pandas as pd
from .text import review_sample
from .dataset import feature_columns


def write_audit(root, examples, interviews, segments, ledger, coverage, rounds, config):
    root = Path(root)
    reports = root/'reports'; reports.mkdir(exist_ok=True)
    review_sample(segments, 100, config['seed']).to_csv(reports/'review_segments.csv', index=False)
    sample = examples.sort_values('example_id').groupby(['event_id','round'], group_keys=False).head(5) if len(examples) else examples
    sample.to_json(reports/'review_matches.jsonl', orient='records', lines=True, force_ascii=False)
    cols = feature_columns(config['history_windows'])
    lines = ['# Pilot data quality', '',
             f'- Parsed transcripts: {len(interviews)}; parsed Q&A segments: {len(segments)}.',
             f'- Accepted examples: {len(examples)} across {examples.event_id.nunique() if len(examples) else 0} events.',
             '- Match review was performed by the implementing AI agent, not a human annotator.',
             '- Forward-looking rules are exploratory. Human annotation is pending; no precision/recall claim is made.',
             '- Date-only transcript metadata supports a retrospective end-of-day cutoff, not a verified live publication time.',
             '- Raw snapshots and transcript-derived outputs are local and ignored by Git. No redistribution rights are asserted.', '',
             '## Exclusions and review queue', '', '```', ledger.groupby(['status','reason']).size().to_string(), '```', '',
             '## Full-field reconciliation', '', '```', coverage.to_string(index=False), '```', '',
             'Field means use all validated complete rounds, including players later cut or withdrawn. An event-round with a missing or mismatched complete player-round is quarantined.', '']
    if len(examples):
        lines += ['## Dataset composition', '', '```', examples.groupby(['event_id','round']).size().to_string(), '```', '',
                  f'Class counts: {examples.y_cls.value_counts().sort_index().to_dict()}.',
                  f'Unique interviewed players: {examples.player_id.nunique()}; largest player share: {examples.player_id.value_counts(normalize=True).max():.1%}.',
                  f'Empty forward-looking subsets: {int(examples.forward_empty.sum())}.',
                  f'Answer character lengths (min/median/max): {examples.answers_only.str.len().min()} / {examples.answers_only.str.len().median():.0f} / {examples.answers_only.str.len().max()}.', '',
                  'Missing feature counts:', '```', examples[cols].isna().sum().to_string(), '```', '',
                  '## Selection bias and limits', '',
                  'Interviews are not a random sample of the field. Compare the following current-round averages descriptively; this is not an estimate of causal selection effects.', '']
        for event in config['events']:
            eid=event['event_id']; selected=examples.loc[examples.event_id==eid]
            population=rounds.loc[(rounds.event_id==eid)&rounds['round'].isin(selected['round'].unique())]
            lines += [f"- {event['name']}: interviewed mean relative score {selected.current_relative_score.mean():.3f}; all-player mean over represented rounds {population.relative_score.mean():.3f}; {len(selected)}/{len(population)} observed round-interviews."]
        lines += ['', 'Only three pilot event groups are available. Splits exercise the machinery and cannot approximate 80/10/10 closely or support reliable model comparisons.',
                  'Historical features use validated single-course, ordinary individual stroke-play events available in the collected season. History before the season boundary is missing, not zero.',
                  'Random grouped splits are retrospective. The separate chronological manifest is the appropriate starting point for a forecasting robustness analysis.',
                  'This preparation report does not evaluate models. The separate optional statistics-only experiment writes results to `reports/pilot_regression/results.md`; no embeddings are generated here.']
    (reports/'data_quality.md').write_text('\n'.join(lines)+'\n')
