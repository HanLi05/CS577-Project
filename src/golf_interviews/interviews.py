"""Conservative ASAP Q&A extraction with explicit speaker attribution."""
from datetime import datetime
import hashlib
import re
import unicodedata
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup


def normalize_name(name):
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode()
    return re.sub(r'[^a-z0-9]', '', name.casefold())


def clean(text):
    return re.sub(r'\s+', ' ', text).strip()


def parse_interview(html, url, player_name):
    soup = BeautifulSoup(html, 'html.parser')
    heading = soup.find('h1')
    if not heading or not soup.find('h2'):
        raise ValueError('missing_interview_header')
    container = heading.parent
    date = datetime.strptime(clean(container.find('h2').get_text()), '%B %d, %Y').date().isoformat()
    subheads = ' '.join(h.get_text(' ', strip=True) for h in container.find_all('h3'))
    match = re.search(r'\b(?:round\s*([1-4])|(first|second|third|fourth)\s+round)\b', subheads, re.I)
    rnd = None if not match else int(match[1]) if match[1] else ['first', 'second', 'third', 'fourth'].index(match[2].lower()) + 1
    iid = parse_qs(urlparse(url).query).get('id', [hashlib.sha256(url.encode()).hexdigest()[:16]])[0]
    segments, question, answer = [], '', []
    mode = None

    def flush():
        nonlocal answer, question
        if answer:
            segments.append(dict(interview_id=iid, segment_id=f'{iid}:{len(segments):03}',
                                 order=len(segments), question=question, answer=clean(' '.join(answer)), speaker=player_name))
        answer, question = [], ''

    paragraphs = container.find_all('p')
    for p in paragraphs:
        text = clean(p.get_text(' ', strip=True))
        if not text or text.startswith('FastScripts'):
            continue
        q = re.match(r'^Q[.:]\s*(.*)', text)
        speaker = re.match(r"^([^:]{2,60}):\s*(.*)", text)
        if speaker:
            letters = [c for c in speaker[1] if c.isalpha()]
            if not letters or sum(c.isupper() for c in letters) / len(letters) < .75:
                speaker = None
        if q:
            flush()
            question, mode = q[1], 'question'
        elif speaker:
            name, speech = speaker.groups()
            if normalize_name(name) == normalize_name(player_name):
                if mode == 'answer':
                    flush()
                answer, mode = [speech], 'answer'
            elif name in ('THE MODERATOR', 'MODERATOR', 'THE INTERVIEWER', 'INTERVIEWER'):
                flush()
                # A moderator's prompt is useful Q&A context, never an answer.
                question, mode = speech, 'question'
            else:
                raise ValueError(f'multiple_speakers:{name}')
        elif mode == 'answer':
            answer.append(text)
        elif mode == 'question':
            question = clean(question + ' ' + text)
    flush()
    if not segments:
        raise ValueError('no_player_answers')
    normalized = '\n'.join(s['question'] + '\n' + s['answer'] for s in segments)
    meta = dict(interview_id=iid, player_name=player_name, interview_date=date,
                event_name=heading.get_text(' ', strip=True), explicit_round=rnd,
                source_url=url, content_hash=hashlib.sha256(normalized.encode()).hexdigest(),
                parser_version='0.1.0', segment_count=len(segments), header=subheads)
    return meta, segments
