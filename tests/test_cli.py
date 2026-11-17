import pandas as pd
import pytest
from golf_matching.cli import main
from test_pipeline import source_fixture,select_events


def test_prepare_and_build_commands_work_with_shared_decisions_directory(tmp_path,monkeypatch):
    source_fixture(tmp_path)
    monkeypatch.setattr('sys.argv',['golf-match','prepare','--root',str(tmp_path),'--years','2024:2025','--offline'])
    main()
    select_events(tmp_path)
    monkeypatch.setattr('sys.argv',['golf-match','prepare','--root',str(tmp_path),'--offline'])
    main()
    monkeypatch.setattr('sys.argv',['golf-match','build','--root',str(tmp_path)])
    main()
    assert pd.read_csv(tmp_path/'data/processed/matches.csv').status.tolist()==['pending','pending']


def test_invalid_year_range_fails_before_collection(monkeypatch):
    monkeypatch.setattr('sys.argv',['golf-match','prepare','--years','2025:2015'])
    with pytest.raises(SystemExit): main()
