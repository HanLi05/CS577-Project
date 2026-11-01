from golf_interviews.text import classify_segment, text_views, review_sample
import pandas as pd


def test_rules_distinguish_past_play_and_preserve_multiple_categories():
    past=classify_segment('How did you play?', 'My strategy yesterday was to attack the pin.')
    assert not past['forward_looking']
    future=classify_segment('What about tomorrow?', 'I feel confident. I will practice putting and rest my back.')
    assert future['forward_looking']
    assert set(future['categories']) >= {'confidence','preparation','physical_condition','expectations'}
    assert future['rule_matches']


def test_empty_forward_subset_retains_example_and_complement():
    segments=[dict(segment_id='s',question='How was today?',answer='I shot 72 yesterday.')]
    view=text_views(segments)
    assert view['forward_empty']
    assert view['answers_only'] == 'I shot 72 yesterday.'
    assert view['non_forward_segment_ids'] == ['s']
    assert not view['forward_segment_ids']


def test_review_sample_contains_both_classes_and_no_fabricated_labels():
    frame=pd.DataFrame([dict(segment_id=str(i), forward_looking=i<5) for i in range(20)])
    sample=review_sample(frame,10,577)
    assert set(sample.forward_looking) == {True,False}
    assert len(sample)==10
    assert sample.human_forward_label.isna().all()
