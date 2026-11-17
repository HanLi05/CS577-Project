"""Offline integration tests use real cached HTML/Parquet, not a fake pipeline."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest
from golf_matching import preprocessing as prep
from golf_matching import sources
from golf_matching.matching import read_table, sync_table, COLUMNS


def cached(root, url, content):
    cache=root/'data/raw/http';cache.mkdir(parents=True,exist_ok=True)
    path=cache/(hashlib.sha256(url.encode()).hexdigest()+'.bin')
    path.write_bytes(content)
    path.with_suffix('.json').write_text(json.dumps(dict(url=url,status=200,sha256=hashlib.sha256(content).hexdigest())))


def source_fixture(root):
    cached(root,sources.ASAP+'robots.txt',b'User-agent: *\nAllow: /\n')
    assets=[]
    for year in [2024,2025]:
        eid=f'e{year}'
        schedule=pd.DataFrame([dict(event_id=eid,tournament_name='Example Open',
                                    start_date=f'{year}-05-23',end_date=f'{year}-05-26')])
        holes=pd.DataFrame([dict(tournament_id=eid,player_id=p,player_name=name,
                                round=4,hole=h,score=4,par=4)
                            for p,name in [('p','Jane Doe'),('q','Other Golfer')] for h in range(1,19)])
        for kind,frame in [('schedule',schedule),('holes',holes)]:
            name=f'{kind}_{year}.parquet';url=f'https://example.org/{name}'
            assets.append(dict(name=name,browser_download_url=url))
            cached(root,url,frame.to_parquet(index=False))
        annual=sources.ASAP+f'show_year.php?category=4&year={year}'
        event_url=sources.ASAP+f'show_events.php?title=EXAMPLE+OPEN&year={year}'
        day=sources.ASAP+f'show_event.php?date={year}-05-26'
        url=sources.ASAP+f'show_interview.php?id={year}'
        cached(root,annual,f'<a href="{event_url}">EXAMPLE OPEN</a>'.encode())
        cached(root,event_url,f'<a href="{day}">Final day</a>'.encode())
        cached(root,day,f'<a href="{url}">Jane Doe</a>'.encode())
        cached(root,url,f'<div><h1>EXAMPLE OPEN</h1><h2>May 26, {year}</h2><h3>Fourth Round</h3><p>Q. Today?</p><p>JANE DOE: Good.</p></div>'.encode())
    cached(root,sources.RELEASES,json.dumps([dict(assets=assets)]).encode())


def select_events(root):
    path=root/'data/decisions/events.csv'
    rows=read_table(path,'events')
    for row in rows: row.update(collect='yes',decision='approve')
    write_reviews(path,'events',rows)


def write_reviews(path,kind,rows):
    # Human editing deliberately bypasses sync, which must preserve old decisions.
    pd.DataFrame(rows,columns=COLUMNS[kind]).to_csv(path,index=False)


def test_discovery_multiyear_prepare_build_and_review_preservation(tmp_path):
    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024,2025])
    events=read_table(tmp_path/'data/decisions/events.csv','events')
    assert len(events)==2
    assert {r['decision'] for r in events}=={'pending'}
    assert {r['collect'] for r in events}=={'no'}
    select_events(tmp_path)
    prep.prepare(tmp_path,offline=True)
    interviews=[json.loads(line) for line in (tmp_path/'data/processed/interviews.jsonl').read_text().splitlines()]
    assert len(interviews)==2
    assert interviews[0]['segments'][0]['answer']=='Good.'
    scores=pd.read_parquet(tmp_path/'data/processed/scores.parquet')
    assert len(scores)==4  # Includes both non-interviewed golfers.
    for kind in ['players','rounds','interviews']:
        path=tmp_path/f'data/decisions/{kind}.csv'
        rows=read_table(path,kind)
        for row in rows:
            row.update(decision='approve',reviewer='Reviewer')
            if kind=='rounds': row['evidence_url']='https://example.org/round-notes'
            if kind=='interviews': row.update(context='post_round',evidence='Explicit fourth-round heading')
        write_reviews(path,kind,rows)
    before={p.name:p.read_bytes() for p in (tmp_path/'data/decisions').glob('*.csv')}
    prep.prepare(tmp_path,offline=True)
    assert before=={p.name:p.read_bytes() for p in (tmp_path/'data/decisions').glob('*.csv')}
    result=prep.build(tmp_path)
    assert result.status.tolist()==['matched','matched']
    assert result.strokes.tolist()==[72,72]
    assert len(list((tmp_path/'data/processed').iterdir()))==4
    dataset=pd.read_parquet(tmp_path/'data/processed/dataset.parquet')
    assert len(dataset)==2
    assert dataset.iloc[0].segments[0]['answer']=='Good.'
    # Correcting a date must not invalidate the independent player approvals.
    periods=read_table(tmp_path/'data/decisions/rounds.csv','rounds')
    periods[0]['date_end']='2024-05-24'
    write_reviews(tmp_path/'data/decisions/rounds.csv','rounds',periods)
    prep.prepare(tmp_path,offline=True)
    assert (tmp_path/'data/decisions/players.csv').read_bytes()==before['players.csv']


def test_build_requires_prepare_after_event_id_or_collection_changes(tmp_path):
    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024])
    select_events(tmp_path)
    prep.prepare(tmp_path,offline=True)
    path=tmp_path/'data/decisions/events.csv'
    rows=read_table(path,'events');rows[0]['event_id']='different'
    write_reviews(path,'events',rows)
    with pytest.raises(ValueError,match='prepare'):
        prep.build(tmp_path)


def test_discovery_reports_missing_year_without_fabricating_an_event(tmp_path):
    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2015,2024])
    coverage=json.loads((tmp_path/'data/raw/discovery.json').read_text())
    assert coverage['2015']['status']=='unavailable'
    assert coverage['2024']['status']=='ok'
    assert [r['year'] for r in read_table(tmp_path/'data/decisions/events.csv','events')]==['2024']


def test_deselecting_all_events_clears_old_outputs_and_rejected_events_stay_visible(tmp_path):
    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024])
    select_events(tmp_path)
    prep.prepare(tmp_path,offline=True)
    path=tmp_path/'data/decisions/events.csv'
    rows=read_table(path,'events');rows[0]['decision']='reject'
    write_reviews(path,'events',rows)
    assert prep.build(tmp_path).iloc[0].status=='excluded'
    rows[0]['collect']='no';write_reviews(path,'events',rows)
    prep.prepare(tmp_path,offline=True)
    assert prep.build(tmp_path).empty
    assert pd.read_csv(tmp_path/'data/processed/matches.csv').empty


def test_archive_titles_that_look_identical_keep_distinct_keys(tmp_path):
    source_fixture(tmp_path)
    annual=sources.ASAP+'show_year.php?category=4&year=2025'
    cached(tmp_path,annual,b'<a href="show_events.php?title=OPEN+P%26G&amp;year=2025">OPEN P&amp;G</a><a href="show_events.php?title=OPEN+P%26AMP%3BG&amp;year=2025">OPEN P&amp;G</a>')
    prep.prepare(tmp_path,offline=True,years=[2025])
    rows=read_table(tmp_path/'data/decisions/events.csv','events')
    assert len(rows)==2
    assert len({r['event_key'] for r in rows})==2
    assert {r['decision'] for r in rows}=={'pending'}


def test_changed_event_source_invalidates_event_approval_only(tmp_path):
    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024])
    select_events(tmp_path)
    prep.prepare(tmp_path,offline=True)
    path=tmp_path/'data/decisions/players.csv'
    players=read_table(path,'players')
    players[0].update(decision='approve',reviewer='Reviewer')
    write_reviews(path,'players',players)
    schedule=pd.DataFrame([dict(event_id='e2024',tournament_name='Different Tournament',
                                start_date='2024-05-23',end_date='2024-05-26')])
    cached(tmp_path,'https://example.org/schedule_2024.parquet',schedule.to_parquet(index=False))
    prep.prepare(tmp_path,offline=True)
    event=read_table(tmp_path/'data/decisions/events.csv','events')[0]
    assert event['decision']=='needs_review'
    assert read_table(path,'players')[0]['decision']=='approve'
    assert prep.build(tmp_path).iloc[0].status=='pending'


def test_missing_hole_scores_preserves_interviews_and_marks_coverage(tmp_path):
    source_fixture(tmp_path)
    prep.prepare(tmp_path, offline=True, years=[2024, 2025])
    select_events(tmp_path)
    columns=['tournament_id','player_id','player_name','round','hole','score','par']
    cached(tmp_path, 'https://example.org/holes_2024.parquet',
           pd.DataFrame(columns=columns).to_parquet(index=False))
    prep.prepare(tmp_path, offline=True)
    events=read_table(tmp_path/'data/decisions/events.csv', 'events')
    assert [r['coverage'] for r in events]==['no_hole_scores','scores_loaded']
    assert all(r['decision']=='approve' for r in events)
    players=read_table(tmp_path/'data/decisions/players.csv', 'players')
    assert players[0]['suggested_player_id']==''
    assert players[0]['decision']=='pending'
    result=prep.build(tmp_path)
    assert len(result)==2
    assert set(result.status)=={'pending'}
    scores=pd.read_parquet(tmp_path/'data/processed/scores.parquet')
    assert set(scores.year)=={'2025'}


def test_interrupted_collection_saves_completed_event_reviews(tmp_path):
    source_fixture(tmp_path)
    prep.prepare(tmp_path, offline=True, years=[2024,2025])
    select_events(tmp_path)
    url=sources.ASAP+'show_interview.php?id=2025'
    stem=tmp_path/'data/raw/http'/hashlib.sha256(url.encode()).hexdigest()
    stem.with_suffix('.json').unlink()
    stem.with_suffix('.bin').unlink()
    with pytest.raises(sources.CacheError, match='Source not cached'):
        prep.prepare(tmp_path, offline=True)
    for kind in ['players','rounds','interviews']:
        rows=read_table(tmp_path/f'data/decisions/{kind}.csv',kind)
        assert rows
        assert {r['event_key'] for r in rows}=={'2024:EXAMPLE OPEN'}
        assert {r['decision'] for r in rows}=={'pending'}
    # A partial run must not be mistaken for a fully prepared selection.
    with pytest.raises(ValueError, match='run prepare'):
        prep.build(tmp_path)


def test_cross_event_interview_collision_preserves_review_decision(tmp_path):
    source_fixture(tmp_path)
    prep.prepare(tmp_path, offline=True, years=[2024])
    select_events(tmp_path)
    prep.prepare(tmp_path, offline=True)
    path=tmp_path/'data/decisions/interviews.csv'
    rows=read_table(path,'interviews')
    rows[0].update(decision='approve',reviewer='Reviewer')
    write_reviews(path,'interviews',rows)
    before=path.read_bytes()
    prep.prepare(tmp_path, offline=True, years=[2025])
    select_events(tmp_path)
    day=sources.ASAP+'show_event.php?date=2025-05-26'
    duplicate=sources.ASAP+'show_interview.php?id=2024'
    cached(tmp_path,day,f'<a href="{duplicate}">Jane Doe</a>'.encode())
    with pytest.raises(ValueError,match='Conflicting archive entries'):
        prep.prepare(tmp_path,offline=True)
    assert path.read_bytes()==before


def test_automatic_alignment_exports_assumed_timing_and_preserves_manual_override(tmp_path):
    from golf_matching.alignment import align

    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024,2025])
    select_events(tmp_path)
    # Only the first year has an explicit round heading; both assume timing.
    url=sources.ASAP+'show_interview.php?id=2025'
    cached(tmp_path,url,b'<div><h1>EXAMPLE OPEN</h1><h2>May 26, 2025</h2>'
           b'<p>Q. Today?</p><p>JANE DOE: Good.</p></div>')
    prep.prepare(tmp_path,offline=True)
    path=tmp_path/'data/decisions/players.csv'
    players=read_table(path,'players')
    for row in players:row.update(decision='approve',reviewer='Reviewer')
    write_reviews(path,'players',players)
    result=align(tmp_path)
    assert result.status.tolist()==['matched','matched']
    assert result.context.tolist()==['post_round_assumed','post_round_assumed']
    dataset=pd.read_parquet(tmp_path/'data/processed/dataset.parquet')
    assert dataset.interview_id.tolist()==['asap:2024','asap:2025']
    assert dataset.context.tolist()==['post_round_assumed','post_round_assumed']
    before={p.name:p.read_bytes() for p in (tmp_path/'data/decisions').glob('*.csv')}
    align(tmp_path)
    assert before=={p.name:p.read_bytes() for p in (tmp_path/'data/decisions').glob('*.csv')}
    # Explicit human rejection must survive future automatic runs.
    path=tmp_path/'data/decisions/interviews.csv'
    rows=read_table(path,'interviews')
    rows[0].update(decision='reject',reviewer='Reviewer',notes='Manual exclusion')
    write_reviews(path,'interviews',rows)
    align(tmp_path)
    assert read_table(path,'interviews')[0]==rows[0]
    assert pd.read_parquet(tmp_path/'data/processed/dataset.parquet').interview_id.tolist()==['asap:2025']
    periods=read_table(tmp_path/'data/decisions/rounds.csv','rounds')
    assert next(r for r in periods if r['event_key']=='2024:EXAMPLE OPEN' and r['round']=='4')['decision']=='pending'


def test_alignment_retains_date_support_for_previously_matched_manual_interview(tmp_path):
    from golf_matching.alignment import align

    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024])
    select_events(tmp_path)
    day=sources.ASAP+'show_event.php?date=2024-05-26'
    url=sources.ASAP+'show_interview.php?id=2024b'
    cached(tmp_path,day,('<a href="'+sources.ASAP+'show_interview.php?id=2024">Jane Doe</a>'
                        f'<a href="{url}">Jane Doe</a>').encode())
    cached(tmp_path,url,b'<div><h1>EXAMPLE OPEN</h1><h2>May 26, 2024</h2>'
           b'<h3>Fourth Round</h3><p>Q. Today?</p><p>JANE DOE: Good.</p></div>')
    prep.prepare(tmp_path,offline=True)
    path=tmp_path/'data/decisions/players.csv'
    players=read_table(path,'players')
    for row in players:row.update(decision='approve',reviewer='Reviewer')
    write_reviews(path,'players',players)
    assert align(tmp_path).status.tolist()==['matched','matched']
    path=tmp_path/'data/decisions/interviews.csv'
    rows=read_table(path,'interviews');rows[1]['reviewer']='Reviewer'
    write_reviews(path,'interviews',rows)
    assert align(tmp_path).status.tolist()==['matched','matched']
    assert read_table(path,'interviews')[1]==rows[1]


def test_date_alignment_exports_assumptions_and_build_requires_realign_after_schedule_change(tmp_path):
    from golf_matching.alignment import align

    source_fixture(tmp_path)
    prep.prepare(tmp_path, offline=True, years=[2024])
    select_events(tmp_path)
    url=sources.ASAP+'show_interview.php?id=2024'
    cached(tmp_path,url,b'<div><h1>EXAMPLE OPEN</h1><h2>May 26, 2024</h2>'
           b'<p>Q. How did you play today?</p><p>JANE DOE: I played well.</p></div>')
    prep.prepare(tmp_path,offline=True)
    path=tmp_path/'data/decisions/players.csv'
    players=read_table(path,'players')
    for row in players: row.update(decision='approve',reviewer='Reviewer')
    write_reviews(path,'players',players)
    result=align(tmp_path)
    assert result.iloc[0].status=='matched'
    assert result.iloc[0].matching_method=='scheduled_date'
    assert result.iloc[0].verification_status=='schedule_assumed'
    dataset=pd.read_parquet(tmp_path/'data/processed/dataset.parquet')
    assert dataset.iloc[0].matching_method=='scheduled_date'
    path=tmp_path/'data/decisions/events.csv'
    events=read_table(path,'events')
    events[0]['start_date']='2024-05-22'
    write_reviews(path,'events',events)
    with pytest.raises(ValueError,match='align'):
        prep.build(tmp_path)
    result=align(tmp_path)
    assert result.iloc[0].status=='pending'
    assert result.iloc[0].reason=='no_round_on_date'


def test_ambiguous_decisions_remain_visible_without_a_manual_queue(tmp_path):
    from golf_matching.alignment import align

    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024])
    select_events(tmp_path)
    url=sources.ASAP+'show_interview.php?id=2024'
    cached(tmp_path,url,b'<div><h1>EXAMPLE OPEN</h1><h2>May 26, 2024</h2>'
           b'<h3>Third Round</h3><p>Q. How was today?</p><p>JANE DOE: Good.</p></div>')
    prep.prepare(tmp_path,offline=True)
    path=tmp_path/'data/decisions/players.csv'
    players=read_table(path,'players')
    for row in players:row.update(decision='approve',reviewer='Reviewer')
    write_reviews(path,'players',players)
    result=align(tmp_path)
    assert result.iloc[0].status=='ambiguous'
    assert result.iloc[0].reason=='round_date_conflict'
    assert pd.read_parquet(tmp_path/'data/processed/dataset.parquet').empty


def test_score_refresh_invalidates_automatic_round_evidence(tmp_path):
    from golf_matching.alignment import align
    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024])
    select_events(tmp_path)
    cached(tmp_path,sources.ASAP+'show_interview.php?id=2024',
           b'<div><h1>EXAMPLE OPEN</h1><h2>May 26, 2024</h2>'
           b'<p>Q. You shot 72 today. How was your round?</p><p>JANE DOE: Good.</p></div>')
    prep.prepare(tmp_path,offline=True)
    path=tmp_path/'data/decisions/players.csv'
    players=read_table(path,'players')
    for row in players:row.update(decision='approve',reviewer='Reviewer')
    write_reviews(path,'players',players)
    assert align(tmp_path).iloc[0].status=='matched'
    holes=pd.DataFrame([dict(tournament_id='e2024',player_id=p,player_name=name,
        round=4,hole=h,score=5,par=4) for p,name in [('p','Jane Doe'),('q','Other Golfer')]
        for h in range(1,19)])
    cached(tmp_path,'https://example.org/holes_2024.parquet',holes.to_parquet(index=False))
    with pytest.raises(ValueError,match='align'):
        prep.prepare(tmp_path,offline=True)
    with pytest.raises(ValueError,match='align'):
        prep.build(tmp_path)
    result = align(tmp_path)
    assert result.iloc[0].status == 'matched'
    assert result.iloc[0].strokes == 90  # Refreshed hole totals, independent of Q&A wording.
    dataset = pd.read_parquet(tmp_path/'data/processed/dataset.parquet')
    assert dataset.iloc[0].segments[0]['question'].startswith('You shot 72 today.')


def test_player_correction_requires_realigning_automatic_interview_decisions(tmp_path):
    from golf_matching.alignment import align
    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024])
    select_events(tmp_path)
    prep.prepare(tmp_path,offline=True)
    path=tmp_path/'data/decisions/players.csv'
    players=read_table(path,'players')
    for row in players:row.update(decision='approve',reviewer='Reviewer')
    write_reviews(path,'players',players)
    align(tmp_path)
    players[0]['player_id']='q'
    write_reviews(path,'players',players)
    with pytest.raises(ValueError,match='align'):
        prep.build(tmp_path)


@pytest.mark.parametrize('kind',['interviews','rounds'])
def test_explicit_rejection_without_reviewer_is_not_overwritten(tmp_path,kind):
    from golf_matching.alignment import align
    source_fixture(tmp_path)
    prep.prepare(tmp_path,offline=True,years=[2024])
    select_events(tmp_path)
    prep.prepare(tmp_path,offline=True)
    player_path=tmp_path/'data/decisions/players.csv'
    players=read_table(player_path,'players')
    for row in players: row.update(decision='approve',reviewer='Reviewer')
    write_reviews(player_path,'players',players)
    path=tmp_path/f'data/decisions/{kind}.csv'
    rows=read_table(path,kind)
    selected=rows[0] if kind=='interviews' else next(r for r in rows if r['round']=='4')
    selected.update(decision='reject',reviewer='')
    write_reviews(path,kind,rows)
    result=align(tmp_path)
    assert result.iloc[0].status!='matched'
    assert any(r['decision']=='reject' and r['reviewer']=='' for r in read_table(path,kind))


def test_alignment_policy_change_requires_realign(tmp_path, monkeypatch):
    from golf_matching import alignment
    source_fixture(tmp_path)
    prep.prepare(tmp_path, offline=True, years=[2024])
    select_events(tmp_path)
    prep.prepare(tmp_path, offline=True)
    path = tmp_path / 'data/decisions/players.csv'
    players = read_table(path, 'players')
    for row in players:
        row.update(decision='approve', reviewer='Reviewer')
    write_reviews(path, 'players', players)
    alignment.align(tmp_path)
    monkeypatch.setattr(alignment, 'ALIGNMENT_POLICY', 'different-policy')
    with pytest.raises(ValueError, match='align'):
        prep.build(tmp_path)
    assert alignment.align(tmp_path).iloc[0].status == 'matched'


def test_unused_calendar_files_do_not_affect_alignment_or_build(tmp_path):
    from golf_matching.alignment import align
    source_fixture(tmp_path)
    prep.prepare(tmp_path, offline=True, years=[2024])
    select_events(tmp_path)
    prep.prepare(tmp_path, offline=True)
    path=tmp_path/'data/decisions/players.csv'
    players=read_table(path,'players')
    for row in players: row.update(decision='approve',reviewer='Reviewer')
    write_reviews(path,'players',players)
    assert align(tmp_path).iloc[0].status == 'matched'
    # Leftover files from an old checkout must no longer be read or hashed.
    for name in ('round_exceptions.csv', 'player_round_overrides.csv'):
        (tmp_path/'data/decisions'/name).write_text('not a supported input')
    assert prep.build(tmp_path).iloc[0].status == 'matched'
    result=align(tmp_path).iloc[0]
    assert result['round'] == '4'
    assert result.verification_status == 'schedule_assumed'


def test_pre_and_post_round_interviews_export_together_without_prediction_filters(tmp_path):
    from golf_matching.alignment import align
    source_fixture(tmp_path)
    prep.prepare(tmp_path, offline=True, years=[2024])
    select_events(tmp_path)
    day = sources.ASAP + 'show_event.php?date=2024-05-26'
    pre_url = sources.ASAP + 'show_interview.php?id=pre2024'
    cached(tmp_path, day, (
        f'<a href="{sources.ASAP}show_interview.php?id=2024">Jane Doe</a>'
        f'<a href="{pre_url}">Jane Doe</a>').encode())
    cached(tmp_path, pre_url, b'<div><h1>EXAMPLE OPEN</h1><h2>May 22, 2024</h2>'
           b'<p>Q. How are preparations?</p><p>JANE DOE: Good.</p></div>')
    prep.prepare(tmp_path, offline=True)
    path = tmp_path/'data/decisions/players.csv'
    players = read_table(path, 'players')
    for row in players: row.update(decision='approve', reviewer='Reviewer')
    write_reviews(path, 'players', players)
    result = align(tmp_path).set_index('interview_id')
    assert result.loc['asap:pre2024', 'status'] == 'matched'
    assert result.loc['asap:pre2024', 'interview_stage'] == 'pre_round_1'
    assert result.loc['asap:pre2024', 'round'] == ''
    assert pd.isna(result.loc['asap:pre2024', 'strokes'])
    assert result.loc['asap:2024', 'interview_stage'] == 'post_round_4'
    dataset = pd.read_parquet(tmp_path/'data/processed/dataset.parquet').set_index('interview_id')
    assert len(dataset) == 2
    assert dataset.loc['asap:pre2024', 'segments'][0]['answer'] == 'Good.'
    # Fixture has only round 4 scores: pre-round 1 does not require its future target.
    assert set(pd.read_parquet(tmp_path/'data/processed/scores.parquet')['round']) == {'4'}
    periods = read_table(tmp_path/'data/decisions/rounds.csv', 'rounds')
    assert len(periods) == 4 and {r['round'] for r in periods} == {'1', '2', '3', '4'}
    assert [r['round'] for r in periods if r['decision'] == 'approve'] == ['4']
    before = {p.name: p.read_bytes() for p in (tmp_path/'data/decisions').glob('*.csv')}
    align(tmp_path)
    assert before == {p.name: p.read_bytes() for p in (tmp_path/'data/decisions').glob('*.csv')}
    # A human can still reject a pre-tournament interview on reruns.
    path = tmp_path/'data/decisions/interviews.csv'
    rows = read_table(path, 'interviews')
    pre = next(r for r in rows if r['interview_id'] == 'asap:pre2024')
    pre.update(decision='reject', reviewer='Reviewer')
    write_reviews(path, 'interviews', rows)
    result = align(tmp_path).set_index('interview_id')
    assert result.loc['asap:pre2024', 'status'] == 'excluded'
