from copy import deepcopy

import pytest
from golf_matching.alignment import infer_round, assign_round


def inputs(question='How did you play today?', heading='', answer='Good.'):
    interview = dict(parse_status='ok', explicit_round=heading, interview_date='2024-05-24',
                     segments=[dict(question=question, answer=answer)])
    scores = {str(i): dict(complete=True, strokes=s) for i, s in enumerate([70,66,69,68],1)}
    return interview,scores,dict(event_key='event',event_id='e',start_date='2024-05-23',end_date='2024-05-26')


@pytest.mark.parametrize('question,answer', [
    ('How are things?', 'Good.'),
    ('How did you play today?', 'I played well.'),
    ('Before you tee off today, how are you?', "I haven't started my round."),
    ('How was today?', 'I still have five holes left to play.'),
    ('How did the playoff go?', 'I won on the second playoff hole.'),
    ('You shot 70 today?', 'No, I shot 75.'),
    ('How was your third round today?', 'My first round was better.'),
    ('Have you shot 59 before?', 'Yes, in college.'),
    ("Justin's round of 69 was impressive.", 'He played well.'),
    ('Could you shoot 60 tomorrow?', 'I hope so.'),
])
def test_conversation_does_not_affect_automatic_round_assignment(question, answer):
    row, scores, event = inputs(question, answer=answer)
    before = deepcopy(row)
    result = assign_round(row, scores, event)
    assert result == assign_round(*inputs('', answer=''))
    assert result['round'] == '2' and result['reason'] == ''
    assert result['context'] == 'post_round_assumed'
    assert result['verification_status'] == 'schedule_assumed'
    assert result['matching_method'] == 'scheduled_date'
    assert row == before  # Keep the full Q&A for downstream analysis.


def test_matching_heading_corroborates_round_but_does_not_verify_timing():
    result = assign_round(*inputs(heading='2'))
    assert result['round'] == '2' and result['reason'] == ''
    assert result['matching_method'] == 'scheduled_date+transcript_heading'
    assert result['context'] == 'post_round_assumed'
    assert result['verification_status'] == 'schedule_assumed'


def test_heading_cannot_move_round_to_a_different_date():
    assert assign_round(*inputs(heading='3'))['reason'] == 'round_date_conflict'


@pytest.mark.parametrize('score', [None, dict(complete=False, strokes=None),
                                    dict(complete=True, strokes=None)])
def test_missing_or_incomplete_scores_still_prevent_inclusion(score):
    row, scores, event = inputs()
    if score is None:
        del scores['2']
    else:
        scores['2'] = score
    assert infer_round(row, scores, event)[2] == 'incomplete_round'


def test_parser_failure_still_prevents_inclusion():
    row, scores, event = inputs()
    row['parse_status'] = 'no_player_answers'
    assert assign_round(row, scores, event)['reason'] == 'no_player_answers'


@pytest.mark.parametrize('observed,reason', [
    ('2024-05-27', 'no_round_on_date'),
    ('invalid', 'invalid_event_dates'),
])
def test_invalid_or_outside_dates_still_prevent_assignment(observed, reason):
    row, scores, event = inputs()
    row['interview_date'] = observed
    assert assign_round(row, scores, event)['reason'] == reason


@pytest.mark.parametrize('start,observed,expected', [
    ('2024-05-22', '2024-05-22', '1'),
    ('2024-05-22', '2024-05-23', '2'),
    ('2024-05-24', '2024-05-26', '3'),
    ('2024-05-24', '2024-05-27', '4'),
])
def test_rounds_follow_start_date_without_weekday_assumptions(start, observed, expected):
    row, scores, event = inputs()
    event.update(start_date=start, asap_url='https://example.org/event')
    row['interview_date'] = observed
    result = assign_round(row, scores, event)
    assert result['round'] == expected
    assert result['schedule_source'] == event['asap_url']


def test_pre_tournament_assignment_has_no_completed_round_or_score_requirement():
    row, scores, event = inputs()
    row['interview_date'] = '2024-05-22'
    result = assign_round(row, {}, event)
    assert result['reason'] == ''
    assert result['context'] == 'pre_tournament'
    assert result['round'] == ''
    assert result['matching_method'] == 'scheduled_date'
    assert result['verification_status'] == 'schedule_assumed'
    assert result['evidence']


def test_pre_tournament_date_with_a_completed_round_heading_is_ambiguous():
    row, scores, event = inputs(heading='1')
    row['interview_date'] = '2024-05-22'
    assert assign_round(row, scores, event)['reason'] == 'round_date_conflict'
