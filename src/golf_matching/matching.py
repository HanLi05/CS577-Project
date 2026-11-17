"""Automatic/manual decision tables and one interview-to-score result table."""
import csv
from datetime import date
from pathlib import Path

import pandas as pd

ALIGNMENT_COLUMNS = ['matching_method', 'verification_status', 'schedule_source',
                     'alignment_reason', 'alignment_hash']

COLUMNS = {
    'events': ['event_key', 'year', 'tournament', 'asap_url', 'suggested_event_id',
               'event_id', 'scoring_name', 'start_date', 'end_date', 'coverage',
               'collect', 'decision', 'source_hash'],
    'players': ['event_key', 'event_id', 'interview_name', 'suggested_player_id',
                'scoring_name', 'player_id', 'decision', 'reviewer', 'notes', 'source_hash'],
    'rounds': ['event_key', 'event_id', 'round', 'suggested_date', 'date_start', 'date_end',
               'decision', 'reviewer', 'evidence_url', 'notes', 'source_hash'],
    'interviews': ['interview_id', 'event_key', 'interview_name', 'interview_date',
                   'transcript_url', 'suggested_round', 'round', 'context',
                   'decision', 'reviewer', 'evidence', 'notes', 'source_hash'] + ALIGNMENT_COLUMNS,
}
KEYS = {'events': ['event_key'], 'players': ['event_key', 'interview_name'],
        'rounds': ['event_key', 'round'], 'interviews': ['interview_id']}
EDITABLE = {
    'events': ['event_id', 'collect', 'decision'],
    'players': ['player_id', 'decision', 'reviewer', 'notes'],
    'rounds': ['date_start', 'date_end', 'decision', 'reviewer', 'evidence_url', 'notes'],
    'interviews': ['round', 'context', 'decision', 'reviewer', 'evidence', 'notes'] + ALIGNMENT_COLUMNS,
}
MATCH_COLUMNS = ['interview_id', 'event_key', 'year', 'tournament', 'event_id',
                 'interview_name', 'player_id', 'player_name', 'interview_date',
                 'context', 'interview_stage', 'round', 'strokes', 'status', 'reason', 'transcript_url',
                 'matching_method', 'verification_status', 'schedule_source']


def index_rows(rows, keys):
    result = {}
    for row in rows:
        key = tuple(str(row.get(k, '')) for k in keys)
        if key in result:
            raise ValueError(f'Duplicate key {key} for {keys}')
        result[key] = row
    return result


def read_table(path, kind):
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        missing = set(COLUMNS[kind]) - set(reader.fieldnames or [])
        if kind == 'interviews':
            missing -= set(ALIGNMENT_COLUMNS)
        if missing:
            raise ValueError(f'{path}: missing columns {sorted(missing)}')
        rows = list(reader)
    if kind == 'interviews':
        for row in rows:
            # Migrate old metadata names without reusing stale automatic hashes.
            legacy_source = row.pop('calendar_source', '')
            row.setdefault('schedule_source', legacy_source)
            row.pop('calendar_hash', None)
            for column in ALIGNMENT_COLUMNS:
                row.setdefault(column, '')
    index_rows(rows, KEYS[kind])
    return rows


def sync_table(path, rows, kind):
    """Refresh suggestions, preserve choices, and flag changed source evidence."""
    path = Path(path)
    old = index_rows(read_table(path, kind), KEYS[kind])
    incoming = index_rows(rows, KEYS[kind])
    for key, row in incoming.items():
        row = {col: str(row.get(col, '')) for col in COLUMNS[kind]}
        row['decision'] = row['decision'] or 'pending'
        previous = old.get(key)
        if previous:
            if kind == 'events' and row['event_id'] != previous['event_id']:
                # Rediscovery must not replace the source evidence for a human-corrected ID
                # with evidence for the automated suggestion. prepare checks the chosen ID.
                for col in ('scoring_name', 'start_date', 'end_date', 'coverage', 'source_hash'):
                    row[col] = previous[col]
            row.update({col: previous[col] for col in EDITABLE[kind]})
            if 'source_hash' in row and row['source_hash'] != previous['source_hash']:
                row['decision'] = 'needs_review'
                if 'notes' in row:
                    row['notes'] = (previous['notes'] + ' Source evidence changed; review again.').strip()
        old[key] = row
    output_rows = list(old.values())
    if kind == 'events':
        output_rows.sort(key=lambda r: (int(r['year']), r['tournament'], r['event_key']))
        # Also migrate existing event tables that still have the removed columns.
        output_rows = [{col: r[col] for col in COLUMNS[kind]} for r in output_rows]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS[kind], lineterminator='\n')
        writer.writeheader()
        writer.writerows(output_rows)


def decision_reason(row, label):
    if not row:
        return f'{label}_not_reviewed'
    decision = row.get('decision', '')
    if decision == 'reject':
        return f'{label}_rejected'
    if decision != 'approve':
        return f'{label}_not_reviewed'
    if label != 'event' and (not row.get('reviewer', '').strip() or row['reviewer'] == 'AI-agent'):
        return f'{label}_missing_human_reviewer'
    return ''


def build_matches(interviews, scores, reviews):
    """One output per interview; no next-round, label, or prediction filters."""
    indices = {kind: index_rows(rows, KEYS[kind]) for kind, rows in reviews.items()}
    index_rows(interviews, ['interview_id'])
    score_rows = scores.to_dict('records')
    score_index = index_rows(score_rows, ['event_key', 'event_id', 'player_id', 'round'])
    roster_index = {(s['event_key'], s['event_id'], s['player_id']): s['player_name']
                    for s in score_rows}
    results = []
    for interview in interviews:
        key, iid = interview['event_key'], interview['interview_id']
        event = indices['events'].get((key,), {})
        player = indices['players'].get((key, interview['interview_name']), {})
        review = indices['interviews'].get((iid,), {})
        rnd = review.get('round', '')
        period = indices['rounds'].get((key, rnd), {})
        out = {col: interview.get(col, '') for col in MATCH_COLUMNS}
        out.update(player_id='', player_name='', round=rnd, context=review.get('context', ''),
                   interview_stage='',
                   strokes=None, status='pending', reason='')
        out.update({col: review.get(col, '') for col in
                    ('matching_method', 'verification_status', 'schedule_source')})
        if review.get('decision') == 'approve' and review.get('reviewer') not in (
                '', None, 'auto:date_alignment', 'auto:round_evidence'):
            out.update(matching_method='manual_review', verification_status='manual',
                       schedule_source=period.get('evidence_url', ''))
        # Explicit exclusions remain visible even when other reviews are pending.
        rejected = next((label for label, row in [('event', event), ('player', player),
                        ('interview', review)] if row.get('decision') == 'reject'), '')
        reason = f'{rejected}_rejected' if rejected else ''
        if rejected == 'interview' and review.get('reviewer') == 'auto:date_alignment':
            reason = review.get('alignment_reason') or reason
            out['status'] = 'excluded'
        reason = reason or decision_reason(event, 'event')
        if not reason and (event.get('event_id') != interview['event_id']
                           or player.get('event_id', interview['event_id']) != interview['event_id']):
            reason = 'event_changed'
        reason = reason or decision_reason(player, 'player')
        if not reason:
            name = roster_index.get((key, interview['event_id'], player['player_id']))
            if name is None:
                reason = 'unknown_player'
            else:
                out.update(player_id=player['player_id'], player_name=name)
        if not reason and review.get('decision') in ('pending', 'ambiguous') and review.get('alignment_reason'):
            reason = review['alignment_reason']
            out['status'] = review['decision']
        reason = reason or decision_reason(review, 'interview')
        if not reason and (review.get('event_key') != key
                           or review.get('source_hash') != interview['source_hash']):
            reason = 'source_changed'
        if not reason and interview['parse_status'] != 'ok':
            reason = interview['parse_status']
        if not reason:
            context = review.get('context')
            if context == 'pre_tournament':
                if rnd:
                    reason = 'unexpected_round'
                elif interview.get('explicit_round'):
                    reason = 'round_conflict'
                elif not review.get('evidence', '').strip():
                    reason = 'missing_interview_evidence'
                else:
                    try:
                        observed = date.fromisoformat(interview['interview_date'])
                        start = date.fromisoformat(event['start_date'])
                        if observed >= start:
                            reason = 'date_conflict'
                    except (ValueError, KeyError):
                        reason = 'invalid_event_dates'
                    if not reason:
                        out.update(status='matched', interview_stage='pre_round_1')
                        reason = 'matched'
            elif context == 'other':
                reason = 'unexpected_round' if rnd else context
                if not rnd:
                    out['status'] = 'identity_only'
            elif context not in ('post_round', 'post_round_assumed'):
                reason = 'context_not_reviewed'
            elif rnd not in ('1', '2', '3', '4'):
                reason = 'invalid_round'
            elif interview.get('explicit_round') and interview['explicit_round'] != rnd:
                reason = 'round_conflict'
            elif not review.get('evidence', '').strip():
                reason = 'missing_interview_evidence'
            else:
                reason = decision_reason(period, 'round')
                if not reason and period.get('event_id') != interview['event_id']:
                    reason = 'event_changed'
                if not reason and not period.get('evidence_url', '').strip():
                    reason = 'missing_round_evidence'
                if not reason:
                    try:
                        start, end, observed = (date.fromisoformat(d) for d in (
                            period['date_start'], period['date_end'], interview['interview_date']))
                        if not start <= observed <= end:
                            reason = 'date_conflict'
                    except (ValueError, KeyError):
                        reason = 'invalid_round_dates'
                if not reason:
                    score = score_index.get((key, interview['event_id'], player['player_id'], rnd))
                    if not score:
                        reason = 'missing_score'
                    elif score['complete'] is not True or pd.isna(score['strokes']):
                        reason = 'incomplete_round'
                    else:
                        out.update(strokes=score['strokes'], status='matched',
                                   interview_stage=f'post_round_{rnd}')
                        reason = 'matched'
        if reason.endswith('_rejected'):
            out['status'] = 'excluded'
        out['reason'] = reason
        results.append(out)
    return pd.DataFrame(results, columns=MATCH_COLUMNS)
