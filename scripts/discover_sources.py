"""Read-only pilot source reconnaissance; snapshots live in data/raw/http."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import pandas as pd
from golf_interviews.sources import Cache, ASAP, release_assets, fetch_asset, links

cache = Cache('data/raw/http')
robots = cache.check_robots(ASAP)
assets = release_assets(cache)
for year in [2015, 2020, 2024, 2025]:
    url = f'{ASAP}show_year.php?category=4&year={year}'
    if not robots.can_fetch('*', url):
        raise RuntimeError(f'Robots disallows {url}')
    content = cache.fetch(url).read_bytes()
    print(year, 'archive event links', len(links(content, url, 'show_events.php')),
          'scoring assets', [name for name in [f'holes_{year}.parquet', f'schedule_{year}.parquet'] if name in assets], flush=True)
for name in ['schedule_2024.parquet', 'holes_2024.parquet', 'tee_times_2024.parquet']:
    frame = pd.read_parquet(fetch_asset(cache, assets, name))
    print(name, frame.shape, frame.columns.tolist(), flush=True)
    if name.startswith('schedule'):
        print(frame.to_string(index=False), flush=True)
    else:
        print(frame.head(2).to_dict('records'), flush=True)
year_url = f'{ASAP}show_year.php?category=4&year=2024'
for name, url in links(cache.fetch(year_url).read_bytes(), year_url, 'show_events.php'):
    if name in ['THE PLAYERS CHAMPIONSHIP', 'THE MEMORIAL TOURNAMENT PRESENTED BY WORKDAY', 'CHARLES SCHWAB CHALLENGE']:
        days = links(cache.fetch(url).read_bytes(), url, 'show_event.php')
        print('EVENT', name, url, 'DAYS', days, flush=True)
        if days:
            name, day = days[0]
            interviews = links(cache.fetch(day).read_bytes(), day, 'show_interview.php')
            print('INTERVIEWS', interviews[:3], flush=True)
            if interviews:
                n, link = interviews[0]
                path = cache.fetch(link)
                print('SAMPLE', link, path, flush=True)
