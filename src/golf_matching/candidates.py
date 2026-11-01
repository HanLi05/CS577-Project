"""Load source metadata and suggest links. Suggestions are never approvals."""
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
import pandas as pd
from .sources import Cache, ASAP, release_assets, fetch_asset, links
from .review import sync_review


def normalize(name):
    text=unicodedata.normalize('NFKD',name).encode('ascii','ignore').decode().casefold()
    return re.sub('[^a-z0-9]','',text)


def suggest(name,date,roster,round_dates):
    found=roster.loc[roster.player_name.map(normalize)==normalize(name),'player_id'].unique()
    rounds=[str(r) for r,d in round_dates.items() if d==date]
    pid=str(found[0]) if len(found)==1 else ''
    rnd=rounds[0] if len(rounds)==1 else ''
    reason=('unique normalized name' if pid else 'no unique name match')
    reason+='; date suggests round, review post-round context and delays' if rnd else '; no unique round date'
    return pid,rnd,reason


def round_records(holes,event_id):
    rows=[]
    for (pid,rnd),group in holes.groupby(['player_id','round'],sort=True):
        if rnd not in (1,2,3,4):
            continue
        g=group[['hole','score','par']].drop_duplicates()
        complete=(len(g)==18 and set(g.hole)==set(range(1,19)) and not g.hole.duplicated().any()
                  and g.score.notna().all() and ((g.score>0)&(g.score%1==0)).all())
        rows.append(dict(event_id=event_id,player_id=str(pid),player_name=group.player_name.iloc[0],
                         round=str(int(rnd)),strokes=int(g.score.sum()) if complete else None,complete=bool(complete)))
    return pd.DataFrame(rows)


def prepare(config,offline=False):
    """Collect one configured event and append new, pending rows to review.csv."""
    cache=Cache(config['cache_dir'],offline,delay=1)
    assets=release_assets(cache)
    year=config['year'];eid=str(config['event_id'])
    schedule_path=fetch_asset(cache,assets,f'schedule_{year}.parquet')
    holes_path=fetch_asset(cache,assets,f'holes_{year}.parquet')
    schedule=pd.read_parquet(schedule_path)
    event=schedule.loc[schedule.event_id.astype(str)==eid]
    if len(event)!=1:
        raise ValueError('Event ID must identify exactly one tournament in this year')
    holes=pd.read_parquet(holes_path)
    holes=holes.loc[holes.tournament_id.astype(str)==eid]
    if holes.empty:
        raise ValueError('No scoring records for configured event')
    scores=round_records(holes,eid)
    roster=scores[['player_id','player_name']].drop_duplicates()
    robots=cache.check_robots(ASAP)
    def page(url):
        if not robots.can_fetch('*',url):
            raise ValueError(f'Collection disallowed: {url}')
        return cache.fetch(url).read_bytes()
    annual=f'{ASAP}show_year.php?category=4&year={year}'
    events=[url for name,url in links(page(annual),annual,'show_events.php') if name==config['asap_name']]
    if len(events)!=1:
        raise ValueError('Archive event name must identify exactly one event')
    start=str(event.iloc[0].start_date)[:10];end=str(event.iloc[0].end_date)[:10]
    round_dates={int(r):str(d) for r,d in config['round_dates'].items()}
    records=[]
    # Include final-round interviews too: a correct match is different from a
    # usable next-round example. Leave practice-day interviews out of this pilot.
    for _,day in links(page(events[0]),events[0],'show_event.php'):
        date=parse_qs(urlparse(day).query).get('date',[None])[0]
        if not date or not start<=datetime.strptime(date,'%Y-%m-%d').date().isoformat()<=end:
            continue
        for name,url in links(page(day),day,'show_interview.php'):
            raw=page(url);soup=BeautifulSoup(raw,'html.parser')
            header=soup.find('h1');date_header=soup.find('h2')
            if header is None or date_header is None:
                raise ValueError(f'Missing interview metadata: {url}')
            date=datetime.strptime(date_header.get_text(' ',strip=True),'%B %d, %Y').date().isoformat()
            pid,rnd,reason=suggest(name,date,roster,round_dates)
            if normalize(header.get_text(' ',strip=True))!=normalize(config['asap_name']):
                pid,rnd,reason='','','transcript tournament header conflicts with archive; review required'
            # Bind decisions to the exact source snapshots and proposed date map.
            evidence=dict(transcript=hashlib.sha256(raw).hexdigest(),event_id=eid,year=year,
                          holes=hashlib.sha256(holes_path.read_bytes()).hexdigest(),
                          schedule=hashlib.sha256(schedule_path.read_bytes()).hexdigest(),
                          round_dates=round_dates,notes_url=config['round_notes_url'])
            records.append(dict(interview_id='asap:'+parse_qs(urlparse(url).query)['id'][0],
                transcript_url=url,transcript_player=name,tournament=config['name'],year=str(year),
                event_id=eid,interview_date=date,suggested_player_id=pid,suggested_round=rnd,
                reason=reason,round_notes_url=config['round_notes_url'],
                scoring_url=f'https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard/{eid}',
                source_fingerprint=hashlib.sha256(json.dumps(evidence,sort_keys=True).encode()).hexdigest()))
    candidates=pd.DataFrame(records).drop_duplicates('interview_id').sort_values(['interview_date','transcript_player'])
    directory=Path(config['output_dir']);directory.mkdir(parents=True,exist_ok=True)
    # Generated files can be replaced; sync_review only appends new review keys.
    candidates.to_csv(directory/'candidates.csv',index=False)
    scores.to_csv(directory/'scoring_rounds.csv',index=False)
    roster.to_csv(directory/'players.csv',index=False)
    snapshot=dict(event_id=eid,year=year,round_dates={str(r):d for r,d in round_dates.items()},
                  files={name:hashlib.sha256((directory/name).read_bytes()).hexdigest()
                         for name in ['candidates.csv','scoring_rounds.csv']})
    (directory/'inputs.json').write_text(json.dumps(snapshot,indent=2)+'\n')
    sync_review(candidates,directory/'review.csv')
    print(f'{len(candidates)} candidates ready in {directory / "review.csv"}; existing decisions preserved.')
