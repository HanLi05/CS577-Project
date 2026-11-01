"""Offline deterministic normalization, matching, feature construction, and audit."""
import hashlib
import json
from pathlib import Path
import re

import pandas as pd
from .collect import write_json
from .interviews import parse_interview, normalize_name
from .scoring import aggregate_rounds, reconcile_fields
from .matching import match_interviews, verify_tee_dates
from .dataset import build_examples, split_groups, feature_columns
from .text import classify_segment, text_views
from .audit import write_audit


def read_mapping(path, columns):
    if not path.exists():
        return pd.DataFrame(columns=columns)
    frame = pd.read_csv(path, dtype={'event_id':str,'player_id':str,'interview_id':str}, keep_default_na=False)
    for column in ('post_round','verified'):
        if column in frame:
            if not frame[column].astype(str).str.lower().isin(['true','false']).all():
                raise ValueError(f'{path}: {column} must be true or false')
            frame[column] = frame[column].astype(str).str.lower().eq('true')
    return frame


def eligible_history_events(schedule, tees, config):
    mapping={normalize_name(e['name']):e['tee_event_id'] for e in config['events']}
    for name,g in tees.groupby('tournament_name'):
        if g.tournament_id.nunique()==1:
            mapping.setdefault(normalize_name(name), str(g.tournament_id.iloc[0]))
    eligible=[]
    for row in schedule.itertuples():
        if re.search(r'Zurich|TOUR Championship|Barracuda|Q-School|Showdown|Presidents|Grant Thornton|Olympic|Hero World',row.tournament_name,re.I):
            continue
        tid=mapping.get(normalize_name(row.tournament_name))
        course=tees.loc[tees.tournament_id.astype(str)==tid,'course_id']
        if len(course) and not course.isna().any() and course.nunique()==1:
            eligible.append(str(row.event_id))
    return eligible


def build(config, root=Path('.')):
    root=Path(root); interim=root/'data/interim'; processed=root/'data/processed'; maps=root/'data/mappings'
    processed.mkdir(parents=True,exist_ok=True); (root/'reports').mkdir(exist_ok=True)
    schedule=pd.read_parquet(interim/'schedule.parquet')
    schedule['event_id']=schedule.event_id.astype(str)
    for col in ['start_date','end_date']:
        schedule[col]=schedule[col].astype(str).str[:10]
    tees=pd.read_parquet(interim/'tee_times.parquet')
    holes=pd.read_parquet(interim/'holes.parquet').rename(columns={'tournament_id':'event_id'})
    holes['event_id']=holes.event_id.astype(str); holes['player_id']=holes.player_id.astype(str)
    reference_path=interim/'season_reference_rounds.parquet'
    reference=pd.read_parquet(reference_path if reference_path.exists() else interim/'reference_rounds.parquet')
    reference['event_id']=reference.event_id.astype(str); reference['player_id']=reference.player_id.astype(str)
    # A separate per-event response takes precedence for pilot reconciliation.
    pilot_ref=pd.read_parquet(interim/'reference_rounds.parquet')
    reference=pd.concat([reference.loc[~reference.event_id.isin(pilot_ref.event_id)],pilot_ref],ignore_index=True)
    eligible=eligible_history_events(schedule,tees,config)
    holes=holes.loc[holes.event_id.isin(eligible)]
    complete=reference.loc[(reference.holes_completed==18)&reference['round'].isin([1,2,3,4])&reference.event_id.isin(eligible)]
    rounds,issues=aggregate_rounds(holes,complete)
    rounds,field_coverage=reconcile_fields(rounds,reference.loc[reference.event_id.isin(eligible)],holes)
    rounds=rounds.merge(schedule[['event_id','start_date','end_date']],on='event_id',validate='many_to_one')
    parsed=[];segments=[];parse_issues=[]
    manifest=json.loads((interim/'interview_manifest.json').read_text())
    for source in manifest:
        raw=(root/source['raw_path']).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=source['raw_sha256']:
            raise ValueError(f'Transcript hash mismatch: {source["source_url"]}')
        try:
            meta,segs=parse_interview(raw,source['source_url'],source['player_name'])
            meta.update(event_id=source['event_id'],raw_sha256=source['raw_sha256'])
            parsed.append(meta);segments.extend(segs)
        except ValueError as error:
            parse_issues.append(dict(interview_id=source['source_url'].split('=')[-1],event_id=source['event_id'],status='excluded',reason=f'parse:{error}'))
    interviews=pd.DataFrame(parsed)
    if interviews.empty:
        raise ValueError('No parseable transcripts; inspect source formats')
    segment_frame=pd.DataFrame([dict(s,**classify_segment(s['question'],s['answer'])) for s in segments])
    aliases=read_mapping(maps/'players.csv',['event_id','name','player_id'])
    reviews=read_mapping(maps/'interview_reviews.csv',['interview_id','event_id','round','post_round','evidence','content_hash'])
    timing=read_mapping(maps/'round_timing.csv',['event_id','round','round_date','next_round_date','verified','evidence_url'])
    matches,ledger=match_interviews(interviews,rounds,aliases,reviews,timing)
    matches,tee_rejections=verify_tee_dates(matches,tees,config)
    for rejection in tee_rejections:
        ledger.loc[ledger.interview_id==rejection['interview_id'], ['status','reason']]=['review_needed',rejection['reason']]
    ledger=pd.concat([ledger,pd.DataFrame(parse_issues)],ignore_index=True)
    examples=build_examples(matches,rounds,config['history_windows'])
    views={iid:text_views(group.to_dict('records')) for iid,group in segment_frame.groupby('interview_id')}
    if len(examples):
        examples=pd.concat([examples.reset_index(drop=True),pd.DataFrame([views[i] for i in examples.interview_id])],axis=1)
    # Save candidate tables even when manual mappings are not yet supplied.
    for name,frame in [('rounds',rounds),('interviews',interviews),('segments',segment_frame),('matches',ledger),('scoring_issues',issues),('events',schedule),('players',holes[['player_id','player_name']].drop_duplicates()),('normalized_holes',holes)]:
        frame.to_parquet(interim/f'{name}.parquet',index=False)
    examples.to_parquet(processed/'examples.parquet',index=False)
    segment_frame.to_json(processed/'segments.jsonl',orient='records',lines=True,force_ascii=False)
    for chronological,name in [(False,'splits'),(True,'splits_chronological')]:
        splits=split_groups(examples,config['seed'],chronological) if examples.event_id.nunique()>=3 else pd.DataFrame(columns=['example_id','event_id','year','split'])
        splits.to_parquet(processed/f'{name}.parquet',index=False)
    field_coverage.to_csv(root/'reports/field_coverage.csv',index=False)
    ledger.to_csv(root/'reports/match_ledger.csv',index=False)
    write_audit(root,examples,interviews,segment_frame,ledger,field_coverage,rounds,config)
    write_json(processed/'feature_columns.json',feature_columns(config['history_windows']))
    fingerprints={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(processed.glob('*')) if p.name!='build_manifest.json'}
    fingerprints['config_sha256']=hashlib.sha256(json.dumps(config,sort_keys=True).encode()).hexdigest()
    for path in sorted(maps.glob('*.csv')):
        fingerprints[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
    # Pin build inputs and implementation in addition to the generated outputs.
    for path in sorted(interim.glob('*')):
        if path.name in {'holes.parquet','schedule.parquet','tee_times.parquet','interview_manifest.json','reference_rounds.parquet','season_reference_rounds.parquet'}:
            fingerprints[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted(Path(__file__).parent.glob('*.py')):
        fingerprints[f'code/{path.name}']=hashlib.sha256(path.read_bytes()).hexdigest()
    write_json(processed/'build_manifest.json',fingerprints)
    print(f'Built {len(examples)} examples from {len(interviews)} parsed interviews; {len(rounds)} validated historical player-rounds.',flush=True)
    return examples
