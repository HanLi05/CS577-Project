"""Parse source interviews and aggregate full-field hole scores without targets."""
from datetime import datetime
import hashlib
import re
import unicodedata

from bs4 import BeautifulSoup
import pandas as pd

SCORE_COLUMNS = ['event_key', 'event_id', 'year', 'player_id', 'player_name',
                 'round', 'holes_completed', 'complete', 'strokes']


def normalize(name):
    """Only a suggestion rule; normalized names are never join keys."""
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub('[^a-z0-9]', '', text.casefold())


def parse_interview(raw, player_name):
    """Return ordered Q&A, preserving a visible status for unsupported pages."""
    # Some legacy pages contain double-encoded nonbreaking-space padding (Â ),
    # including before speaker labels. Normalize that exact byte sequence only;
    # retain the original bytes for the source hash below.
    soup = BeautifulSoup(raw.replace(b'\xc3\x82\xc2\xa0', b' '), 'html.parser')
    row = dict(source_hash=hashlib.sha256(raw).hexdigest(), tournament='',
               interview_date='', explicit_round='', segments=[], parse_status='ok')
    heading = soup.find('h1')
    if heading is None or heading.parent.find('h2') is None:
        return dict(row, parse_status='missing_header')
    container = heading.parent
    row['tournament'] = heading.get_text(' ', strip=True)
    try:
        row['interview_date'] = datetime.strptime(
            container.find('h2').get_text(' ', strip=True), '%B %d, %Y').date().isoformat()
    except ValueError:
        return dict(row, parse_status='invalid_date')
    subheads = ' '.join(h.get_text(' ', strip=True) for h in container.find_all('h3'))
    explicit = re.search(r'\b(?:round\s*([1-4])|(first|second|third|fourth)\s+round)\b', subheads, re.I)
    if explicit:
        row['explicit_round'] = explicit[1] or str(
            ['first', 'second', 'third', 'fourth'].index(explicit[2].lower()) + 1)
    segments, question, answer, mode = [], '', [], None

    def flush():
        nonlocal question, answer
        if answer:
            segments.append(dict(order=len(segments), question=question,
                                 answer=' '.join(answer)))
        question, answer = '', []

    paragraphs = [p for p in container.find_all('p') if p.get_text(strip=True)]
    if paragraphs:
        lines = [p.get_text(' ', strip=True) for p in paragraphs]
    else:
        # Older ASAP transcripts put Q&A directly in a table cell, separated
        # by <br> tags. Keep inline bold question fragments on the same line.
        for header in container.find_all(['h1', 'h2', 'h3']):
            header.decompose()
        for br in container.find_all('br'):
            br.replace_with('\n')
        lines = container.get_text(' ').splitlines()

    # The archive's named golfer owns the answers. Other labeled speakers
    # supply interviewer/context text; their presence never rejects the page.
    other_speakers = {}

    for line in lines:
        text = ' '.join(line.split())
        if not text or text.startswith('FastScripts'):
            continue
        prompt = re.match(r'^Q[.:]\s*(.*)', text)
        speaker = re.match(r'^([^:]{2,60}):\s*(.*)', text)
        if prompt:
            flush()
            question, mode = prompt[1], 'question'
        elif speaker:
            name, speech = speaker.groups()
            if normalize(name) == normalize(player_name):
                if mode == 'answer':
                    flush()
                answer, mode = [speech], 'answer'
            else:
                other_speakers.setdefault(normalize(name), name)
                flush()
                question, mode = speech, 'question'
        elif mode == 'answer':
            answer.append(text)
        elif mode == 'question':
            question = (question + ' ' + text).strip()
    flush()
    if other_speakers:
        row['other_speaker_names'] = list(other_speakers.values())
    return dict(row, segments=segments, parse_status='ok' if segments else 'no_player_answers')


def round_scores(holes, event_key, event_id, year):
    """Keep every golfer; partial/conflicting rounds have no invented total."""
    records = []
    for (pid, rnd), group in holes.groupby(['player_id', 'round'], sort=True):
        if rnd not in (1, 2, 3, 4):
            continue  # Regulation scoring only; preserve raw playoff data in cache.
        unique = group[['hole', 'score', 'par']].drop_duplicates()
        complete = (len(unique) == 18 and set(unique.hole) == set(range(1, 19))
                    and not unique.hole.duplicated().any() and unique.score.notna().all()
                    and ((unique.score > 0) & (unique.score % 1 == 0)).all())
        records.append(dict(event_key=event_key, event_id=event_id, year=str(year),
                            player_id=str(pid), player_name=group.player_name.iloc[0],
                            round=str(int(rnd)), holes_completed=unique.loc[
                                unique.score.notna() & (unique.score > 0), 'hole'].nunique(),
                            complete=bool(complete),
                            strokes=int(unique.score.sum()) if complete else None))
    return pd.DataFrame(records, columns=SCORE_COLUMNS)


def prepare(root, offline=False, years=()):
    """Discover optional years, then prepare events marked collect=yes."""
    from datetime import timedelta
    import json
    from pathlib import Path
    from urllib.parse import parse_qs, urlparse
    from .sources import Cache, ASAP, discover_events, release_assets, fetch_asset, links, event_fingerprint
    from .matching import read_table, sync_table

    root = Path(root)
    decisions_dir, output = root / 'data/decisions', root / 'data/processed'
    cache = Cache(root / 'data/raw/http', offline=offline)
    sync_table(decisions_dir / 'events.csv', [], 'events')
    if years:
        events, coverage = discover_events(cache, years)
        sync_table(decisions_dir / 'events.csv', events, 'events')
        (root / 'data/raw/discovery.json').write_text(json.dumps(coverage, indent=2) + '\n')
    events = [r for r in read_table(decisions_dir / 'events.csv', 'events')
              if r['collect'] == 'yes']
    if not events:
        print('No events selected. Set collect=yes and event_id in data/decisions/events.csv.')
    assets = release_assets(cache) if events else {}
    robots = cache.check_robots(ASAP) if events else None

    def page(url):
        if not robots.can_fetch('*', url):
            raise ValueError(f'Collection disallowed: {url}')
        return cache.fetch(url).read_bytes()

    def fingerprint(value):
        return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    seasons, source_paths = {}, []
    interviews, all_scores = [], []
    suggestions = {kind: [] for kind in ('players', 'rounds', 'interviews')}
    interview_events = {r['interview_id']: r['event_key']
                        for r in read_table(decisions_dir / 'interviews.csv', 'interviews')}
    prepared_events = {}
    for event in events:
        key, eid, year = event['event_key'], event['event_id'], event['year']
        if not eid:
            raise ValueError(f'{key}: choose a scoring event_id before collection')
        if year not in seasons:
            paths = [fetch_asset(cache, assets, f'{kind}_{year}.parquet') for kind in ('schedule', 'holes')]
            seasons[year] = [pd.read_parquet(path) for path in paths]
            source_paths.extend(str(p.relative_to(root)) for p in paths)
        schedule, holes = seasons[year]
        selected = schedule.loc[schedule.event_id.astype(str) == eid]
        if len(selected) != 1:
            raise ValueError(f'{key}: event_id must identify one tournament in the {year} schedule')
        scoring_event = selected.iloc[0]
        event_holes = holes.loc[holes.tournament_id.astype(str) == eid]
        if event_holes.empty:
            print(f'{key}: no hole scores available for {eid}; retaining interviews for review.')
        scores = round_scores(event_holes, key, eid, year)
        all_scores.append(scores)
        roster = scores[['player_id', 'player_name']].drop_duplicates()
        start = str(scoring_event.start_date)[:10]
        end = str(scoring_event.end_date)[:10]
        dates = {str(r): (datetime.fromisoformat(start) + timedelta(days=r-1)).date().isoformat()
                 for r in (1, 2, 3, 4)}
        for rnd, suggested in dates.items():
            suggestions['rounds'].append(dict(event_key=key, event_id=eid, round=rnd,
                suggested_date=suggested, date_start=suggested, date_end=suggested,
                source_hash=fingerprint([eid, start, end])))
        event_interviews = {}
        for _, day in links(page(event['asap_url']), event['asap_url'], 'show_event.php'):
            for name, url in links(page(day), day, 'show_interview.php'):
                iid = 'asap:' + parse_qs(urlparse(url).query)['id'][0]
                row = dict(parse_interview(page(url), name), interview_id=iid, event_key=key,
                           event_id=eid, year=year, interview_name=name, transcript_url=url)
                if row['parse_status'] == 'ok' and normalize(row['tournament']) != normalize(event['tournament']):
                    row['parse_status'] = 'event_conflict'
                if iid in event_interviews and event_interviews[iid] != row:
                    raise ValueError(f'Conflicting archive entries for {iid}')
                event_interviews[iid] = row
        for iid in event_interviews:
            if iid in interview_events and interview_events[iid] != key:
                raise ValueError(f'Conflicting archive entries for {iid}: '
                                 f'{interview_events[iid]} and {key}')
        interview_events.update({iid: key for iid in event_interviews})
        for row in sorted(event_interviews.values(), key=lambda r: (r['interview_date'], r['interview_id'])):
            date = row['interview_date']
            suggested_round = row['explicit_round'] or next((r for r, d in dates.items() if d == date), '')
            suggestions['interviews'].append(dict(row, suggested_round=suggested_round,
                                                 round=suggested_round, context=''))
            interviews.append(row)
        for name in sorted({r['interview_name'] for r in event_interviews.values()}):
            found = roster.loc[roster.player_name.map(normalize) == normalize(name)]
            pid = found.player_id.iloc[0] if found.player_id.nunique() == 1 else ''
            suggestions['players'].append(dict(event_key=key, event_id=eid, interview_name=name,
                suggested_player_id=pid, player_id=pid,
                scoring_name=' / '.join(sorted(found.player_name.unique())),
                source_hash=fingerprint([eid, name, sorted(found.itertuples(index=False, name=None))])))
        # Keep source schedule information readable in the editable event inventory.
        updated = dict(event, scoring_name=scoring_event.tournament_name, start_date=start,
                       end_date=end, coverage='no_hole_scores' if event_holes.empty else 'scores_loaded')
        updated['source_hash'] = event_fingerprint(updated)
        sync_table(decisions_dir / 'events.csv', [updated], 'events')
        prepared_events[key] = {k: event[k] for k in ('event_id', 'year', 'tournament', 'asap_url')}
        # Save review progress after each complete event. Processed outputs are
        # published only after the entire selected collection succeeds.
        for kind, rows in suggestions.items():
            sync_table(decisions_dir / f'{kind}.csv', rows, kind)
        suggestions = {kind: [] for kind in suggestions}
        print(f'{key}: {len(event_interviews)} interviews; {len(scores)} full-field player-rounds.')
    from .matching import index_rows
    index_rows(interviews, ['interview_id'])
    for kind in suggestions:
        sync_table(decisions_dir / f'{kind}.csv', [], kind)
    output.mkdir(parents=True, exist_ok=True)
    (output / 'interviews.jsonl').write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in interviews))
    scores = pd.concat(all_scores, ignore_index=True) if all_scores else pd.DataFrame(columns=SCORE_COLUMNS)
    scores.to_parquet(output / 'scores.parquet', index=False)
    # Internal replay metadata lives with the cache, not alongside review worksheets.
    snapshot = dict(events=prepared_events, source_paths=source_paths,
                    files={name: hashlib.sha256((output / name).read_bytes()).hexdigest()
                           for name in ('interviews.jsonl', 'scores.parquet')})
    (root / 'data/raw/prepared.json').write_text(json.dumps(snapshot, indent=2) + '\n')
    build(root)


def prepared_inputs(root):
    """Load inputs only when source hashes and the selected events still agree."""
    import json
    from pathlib import Path
    from .matching import read_table

    root = Path(root)
    output = root / 'data/processed'
    snapshot_path = root / 'data/raw/prepared.json'
    if not snapshot_path.exists():
        raise ValueError('Run prepare before build')
    snapshot = json.loads(snapshot_path.read_text())
    reviews = {kind: read_table(root / f'data/decisions/{kind}.csv', kind)
               for kind in ('events', 'players', 'rounds', 'interviews')}
    selected = {r['event_key']: {k: r[k] for k in ('event_id', 'year', 'tournament', 'asap_url')}
                for r in reviews['events'] if r['collect'] == 'yes'}
    if selected != snapshot['events']:
        raise ValueError('Event selection or source IDs changed; run prepare before build')
    for name, digest in snapshot['files'].items():
        if hashlib.sha256((output / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Generated {name} changed; run prepare before build')
    interviews = [json.loads(line) for line in (output / 'interviews.jsonl').read_text().splitlines()]
    scores = pd.read_parquet(output / 'scores.parquet')
    return interviews, scores, reviews


def build(root):
    """Apply decisions; export the full audit and the included interview dataset."""
    from pathlib import Path
    from .matching import build_matches
    from .alignment import alignment_state, AUTO

    interviews, scores, reviews = prepared_inputs(root)
    alignment_hash = alignment_state(root, reviews['events'])
    current_ids = {row['interview_id'] for row in interviews}
    if any(row['interview_id'] in current_ids and row['reviewer'] == AUTO
           and row['alignment_hash'] != alignment_hash for row in reviews['interviews']):
        raise ValueError('Schedule, prepared inputs, player decisions, or alignment policy changed; run align before build')
    output = Path(root) / 'data/processed'
    matches = build_matches(interviews, scores, reviews)
    matches.to_csv(output / 'matches.csv', index=False)
    text = {r['interview_id']: r for r in interviews}
    dataset = matches.loc[matches.status == 'matched'].copy()
    dataset['segments'] = [text[i]['segments'] for i in dataset.interview_id]
    dataset['source_hash'] = [text[i]['source_hash'] for i in dataset.interview_id]
    dataset.to_parquet(output / 'dataset.parquet', index=False)
    print(f'Match statuses: {matches.status.value_counts().to_dict()}')
    print(f'Working dataset: {len(dataset)} interviews in {output / "dataset.parquet"}')
    return matches
