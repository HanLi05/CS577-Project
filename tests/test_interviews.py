import pytest
from golf_interviews.interviews import parse_interview


def page(body, headings='<h3>Jane Doe</h3><h3>Quick Quotes</h3>'):
    return f'<td><h1>Event</h1><h2>May 24, 2024</h2>{headings}{body}<strong>FastScripts Transcript by ASAP Sports</strong></td>'


def test_structure_multiline_intro_moderator_and_negation():
    html = page('<p>THE MODERATOR: How was round two?</p><p>JANE DOE: I am not hurt.</p>'
                '<p>Still feeling good.</p><p><b>Q.</b> What about tomorrow?</p>'
                '<p>JANE DOE: I will practice.</p><p>THE MODERATOR: Thank you.</p>')
    interview, segs = parse_interview(html, 'https://www.asapsports.com/show_interview.php?id=1', 'Jane Doe')
    assert interview['interview_date'] == '2024-05-24'
    assert segs[0]['question'] == 'How was round two?'
    assert segs[0]['answer'] == 'I am not hurt. Still feeling good.'
    assert segs[1]['question'] == 'What about tomorrow?'
    assert len(segs) == 2
    assert all('FastScripts' not in s['answer'] for s in segs)


def test_missing_question_preserved_and_panel_excluded():
    _, segs = parse_interview(page('<p>JANE DOE: I feel ready.</p>'), 'https://example.org/?id=1', 'Jane Doe')
    assert segs[0]['question'] == ''
    with pytest.raises(ValueError, match='multiple_speakers'):
        parse_interview(page('<p>JANE DOE: Hi.</p><p>JOHN DOE: Hello.</p>'), 'https://example.org/?id=1', 'Jane Doe')


def test_explicit_round_header_only_not_incidental_question():
    meta, _ = parse_interview(page('<p>Q. Remember round two last year?</p><p>JANE DOE: Yes.</p>'), 'https://example.org/?id=1', 'Jane Doe')
    assert meta['explicit_round'] is None
    meta, _ = parse_interview(page('<p>JANE DOE: Hi.</p>', '<h3>Jane Doe</h3><h3>Round 2 Quick Quotes</h3>'), 'https://example.org/?id=1', 'Jane Doe')
    assert meta['explicit_round'] == 2


@pytest.mark.parametrize('name,label', [('Rory McIlroy','RORY McILROY'),('Ludvig Aberg','LUDVIG Ă…BERG')])
def test_mixed_case_and_source_encoding_speaker_labels(name,label):
    _, segments = parse_interview(page(f'<p>Q. How was today?</p><p>{label}: I played well.</p>'), 'https://example.org/?id=1',name)
    assert segments[0]['answer'] == 'I played well.'
