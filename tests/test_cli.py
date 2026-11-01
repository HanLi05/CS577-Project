import json
import hashlib
import pandas as pd
import pytest
import yaml
from golf_matching.cli import main
from golf_matching.review import sync_review
from test_review import candidates,scores,approve


def test_export_checks_source_files_and_config_without_editing_reviews(tmp_path,monkeypatch):
    directory=tmp_path/'matching';directory.mkdir()
    config={'output_dir':str(directory),'event_id':'e','year':2024,'round_dates':{1:'2024-05-23',2:'2024-05-24'}}
    path=tmp_path/'config.yaml';path.write_text(yaml.safe_dump(config))
    c=candidates();c.to_csv(directory/'candidates.csv',index=False)
    scores().to_csv(directory/'scoring_rounds.csv',index=False)
    sync_review(c,directory/'review.csv');approve(directory/'review.csv')
    snapshot={'event_id':'e','year':2024,'round_dates':{'1':'2024-05-23','2':'2024-05-24'},
              'files':{name:hashlib.sha256((directory/name).read_bytes()).hexdigest() for name in ['candidates.csv','scoring_rounds.csv']}}
    (directory/'inputs.json').write_text(json.dumps(snapshot))
    monkeypatch.setattr('sys.argv',['golf-match','export','--config',str(path)])
    before=(directory/'review.csv').read_bytes()
    main()
    assert len(pd.read_csv(directory/'approved_links.csv'))==1
    assert (directory/'review.csv').read_bytes()==before
    config['round_dates'][1]='2024-05-22';path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError,match='prepare'):
        main()
    config['round_dates'][1]='2024-05-23';path.write_text(yaml.safe_dump(config))
    (directory/'scoring_rounds.csv').write_text('changed')
    with pytest.raises(ValueError,match='changed'):
        main()
