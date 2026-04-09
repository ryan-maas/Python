"""
Advent of Code solver template.
Usage:
  python day_template.py --input inputs/day1.txt --part all

Copy/rename this file for each day (e.g., day_01.py) and implement
`parse_input`, `part1`, and `part2`.
"""
from pathlib import Path
import argparse
import time
from typing import Any

EXAMPLE = """
1721
979
366
299
675
1456
"""


def parse_input(text: str) -> Any:
    """Parse raw input text into a convenient data structure.
    Default: list of ints (one per line).
    Modify this for each day's input format.
    """
    return [int(line) for line in text.strip().splitlines() if line.strip()]


def part1(data: Any) -> Any:
    """Solve part 1. Return the answer."""
    raise NotImplementedError("Implement part1")


def part2(data: Any) -> Any:
    """Solve part 2. Return the answer."""
    raise NotImplementedError("Implement part2")


def run(text: str, which: str) -> None:
    data = parse_input(text)
    results = {}
    if which in ("1", "all"):
        start = time.perf_counter()
        results['part1'] = part1(data)
        results['time1'] = time.perf_counter() - start
    if which in ("2", "all"):
        start = time.perf_counter()
        results['part2'] = part2(data)
        results['time2'] = time.perf_counter() - start

    if 'part1' in results:
        print(f"Part 1: {results['part1']} (t={results['time1']:.4f}s)")
    if 'part2' in results:
        print(f"Part 2: {results['part2']} (t={results['time2']:.4f}s)")


def main() -> None:
    p = argparse.ArgumentParser(description="Advent of Code day runner")
    p.add_argument('--input', '-i', type=Path, help='Path to input file')
    p.add_argument('--part', choices=['1', '2', 'all'], default='all')
    p.add_argument('--example', action='store_true', help='Run with built-in example')
    args = p.parse_args()

    if args.example:
        text = EXAMPLE
    else:
        input_path = args.input or (Path(__file__).parent / 'inputs' / 'day1.txt')
        if not input_path.exists():
            raise SystemExit(f"Input file not found: {input_path}")
        text = input_path.read_text()

    run(text, args.part)


if __name__ == '__main__':
    main()
