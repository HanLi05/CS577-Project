"""Prepare sources, assign interview stages and rounds, and build the dataset."""
import argparse
from pathlib import Path

from .preprocessing import prepare, build
from .alignment import align


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['prepare', 'align', 'build'])
    parser.add_argument('--root', type=Path, default=Path('.'), help='Project directory (default: current directory)')
    parser.add_argument('--years', help='Discover event inventory for a year or inclusive range, e.g. 2015:2025')
    parser.add_argument('--offline', action='store_true', help='Use cached sources only')
    args = parser.parse_args()
    if args.command in ('align', 'build'):
        if args.years or args.offline:
            parser.error('--years and --offline apply to prepare; align/build are always local')
        (align if args.command == 'align' else build)(args.root)
        return
    years = []
    if args.years:
        try:
            parts = [int(part) for part in args.years.split(':')]
            if len(parts) not in (1, 2) or not 1900 <= parts[0] <= parts[-1] <= 2100:
                raise ValueError
            years = list(range(parts[0], parts[-1] + 1))
        except ValueError:
            parser.error('--years must be a year or an ascending range such as 2015:2025')
    prepare(args.root, offline=args.offline, years=years)


if __name__ == '__main__':
    main()
