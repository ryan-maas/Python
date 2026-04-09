"""Simple runner to execute a day's script in a subprocess.
Usage:
  python run_day.py "Day 1.py" -- --input inputs/day1.txt --part all
Put `--` before the target script args so they are forwarded.
"""
import sys
import subprocess
from pathlib import Path
import argparse

p = argparse.ArgumentParser()
p.add_argument('script', type=Path, help='Path to the day script to run')
p.add_argument('rest', nargs=argparse.REMAINDER, help='Arguments to forward to the script (prefix with --)')
args = p.parse_args()

if not args.script.exists():
    print(f"Script not found: {args.script}")
    sys.exit(1)

cmd = [sys.executable, str(args.script)] + args.rest
print('Running:', ' '.join(cmd))
res = subprocess.run(cmd)
sys.exit(res.returncode)
