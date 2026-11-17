from copy import deepcopy
import pandas as pd
import pytest
from golf_matching import matching as match


def fixture():
    event = dict(event_key='2024:open', year='2024', event_id='e', tournament='Open',
                 decision='approve', start_date='2024-05-23', end_date='2024-05-26')
    player = dict(event_key='2024:open', event_id='e', interview_name='Jane Doe',
                  player_id='p', decision='approve', reviewer='Reviewer')
    period = dict(event_key='2024:open',event_id='e',round='4',date_start='2024-05-26',
                  date_end='2024-05-26',decision='approve',reviewer='Reviewer',evidence_url='https://example.org/round')
    review = dict(interview_id='asap:1',event_key='2024:open',round='4',context='post_round',
                  decision='approve',reviewer='Reviewer',source_hash='abc',evidence='Completed round stated in Q&A')
    interview = dict(interview_id='asap:1',event_key='2024:open',event_id='e',year='2024',
                     interview_name='Jane Doe',interview_date='2024-05-26',source_hash='abc',
                     parse_status='ok',explicit_round='',tournament='Open',
                     transcript_url='https://example.org/1')
    scores=pd.DataFrame([dict(event_key='2024:open',event_id='e',player_id='p',player_name='Jane Doe',
                             round='4',strokes=72,complete=True,holes_completed=18)])
    reviews={'events':[event],'players':[player],'rounds':[period],'interviews':[review]}
    return [interview],scores,reviews


def test_final_round_and_multiple_distinct_interviews_match_without_next_round():
    interviews,scores,reviews=fixture()
    interviews.append(dict(interviews[0],interview_id='asap:2'))
    reviews['interviews'].append(dict(reviews['interviews'][0],interview_id='asap:2'))
    result=match.build_matches(interviews,scores,reviews)
    assert result.status.tolist()==['matched','matched']
    assert result.strokes.tolist()==[72,72]
    assert 'target_strokes' not in result


@pytest.mark.parametrize('table', ['events','players','rounds','interviews'])
def test_each_human_decision_is_required(table):
    interviews,scores,reviews=fixture()
    reviews[table][0]['decision']='pending'
    result=match.build_matches(interviews,scores,reviews)
    assert result.iloc[0].status=='pending'
    assert pd.isna(result.iloc[0].strokes)


def test_pre_tournament_interviews_are_included_without_completed_round_scores():
    interviews,scores,reviews=fixture()
    reviews['interviews'][0].update(context='pre_tournament',round='')
    interviews[0]['interview_date'] = '2024-05-22'
    reviews['rounds'] = []
    scores['complete'] = False
    scores['strokes'] = None
    result=match.build_matches(interviews,scores,reviews)
    assert result.iloc[0].status=='matched'
    assert result.iloc[0].interview_stage == 'pre_round_1'
    assert result.iloc[0]['round'] == ''
    assert result.iloc[0].player_id=='p'
    assert pd.isna(result.iloc[0].strokes)
    reviews['interviews'][0]['decision']='reject'
    assert match.build_matches(interviews,scores,reviews).iloc[0].status=='excluded'


@pytest.mark.parametrize('change,reason',[
    ('source','source_changed'),('event','event_changed'),('round','round_conflict'),
    ('partial','incomplete_round'),('missing','missing_score'),('date','date_conflict'),
    ('speaker','no_player_answers'),('player','unknown_player')])
def test_unsafe_joins_are_flagged(change,reason):
    interviews,scores,reviews=fixture()
    if change=='source': interviews[0]['source_hash']='new'
    if change=='event': reviews['events'][0]['event_id']='other'
    if change=='round': interviews[0]['explicit_round']='3'
    if change=='partial': scores['complete']=False
    if change=='missing': scores['round']='3'
    if change=='date': interviews[0]['interview_date']='2024-05-25'
    if change=='speaker': interviews[0]['parse_status']='no_player_answers'
    if change=='player': reviews['players'][0]['player_id']='wrong'
    result=match.build_matches(interviews,scores,reviews)
    assert result.iloc[0].reason==reason
    assert pd.isna(result.iloc[0].strokes)


def test_duplicate_scoring_or_review_keys_fail_instead_of_choosing_one():
    interviews,scores,reviews=fixture()
    with pytest.raises(ValueError,match='Duplicate'):
        match.build_matches(interviews,pd.concat([scores,scores]),reviews)
    reviews['players'].append(deepcopy(reviews['players'][0]))
    with pytest.raises(ValueError,match='Duplicate'):
        match.build_matches(interviews,scores,reviews)


def test_sync_preserves_choices_and_flags_only_changed_evidence(tmp_path):
    path=tmp_path/'players.csv'
    row=dict(event_key='2024:open',event_id='e',interview_name='Jane Doe',
             suggested_player_id='p',player_id='p',source_hash='a')
    match.sync_table(path,[row],'players')
    df=pd.read_csv(path,keep_default_na=False,dtype=str)
    df.loc[0,['player_id','decision','reviewer','notes']]=['corrected','approve','Reviewer','checked']
    df.to_csv(path,index=False)
    before=path.read_bytes()
    match.sync_table(path,[row],'players')
    assert path.read_bytes()==before
    match.sync_table(path,[dict(row,source_hash='b')],'players')
    updated=pd.read_csv(path,keep_default_na=False)
    assert updated.iloc[0].player_id=='corrected'
    assert updated.iloc[0].decision=='needs_review'
    assert 'checked' in updated.iloc[0].notes


def test_event_sync_keeps_year_order_and_approval_without_reviewer_or_notes(tmp_path):
    path = tmp_path / 'events.csv'
    schwab = dict(event_key='2024:schwab', year='2024', tournament='CHARLES SCHWAB',
                  event_id='e', collect='yes', decision='approve', source_hash='a')
    match.sync_table(path, [schwab], 'events')
    match.sync_table(path, [
        dict(event_key='2025:open', year='2025', tournament='OPEN'),
        dict(event_key='2024:arnold', year='2024', tournament='ARNOLD PALMER'),
        dict(event_key='2015:open', year='2015', tournament='OPEN'),
        dict(schwab, decision='pending'),
    ], 'events')
    rows = match.read_table(path, 'events')
    assert [r['event_key'] for r in rows] == [
        '2015:open', '2024:arnold', '2024:schwab', '2025:open']
    assert rows[2]['decision'] == 'approve'
    assert not {'reviewer', 'notes'} & set(rows[2])
    match.sync_table(path, [dict(schwab, source_hash='b')], 'events')
    rows = match.read_table(path, 'events')
    assert rows[2]['decision'] == 'needs_review'
    assert not {'reviewer', 'notes'} & set(rows[2])


def test_legacy_interview_tables_migrate_optional_alignment_metadata(tmp_path):
    import csv
    path=tmp_path/'interviews.csv'
    old_columns=[c for c in match.COLUMNS['interviews'] if c not in match.ALIGNMENT_COLUMNS]
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=old_columns)
        writer.writeheader()
        writer.writerow(dict(interview_id='asap:1',event_key='event',decision='approve',reviewer='Reviewer'))
    row=match.read_table(path,'interviews')[0]
    assert row['reviewer']=='Reviewer'
    assert row['matching_method']==''
    match.sync_table(path,[],'interviews')
    assert match.read_table(path,'interviews')[0]==row


def test_legacy_calendar_metadata_migrates_without_preserving_stale_hash(tmp_path):
    import csv
    path = tmp_path / 'interviews.csv'
    columns = [c.replace('schedule_source', 'calendar_source').replace('alignment_hash', 'calendar_hash')
               for c in match.COLUMNS['interviews']]
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        writer.writerow(dict(interview_id='asap:1', event_key='event', decision='approve',
                             reviewer='Reviewer', evidence='Checked', calendar_hash='old-hash',
                             calendar_source='https://example.org/evidence'))
    row = match.read_table(path, 'interviews')[0]
    assert row['schedule_source'] == 'https://example.org/evidence'
    assert row['alignment_hash'] == ''
    assert row['reviewer'] == 'Reviewer' and row['decision'] == 'approve'
    assert 'calendar_hash' not in row and 'calendar_source' not in row
    match.sync_table(path, [], 'interviews')
    assert match.read_table(path, 'interviews')[0] == row


@pytest.mark.parametrize('rnd', ['1', '2', '3', '4'])
def test_post_round_stage_follows_validated_completed_round(rnd):
    interviews, scores, reviews = fixture()
    reviews['rounds'][0]['round'] = rnd
    reviews['interviews'][0]['round'] = rnd
    scores['round'] = rnd
    result = match.build_matches(interviews, scores, reviews).iloc[0]
    assert result.status == 'matched'
    assert result.interview_stage == f'post_round_{rnd}'
    assert result.strokes == 72


def test_other_context_remains_identity_only_without_a_stage():
    interviews, scores, reviews = fixture()
    reviews['interviews'][0].update(context='other', round='')
    result = match.build_matches(interviews, scores, reviews).iloc[0]
    assert result.status == 'identity_only'
    assert result.interview_stage == ''


@pytest.mark.parametrize('change,reason', [
    ('date', 'date_conflict'), ('invalid_date', 'invalid_event_dates'),
    ('heading', 'round_conflict'), ('round', 'unexpected_round'),
    ('evidence', 'missing_interview_evidence'), ('player', 'unknown_player'),
    ('source', 'source_changed'), ('parse', 'no_player_answers'),
])
def test_pre_tournament_inclusion_preserves_validation(change, reason):
    interviews, scores, reviews = fixture()
    interviews[0]['interview_date'] = '2024-05-22'
    reviews['interviews'][0].update(context='pre_tournament', round='')
    if change == 'date': interviews[0]['interview_date'] = '2024-05-23'
    if change == 'invalid_date': interviews[0]['interview_date'] = 'invalid'
    if change == 'heading': interviews[0]['explicit_round'] = '1'
    if change == 'round': reviews['interviews'][0]['round'] = '1'
    if change == 'evidence': reviews['interviews'][0]['evidence'] = ''
    if change == 'player': reviews['players'][0]['player_id'] = 'unknown'
    if change == 'source': interviews[0]['source_hash'] = 'changed'
    if change == 'parse': interviews[0]['parse_status'] = 'no_player_answers'
    result = match.build_matches(interviews, scores, reviews).iloc[0]
    assert result.reason == reason
    assert result.status != 'matched'
    assert result.interview_stage == ''
