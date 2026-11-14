"""Build a JSON route from the prepared Jezero arrays."""

import argparse
import json
from pathlib import Path

from . import load_jezero_grid, plan_route


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", nargs=2, type=float, metavar=("LON", "LAT"), required=True)
    parser.add_argument("--end", nargs=2, type=float, metavar=("LON", "LAT"), required=True)
    parser.add_argument("--data-dir", type=Path, default=Path("data/processed"))
    parser.add_argument("--prefix", default="jezero")
    parser.add_argument("--mode", choices=("astar", "hierarchical"), default="astar")
    parser.add_argument("--max-slope", type=float, default=15.0)
    parser.add_argument("--slope-weight", type=float, default=1.0)
    parser.add_argument("--block-size", type=int, default=16)
    args = parser.parse_args()
    try:
        grid = load_jezero_grid(args.data_dir, args.prefix)
        result = plan_route(*grid, tuple(args.start), tuple(args.end), mode=args.mode,
                            max_slope_deg=args.max_slope, slope_weight=args.slope_weight,
                            block_size=args.block_size)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, allow_nan=False))


if __name__ == "__main__":
    main()
