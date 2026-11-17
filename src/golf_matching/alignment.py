"""Assign pre-tournament or post-round interviews using dates and source metadata."""
import csv
import hashlib
import json
from collections import defaultdict
from datetime import date
from pathlib import Path

from .matching import COLUMNS, build_matches, read_table

AUTO = 'auto:date_alignment'
AUTOMATIC = {'', AUTO, 'auto:round_evidence'}
ALIGNMENT_POLICY = 'date_alignment:interview_stages:v5'


def alignment_state(root, events):
    """Bind automatic decisions to policy, schedules, prepared inputs, and identities."""
    schedules = sorted((r['event_key'], r['event_id'], r['start_date'], r['end_date'])
                       for r in events if r.get('collect') == 'yes')
    snapshot = json.loads((Path(root) / 'data/raw/prepared.json').read_text())
    players = sorted(tuple(row.get(k, '') for k in (
        'event_key', 'event_id', 'interview_name', 'player_id', 'decision'))
        for row in read_table(Path(root) / 'data/decisions/players.csv', 'players'))
    digest = hashlib.sha256(json.dumps(
        [ALIGNMENT_POLICY, schedules, snapshot['files'], players], sort_keys=True).encode()).hexdigest()
    return digest


def assign_round(interview, scores, event):
    """Match by dates and explicit headings; do not interpret Q&A wording."""
    result = dict(round='', reason='', context='', evidence='', matching_method='',
                  verification_status='', schedule_source='')

    def fail(reason):
        return dict(result, round='', reason=reason)

    if interview['parse_status'] != 'ok':
        return fail(interview['parse_status'])
    try:
        observed = date.fromisoformat(interview['interview_date'])
        start = date.fromisoformat(event['start_date'])
    except (KeyError, ValueError):
        return fail('invalid_event_dates')
    if observed < start:
        result.update(context='pre_tournament', matching_method='scheduled_date',
                      verification_status='schedule_assumed',
                      schedule_source=event.get('asap_url') or 'schedule:start_date',
                      evidence=f'Interview date {observed.isoformat()} precedes scheduled start '
                               f'{start.isoformat()}; no completed tournament round.')
        if interview.get('explicit_round'):
            return fail('round_date_conflict')
        return result
    result.update(context='post_round_assumed', evidence=(
        'Post-round timing assumed from interview date; Q&A wording is not used for matching.'))
    rnd = str(1 + (observed - start).days)
    if rnd not in ('1', '2', '3', '4'):
        return fail('no_round_on_date')
    result.update(matching_method='scheduled_date', verification_status='schedule_assumed',
                  schedule_source=event.get('asap_url') or 'schedule:start_date')
    explicit = interview.get('explicit_round', '')
    if explicit and rnd != explicit:
        return fail('round_date_conflict')
    score = scores.get(rnd, {})
    if score.get('complete') is not True or score.get('strokes') is None:
        return fail('incomplete_round')
    if explicit:
        result['matching_method'] += '+transcript_heading'
        result['evidence'] += f' Explicit round {explicit} transcript heading agrees.'
    result.update(round=rnd, evidence=(
        f"Date {observed.isoformat()} maps to round {rnd} "
        f"({result['verification_status']}). {result['evidence']}"))
    return result


def infer_round(interview, scores, event):
    """Compatibility wrapper returning round, evidence, and reason."""
    result = assign_round(interview, scores, event)
    return result['round'], result['evidence'], result['reason']


def align(root):
    """Record automatic decisions; preserve manual overrides and build the dataset."""
    from .preprocessing import prepared_inputs, build

    root = Path(root)
    interviews, scores, reviews = prepared_inputs(root)
    alignment_hash = alignment_state(root, reviews['events'])
    events = {r['event_key']: r for r in reviews['events']}
    players = {(r['event_key'], r['interview_name']): r for r in reviews['players']}
    periods = {(r['event_key'], r['round']): r for r in reviews['rounds']}
    decisions = {r['interview_id']: r for r in reviews['interviews']}
    # Keep dates that already support a valid human-approved match. Automatic
    # reruns must not narrow those dates just because the interview is now manual.
    manual_dates = defaultdict(set)
    manual_interviews = [r for r in interviews
                         if decisions[r['interview_id']]['reviewer'] not in AUTOMATIC
                         and decisions[r['interview_id']]['decision'] == 'approve']
    if manual_interviews:
        for row in build_matches(manual_interviews, scores, reviews).to_dict('records'):
            if row['status'] == 'matched' and row['round']:
                manual_dates[(row['event_key'], row['round'])].add(row['interview_date'])
    scoring = defaultdict(dict)
    for s in scores.to_dict('records'):
        scoring[(s['event_key'], s['event_id'], s['player_id'])][s['round']] = s
    candidates = defaultdict(list)

    def record(row, result):
        reason = result['reason']
        excluded = {'event_not_approved', 'player_not_included',
                    'no_player_answers', 'event_conflict', 'missing_header', 'invalid_date'}
        ambiguous = {'round_date_conflict'}
        decision = ('approve' if not reason else 'reject' if reason in excluded else
                    'ambiguous' if reason in ambiguous else 'pending')
        row.update({k: result.get(k, '') for k in ('round', 'context', 'evidence',
                    'matching_method', 'verification_status', 'schedule_source')})
        row.update(decision=decision, reviewer=AUTO, alignment_reason=reason,
                   alignment_hash=alignment_hash)
        if reason:
            row['evidence'] = f"{reason}: {result.get('evidence', '')}".rstrip(': ')

    for interview in interviews:
        row = decisions[interview['interview_id']]
        # A named human can retain or recover an interview through manual review.
        if row['reviewer'] and row['reviewer'] not in AUTOMATIC:
            continue
        if row['decision'] in ('approve', 'reject') and row['reviewer'] not in AUTOMATIC - {''}:
            continue
        event = events[interview['event_key']]
        player = players[(interview['event_key'], interview['interview_name'])]
        if event['decision'] != 'approve' or event['event_id'] != interview['event_id']:
            record(row, dict(reason='event_not_approved'))
            continue
        if player['decision'] != 'approve' or player['event_id'] != interview['event_id']:
            record(row, dict(reason='player_not_included'))
            continue
        roster = scoring[(interview['event_key'], interview['event_id'], player['player_id'])]
        result = assign_round(interview, roster, event)
        if result['reason'] or result['context'] == 'pre_tournament':
            record(row, result)
        else:
            candidates[(interview['event_key'], result['round'])].append((row, interview, result))

    # Withdraw old automatic date approvals if their supporting interviews no
    # longer qualify. Dates supporting valid manual matches remain protected.
    for key, period in periods.items():
        if period['reviewer'] in AUTOMATIC - {''} and key not in manual_dates:
            period.update(decision='pending', evidence_url='',
                          notes='No current automatic round evidence.')

    for key, group in candidates.items():
        period = periods[key]
        dates = sorted({interview['interview_date'] for _, interview, _ in group} | manual_dates[key])
        manual = period['reviewer'] not in AUTOMATIC - {''} and bool(
            period['reviewer'] or period['decision'] in ('approve', 'reject'))
        if not manual:
            period.update(decision='approve', reviewer=AUTO, date_start=dates[0], date_end=dates[-1],
                          evidence_url=group[0][1]['transcript_url'],
                          notes='Interview dates accepted by scheduled day-per-round rule; post-round timing assumed. Q&A wording is not used for matching.')
        for row, interview, result in group:
            if period['decision'] != 'approve':
                record(row, dict(result, round='', reason='round_not_approved'))
            elif not period['date_start'] <= interview['interview_date'] <= period['date_end']:
                record(row, dict(result, round='', reason='round_date_conflict'))
            else:
                record(row, result)

    for kind in ('rounds', 'interviews'):
        path = root / f'data/decisions/{kind}.csv'
        temporary = path.with_suffix('.csv.tmp')
        with temporary.open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=COLUMNS[kind], lineterminator='\n')
            writer.writeheader()
            writer.writerows(reviews[kind])
        temporary.replace(path)
    return build(root)
