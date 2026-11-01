from golf_interviews.collect import scoreboard_rounds, eligible_day_links


def test_scoreboard_rounds_preserves_cut_rounds_and_filters_other_events():
    data = {'events': [{'id': 'e', 'competitions': [{'competitors': [
        {'id': '1', 'athlete': {'displayName': 'A'}, 'status': {'type': {'name': 'STATUS_CUT'}},
         'linescores': [{'period': 1, 'value': 72, 'linescores': [{'period': h, 'value': 4} for h in range(1,19)]}]}
    ]}]}]}
    rounds = scoreboard_rounds(data, 'e')
    assert rounds[0]['expected_strokes'] == 72
    assert rounds[0]['holes_completed'] == 18
    assert scoreboard_rounds(data, 'other') == []


def test_collection_does_not_treat_navigation_or_practice_days_as_rounds():
    links = [('Archive', 'https://example.org/show_event.php'),
             ('Event', 'https://example.org/show_event.php?date=2024-5-21'),
             ('Event', 'https://example.org/show_event.php?date=2024-5-23')]
    assert eligible_day_links(links, '2024-05-23', '2024-05-26') == [links[2]]


def test_team_competitors_do_not_become_individual_rounds():
    assert scoreboard_rounds({'id':'e','competitions':[{'competitors':[{'id':'team','team':{'displayName':'Team'},'linescores':[{'period':1,'value':60}]}]}]},'e') == []
