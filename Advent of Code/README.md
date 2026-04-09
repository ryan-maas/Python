Advent of Code — Python template

Files added:
- `day_template.py`: reusable solver template. Copy/rename per day and implement `parse_input`, `part1`, `part2`.
- `run_day.py`: helper runner to invoke a day script and forward args.
- `inputs/day1.txt`: example input for quick testing.

Quick start

Run the template with the example data:

```bash
python "Advent of Code/day_template.py" --example
```

Run with the provided sample input:

```bash
python "Advent of Code/day_template.py" --input "Advent of Code/inputs/day1.txt" --part all
```

Use the runner to forward args (use `--` before script args):

```bash
python "Advent of Code/run_day.py" "Advent of Code/day_template.py" -- --input "Advent of Code/inputs/day1.txt" --part all
```

Recommendation

- Copy `day_template.py` to a day-specific file (e.g., `day_01.py`) and implement the two part functions.
- Keep inputs in the `inputs/` folder next to the scripts.
