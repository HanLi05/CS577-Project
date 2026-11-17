import pandas as pd
import pytest
from golf_matching import preprocessing as prep


def test_parse_preserves_qa_and_intro_without_moderator_answers():
    html = '''<div><h1>Example Open</h1><h2>May 23, 2024</h2>
    <h3>First Round</h3><p>JANE DOE: Opening remark.</p>
    <p>THE MODERATOR: How was today?</p><p>JANE DOE: Good.</p>
    <p>Still improving.</p><p>Q. Tomorrow?</p><p>JANE DOE: Stay patient.</p>
    <p>FastScripts Transcript by ASAP Sports</p></div>'''
    row = prep.parse_interview(html.encode(), 'Jane Doe')
    assert row['explicit_round'] == '1'
    assert row['interview_date'] == '2024-05-23'
    assert row['segments'] == [
        {'order': 0, 'question': '', 'answer': 'Opening remark.'},
        {'order': 1, 'question': 'How was today?', 'answer': 'Good. Still improving.'},
        {'order': 2, 'question': 'Tomorrow?', 'answer': 'Stay patient.'},
    ]


def test_other_speakers_never_become_the_named_golfers_answers():
    raw = b'''<div><h1>Open</h1><h2>May 23, 2024</h2>
    <p>JANE DOE: My opening remarks.</p>
    <p>John Doe: Another person's comments.</p><p>More from that person.</p>
    <p>JANE DOE: My response.</p><p>John Doe: Thank you.</p></div>'''
    row = prep.parse_interview(raw, 'Jane Doe')
    assert row['parse_status'] == 'ok'
    assert row['other_speaker_names'] == ['John Doe']
    assert row['segments'] == [
        {'order': 0, 'question': '', 'answer': 'My opening remarks.'},
        {'order': 1, 'question': "Another person's comments. More from that person.", 'answer': 'My response.'},
    ]


def test_missing_header_and_missing_named_player_remain_visible():
    assert prep.parse_interview(b'<p>broken</p>', 'Jane Doe')['parse_status'] == 'missing_header'
    raw = b'<div><h1>Open</h1><h2>May 23, 2024</h2><p>JOHN DOE: Hi.</p></div>'
    result = prep.parse_interview(raw, 'Jane Doe')
    assert result['parse_status'] == 'no_player_answers'
    assert result['segments'] == []


def test_scores_keep_full_field_partial_rounds_and_detect_conflicts():
    rows = [dict(player_id=p, player_name=p, round=r, hole=h, score=4, par=4)
            for p,r,n in [('a',4,18),('b',2,9)] for h in range(1,n+1)]
    scores = prep.round_scores(pd.DataFrame(rows), '2024:open', 'e', '2024')
    assert scores.strokes.tolist()[0] == 72
    assert scores.complete.tolist() == [True,False]
    assert pd.isna(scores.iloc[1].strokes)
    rows.append(dict(rows[0],score=5))
    assert not prep.round_scores(pd.DataFrame(rows), '2024:open', 'e', '2024').iloc[0].complete


@pytest.mark.parametrize('label,introduction', [
    ('The Moderator', 'Today?'),
    ('Alex Host', 'How are things?'),
    ('Alex Host', 'We welcome Jane Doerr to the room.'),
    ('Alex Host', "Let's begin."),
])
def test_other_speakers_require_no_name_list_or_intro_phrase(label, introduction):
    raw = f'''<div><h1>Open</h1><h2>May 23, 2024</h2>
    <p>{label}: {introduction}</p><p>Jane Doe: Good.</p></div>'''
    row = prep.parse_interview(raw.encode(), 'Jane Doe')
    assert row['parse_status'] == 'ok'
    assert row['segments'] == [{'order': 0, 'question': introduction, 'answer': 'Good.'}]


def test_doug_milne_thanks_for_joining_us_does_not_reject_rory_interview():
    raw = b'''<div><h1>Arnold Palmer Invitational</h1><h2>March 18, 2015</h2>
    <p>DOUG MILNE: Rory McIlroy, thanks for joining us for a few minutes.</p>
    <p>RORY MCILROY: Delighted to be here.</p><p>DOUG MILNE: We'll take questions.</p>
    <p>Q. What do you think of the course?</p><p>RORY MCILROY: I really like it.</p>
    <p>DOUG MILNE: Thanks for your time.</p></div>'''
    row = prep.parse_interview(raw, 'Rory McIlroy')
    assert row['parse_status'] == 'ok'
    assert row['other_speaker_names'] == ['DOUG MILNE']
    assert row['segments'] == [
        {'order': 0, 'question': 'Rory McIlroy, thanks for joining us for a few minutes.',
         'answer': 'Delighted to be here.'},
        {'order': 1, 'question': 'What do you think of the course?', 'answer': 'I really like it.'},
    ]


def test_legacy_line_break_transcripts_keep_qa_and_speaker_boundaries():
    raw = b'''<td><h1>Open</h1><br><h2>July 31, 2015</h2><br>
    <h3><a>Jane Doe</a></h3><br><i>Location</i><p></p><br>
    <b>Q. </b><b>How was today?</b><br>JANE DOE: Good.<br>
    Continued answer.<br>ALEX HOST: What about tomorrow?<br>
    JANE DOE: Stay patient.<br><strong>FastScripts Transcript by ASAP Sports</strong></td>'''
    row = prep.parse_interview(raw, 'Jane Doe')
    assert row['parse_status'] == 'ok'
    assert row['segments'] == [
        {'order': 0, 'question': 'How was today?', 'answer': 'Good. Continued answer.'},
        {'order': 1, 'question': 'What about tomorrow?', 'answer': 'Stay patient.'},
    ]


def test_named_host_intro_can_span_multiple_paragraphs():
    raw = b'''<div><h1>Open</h1><h2>May 23, 2024</h2>
    <p>ALEX HOST: We will get started.</p><p>Tell us about your round.</p>
    <p>JANE DOE: Good.</p></div>'''
    result = prep.parse_interview(raw, 'Jane Doe')
    assert result['parse_status'] == 'ok'
    assert result['segments'] == [{'order': 0,
        'question': 'We will get started. Tell us about your round.', 'answer': 'Good.'}]


def test_double_encoded_nbsp_padding_does_not_hide_player_or_question_labels():
    # ASAP 107474 pads some speaker/question labels with UTF-8 bytes for "Â ".
    import hashlib
    pad = b'\xc3\x82\xc2\xa0' * 6
    raw = (b'<td><h1>Open</h1><h2>March 18, 2015</h2><br>'
           b'DOUG MILNE: Thanks for joining us.<br>RORY MCILROY: Happy to be here.<br>'
           + pad + b'Q. What did you shoot?<br>'
           + pad + b"RORY MCILROY: It wasn't the course record.<br></td>")
    result = prep.parse_interview(raw, 'Rory McIlroy')
    assert result['parse_status'] == 'ok'
    assert result['source_hash'] == hashlib.sha256(raw).hexdigest()
    assert result['other_speaker_names'] == ['DOUG MILNE']
    assert result['segments'][-1] == {'order': 1, 'question': 'What did you shoot?',
                                    'answer': "It wasn't the course record."}
