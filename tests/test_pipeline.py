import json
from pathlib import Path
import pandas as pd
from golf_interviews.pipeline import build


def test_offline_pipeline_outputs_and_repeatability(tmp_path):
    raw=tmp_path/'data/raw'; raw.mkdir(parents=True)
    interim=tmp_path/'data/interim';interim.mkdir()
    maps=tmp_path/'data/mappings';maps.mkdir()
    holes=[]; ref=[]; schedule=[]; tees=[]; manifest=[]; aliases=[];reviews=[];timing=[]
    from golf_interviews.interviews import parse_interview
    for j in range(3):
        eid=f'e{j}';date=f'2024-05-{j*5+1:02}';nxt=f'2024-05-{j*5+2:02}'
        schedule.append(dict(event_id=eid,tournament_name=eid,start_date=date,end_date=nxt))
        for player in ('1','2'):
            for rnd in (1,2):
                for h in range(1,19):
                    holes.append(dict(tournament_id=eid,player_id=player,player_name=f'Player {player}',round=rnd,hole=h,par=4,score=4))
                ref.append(dict(event_id=eid,player_id=player,player_name=f'Player {player}',round=rnd,expected_strokes=72,holes_completed=18,final_status='complete'))
                tees.append(dict(tournament_id=eid,tournament_name=eid,player_id=player,player_name=f'Player {player}',round=rnd,course_id='c',tee_time=pd.Timestamp(date if rnd==1 else nxt,tz='UTC'),timezone='UTC'))
        url=f'https://www.asapsports.com/show_interview.php?id={j}'
        html=f'<td><h1>{eid}</h1><h2>May {j*5+1}, 2024</h2><h3>Player 1</h3><p>Q. How was the round?</p><p>PLAYER 1: Good. I will practice tomorrow.</p></td>'
        path=raw/f'{j}.html';path.write_text(html)
        import hashlib
        manifest.append(dict(event_id=eid,player_name='Player 1',source_url=url,raw_path=str(path.relative_to(tmp_path)),raw_sha256=hashlib.sha256(html.encode()).hexdigest()))
        meta,_=parse_interview(html,url,'Player 1')
        aliases.append(dict(event_id=eid,name='Player 1',player_id='1'))
        reviews.append(dict(interview_id=str(j),event_id=eid,round=1,post_round=True,evidence='Reviewed post-round statement',content_hash=meta['content_hash']))
        timing.append(dict(event_id=eid,round=1,round_date=date,next_round_date=nxt,verified=True,evidence_url='https://example.org/notes'))
    for name,rows in [('holes',holes),('schedule',schedule),('tee_times',tees),('reference_rounds',ref)]:
        pd.DataFrame(rows).to_parquet(interim/f'{name}.parquet')
    (interim/'interview_manifest.json').write_text(json.dumps(manifest))
    for name,rows in [('players',aliases),('interview_reviews',reviews),('round_timing',timing)]:
        pd.DataFrame(rows).to_csv(maps/f'{name}.csv',index=False)
    config=dict(seed=577,history_windows=[5,20],events=[dict(event_id=f'e{j}',name=f'e{j}',tee_event_id=f'e{j}') for j in range(3)])
    build(config,tmp_path)
    path=tmp_path/'data/processed/examples.parquet'
    x=pd.read_parquet(path)
    assert len(x)==3
    assert set(x.y_cls)=={0}
    assert (tmp_path/'reports/data_quality.md').exists()
    old=(tmp_path/'data/processed/build_manifest.json').read_text()
    assert 'tournament_id' in pd.read_parquet(interim/'holes.parquet').columns
    build(config,tmp_path)
    assert (tmp_path/'data/processed/build_manifest.json').read_text()==old
    pd.testing.assert_frame_equal(x,pd.read_parquet(path))
