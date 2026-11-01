"""Collect scoring records and interview pages for the configured tournaments.

This file gathers the source material. Parsing interview text and deciding which
interviews can be paired with next-round scores happen later in the pipeline.
"""
from datetime import datetime
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd
from .sources import ASAP, Cache, release_assets, fetch_asset, links


def write_json(path, value):
    """Save a readable JSON file, creating its folder if needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str) + '\n')


def eligible_day_links(candidates, start, end):
    """Keep archive links dated within the tournament, skipping practice days."""
    result = []
    for name, url in candidates:
        date = parse_qs(urlparse(url).query).get('date', [None])[0]
        if date and start <= datetime.strptime(date, '%Y-%m-%d').date().isoformat() <= end:
            result.append((name, url))
    return result


def scoreboard_rounds(data, event_id):
    """Turn ESPN's nested response into player-round records for score checks."""
    result = []
    for event in data.get('events', [data]):
        if str(event.get('id')) != event_id:
            continue
        for competition in event.get('competitions', []):
            for player in competition.get('competitors', []):
                if 'athlete' not in player:
                    continue  # Team events are outside the individual-player dataset.
                for rnd in player.get('linescores', []):
                    result.append(dict(event_id=event_id, player_id=str(player['id']),
                                       player_name=player['athlete']['displayName'],
                                       round=rnd['period'], expected_strokes=rnd.get('value'),
                                       holes_completed=sum(h.get('value', 0) > 0 for h in rnd.get('linescores', [])),
                                       final_status=player.get('status', {}).get('type', {}).get('name', 'unknown')))
    return result


def collect(config, root=Path('.'), offline=False):
    """Gather the configured pilot's sources and save an index of its interviews."""
    # Reuse saved downloads when possible. Offline mode requires them to exist.
    root = Path(root)
    cache = Cache(root / 'data/raw/http', offline, config['request_delay_seconds'])
    assets = release_assets(cache)
    robots = cache.check_robots(ASAP)
    def asap(url):
        if not robots.can_fetch('*', url):
            raise RuntimeError(f'robots.txt disallows collection: {url}')
        return cache.fetch(url)
    # Load the season's schedule, hole scores, and tee times from golfastR.
    # Keeping the full scoring population supports field averages and history.
    year = config['pilot_year']
    tables = {}
    for kind, filename in [('schedule', f'schedule_{year}.parquet'), ('holes', f'holes_{year}.parquet'), ('tee_times', f'tee_times_{year}.parquet')]:
        tables[kind] = pd.read_parquet(fetch_asset(cache, assets, filename))
    directory = root / 'data/interim'
    directory.mkdir(parents=True, exist_ok=True)
    for kind, frame in tables.items():
        frame.to_parquet(directory / f'{kind}.parquet', index=False)
    # Check a few other years for source availability; this is not a full
    # collection of their interviews or a guarantee that their records match.
    coverage = []
    for probe in sorted(set(config['probe_years'] + [year])):
        url = f'{ASAP}show_year.php?category=4&year={probe}'
        page = asap(url)
        # Actual small scoring assets, not just a check that filenames exist.
        schedule = pd.read_parquet(fetch_asset(cache, assets, f'schedule_{probe}.parquet'))
        holes = pd.read_parquet(fetch_asset(cache, assets, f'holes_{probe}.parquet'))
        coverage.append(dict(year=probe, archive_events=len(links(page.read_bytes(), url, 'show_events.php')),
                             schedule_events=len(schedule), scoring_events=holes.tournament_id.nunique(),
                             scoring_rows=len(holes), scope='presence only; not verified usable overlap'))
    # Find each selected tournament in the interview archive using its exact
    # configured name, and get its scoring reference from ESPN.
    year_url = f'{ASAP}show_year.php?category=4&year={year}'
    event_links = links(asap(year_url).read_bytes(), year_url, 'show_events.php')
    manifest, reference = [], []
    for event in config['events']:
        eid = event['event_id']
        schedule = tables['schedule'].loc[tables['schedule'].event_id.astype(str) == eid]
        if len(schedule) != 1:
            raise ValueError(f'Event ID not uniquely present in schedule: {eid}')
        row = schedule.iloc[0]
        candidates = [url for name, url in event_links if name == event['asap_name']]
        if len(candidates) != 1:
            raise ValueError(f'ASAP event not uniquely resolved: {event["asap_name"]}')
        url = candidates[0]
        dates = eligible_day_links(links(asap(url).read_bytes(), url, 'show_event.php'), str(row.start_date)[:10], str(row.end_date)[:10])
        score_url = f'https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard/{eid}'
        reference.extend(scoreboard_rounds(cache.json(score_url), eid))
        # Follow tournament -> day -> interview links and save each original page.
        # The manifest is an index: who spoke, at which event, and where the page
        # is saved. It does not yet mean the interview is a usable example.
        for _, day in dates:
            for player, interview in links(asap(day).read_bytes(), day, 'show_interview.php'):
                path = asap(interview)
                manifest.append(dict(event_id=eid, player_name=player, source_url=interview,
                                     archive_day_url=day, event_url=url,
                                     raw_path=str(path.relative_to(root)),
                                     raw_sha256=json.loads(path.with_suffix('.json').read_text())['sha256']))
            print(f'Collected {event["name"]}: {parse_qs(urlparse(day).query)["date"][0]}', flush=True)
        # Persist progress; interrupted runs resume from the verified HTTP cache.
        write_json(directory / 'interview_manifest.json', manifest)
    pd.DataFrame(reference).to_parquet(directory / 'reference_rounds.parquet', index=False)
    # One season response validates historical scoring too (not just pilot golfers).
    season = cache.json(f'https://site.api.espn.com/apis/site/v2/sports/golf/pga/scoreboard?dates={year}')
    season_reference = [r for event in season.get('events', []) for r in scoreboard_rounds(event, str(event['id']))]
    pd.DataFrame(season_reference).to_parquet(directory / 'season_reference_rounds.parquet', index=False)
    write_json(root / 'reports/source_coverage.json', coverage)
    print(f'Collected {len(manifest)} transcript references; raw sources cached.', flush=True)
    return manifest
