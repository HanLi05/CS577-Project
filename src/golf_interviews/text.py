"""Transparent exploratory rules, not validated semantic annotations."""
import re
import pandas as pd

RULE_VERSION = '0.1.0'
CATEGORIES = {
    'confidence': r'\b(confiden\w*|belief|believe|trust|comfortable)\b',
    'physical_condition': r'\b(injur\w*|pain|hurt|sore|back|neck|fatigue|tired|health\w*|rest|recover\w*)\b',
    'preparation': r'\b(practic\w*|prepar\w*|warm.?up|work on|working on|range|training)\b',
    'strategy': r'\b(strateg\w*|plan\w*|approach|target\w*|aggress\w*|conservative|attack\w*)\b',
    'expectations': r'\b(tomorrow|next round|weekend|upcoming|expect\w*|hope\w*|going forward)\b',
}
FUTURE = r"\b(tomorrow|next round|upcoming|weekend|will|i'll|we'll|going to|look(?:ing)? forward|plan to|hope to)\b"
PRESENT_STATE = r"\b(i (?:feel|am|have)|i'm|feeling|still|right now)\b"


def classify_segment(question, answer):
    text = (question + ' ' + answer).lower().replace('’', "'")
    categories = [name for name, pattern in CATEGORIES.items() if re.search(pattern, text)]
    matches = []
    if re.search(FUTURE, text):
        matches.append('future_reference')
    if set(categories) & {'confidence','physical_condition','preparation'} and re.search(PRESENT_STATE, answer.lower().replace('’', "'")):
        matches.append('ongoing_state')
    forward = bool(matches)
    return dict(forward_looking=forward, categories=categories if forward else [], rule_matches=matches, rule_version=RULE_VERSION)


def text_views(segments):
    annotated = [dict(s, **classify_segment(s['question'], s['answer'])) for s in segments]
    forward = [s for s in annotated if s['forward_looking']]
    other = [s for s in annotated if not s['forward_looking']]
    return dict(answers_only='\n\n'.join(s['answer'] for s in annotated),
                question_answer='\n\n'.join(('Q: '+s['question']+'\n' if s['question'] else '')+'A: '+s['answer'] for s in annotated),
                forward_answers='\n\n'.join(s['answer'] for s in forward),
                non_forward_answers='\n\n'.join(s['answer'] for s in other),
                forward_segment_ids=[s['segment_id'] for s in forward],
                non_forward_segment_ids=[s['segment_id'] for s in other], forward_empty=not forward)


def review_sample(segments, n=100, seed=577):
    if segments.empty:
        return segments.assign(human_forward_label=pd.Series(dtype='object'))
    n = min(n, len(segments))
    base = segments.sort_values('segment_id')
    pieces = [group.sample(min(len(group), max(1,n//2)), random_state=seed) for _, group in base.groupby('forward_looking')]
    sample = pd.concat(pieces).head(n)
    remaining = base.loc[~base.segment_id.isin(sample.segment_id)]
    if len(sample) < n:
        sample = pd.concat([sample, remaining.sample(n-len(sample), random_state=seed)])
    sample = sample.sort_values('segment_id').copy()
    sample['human_forward_label'] = pd.NA
    sample['human_categories'] = pd.NA
    sample['review_notes'] = pd.NA
    return sample
