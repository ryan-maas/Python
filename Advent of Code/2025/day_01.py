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
L68
L30
R48
L5
R60
L55
L1
L99
R14
L82
"""


def parse_input(text: str) -> Any:
    """Parse raw input text into a convenient data structure.
    Default: list of ints (one per line).
    Modify this for each day's input format.
    """
    return [line for line in text.strip().splitlines() if line.strip()]


def part1(data: Any) -> Any:
    """Solve part 1. Return the answer."""
    dial_location = 50
    zero_stop_counter = 0
    for rotation in data:
        direction = rotation[0]
        amount = int(rotation[1:])
        if direction == 'L':
            dial_location = (dial_location - amount) % 100
        elif direction == 'R':
            dial_location = (dial_location + amount) % 100
        
        if dial_location == 0: zero_stop_counter += 1

    return zero_stop_counter


def part2(data: Any) -> Any:
    """Solve part 2. Return the answer."""
    #dial_location = 50
    pos = 50
    count = 0
    
    for instruction in data:
        direction = instruction[0]
        amount = int(instruction[1:])
        
        if direction == 'L':
            # Left rotation: decrease position
            # Count complete cycles through 0
            complete_cycles = amount // 100
            count += complete_cycles
            
            if pos == 0: pos = 100  # To handle exact 0 case correctly

            # Check if we pass through 0 in the remainder
            remainder = amount % 100
            new_pos = (pos - remainder) % 100
            
            # We pass through 0 if: pos - remainder < 0 (before modulo)
            # Which means: remainder > pos
            if remainder > pos:
                count += 1
            
            pos = new_pos
            
        else:  # direction == 'R'
            # Right rotation: increase position
            # Count complete cycles through 0
            complete_cycles = amount // 100
            count += complete_cycles
            
            # Check if we pass through 0 in the remainder
            remainder = amount % 100
            new_pos = (pos + remainder) % 100
            
            # We pass through 0 if: pos + remainder >= 100 (before modulo)
            # Which means: new_pos < pos (after modulo, we wrapped)
            if pos + remainder > 100:
                count += 1
            
            pos = new_pos
        
        # Check if we ended exactly on 0
        if pos == 0:
            count += 1
        print(pos, count)
    return count


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
