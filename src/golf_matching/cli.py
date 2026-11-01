"""Two commands: prepare suggestions, then export your reviewed matches."""
import argparse
import hashlib
import json
from pathlib import Path
import pandas as pd
import yaml
from .candidates import prepare
from .review import read_csv,export_reviews


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['prepare','export'])
    parser.add_argument('--config',default='configs/charles-schwab-2024.yaml')
    parser.add_argument('--offline',action='store_true')
    args=parser.parse_args()
    config=yaml.safe_load(Path(args.config).read_text())
    if args.command=='prepare':
        prepare(config,args.offline)
    else:
        directory=Path(config['output_dir'])
        snapshot=json.loads((directory/'inputs.json').read_text())
        if (snapshot['event_id']!=str(config['event_id']) or snapshot['year']!=config['year']
            or snapshot['round_dates']!={str(r):str(d) for r,d in config['round_dates'].items()}):
            raise ValueError('Configuration changed; run prepare again before export')
        for name in ('candidates.csv','scoring_rounds.csv'):
            if hashlib.sha256((directory/name).read_bytes()).hexdigest()!=snapshot['files'][name]:
                raise ValueError(f'Generated input changed: {name}; run prepare again')
        scores=pd.read_csv(directory/'scoring_rounds.csv',dtype={'event_id':str,'player_id':str,'round':str})
        # Do not interpret the string "False" as a truthy completion flag.
        if not scores.complete.astype(str).str.lower().isin(['true','false']).all():
            raise ValueError('Invalid scoring completion flags')
        scores['complete']=scores.complete.astype(str).str.lower().eq('true')
        approved,status=export_reviews(read_csv(directory/'candidates.csv'),directory/'review.csv',scores,
                                       {int(r):str(d) for r,d in config['round_dates'].items()})
        approved.to_csv(directory/'approved_links.csv',index=False)
        status.to_csv(directory/'status.csv',index=False)
        print(f'{len(approved)} approved links. Decisions and eligibility: {directory / "status.csv"}')


if __name__=='__main__':
    main()
