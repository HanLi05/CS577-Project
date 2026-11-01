"""Run with python -m golf_interviews.cli (or installed golf-data)."""
import argparse
from pathlib import Path
import yaml
from .collect import collect


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['collect', 'build', 'run', 'train'])
    parser.add_argument('--config', default='configs/data.yaml')
    parser.add_argument('--offline', action='store_true', help='Use verified cached sources only')
    args = parser.parse_args()
    config = yaml.safe_load(Path(args.config).read_text())
    if args.command in ('collect', 'run'):
        collect(config, offline=args.offline)
    if args.command in ('build', 'run'):
        from .pipeline import build
        build(config)
    if args.command == 'train':
        # Training reads existing prepared data; it does not collect or rebuild it.
        from .training import train_pilot
        train_pilot(config)


if __name__ == '__main__':
    main()
