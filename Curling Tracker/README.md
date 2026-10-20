# Curling Tracker

A mobile-friendly web app for tracking curling shots live during a game. Built with Flask and SQLite — no external services required.

## Features

- **Live shot tracking** — record every throw: weight call, turn, line, and result score
- **Flexible lineup** — track both teams or home team only; away lineup is optional
- **Shot detail** — log the called weight and actual weight thrown separately
- **End scoring** — enter the score after each end; hammer is tracked automatically
- **Game stats** — per-player shooting percentage, result distribution bar, and breakdown by shot type (Guard / Draw / Takeout)
- **Scoreline** — full end-by-end scoreline with hammer indicator
- **Player roster** — maintain a saved roster for autocomplete when setting up games
- **Export** — download shot data as CSV or JSON per game, or across a date range from the home screen
- **Delete games** — remove a game and all its data with a confirmation prompt

## Shot Scoring

Each shot is scored 0–4:

| Score | Label   |
|-------|---------|
| 4     | Perfect |
| 3     | Good    |
| 2     | Fair    |
| 1     | Poor    |
| 0     | Miss    |

Shooting percentage = `(total score / (shots × 4)) × 100`

## Weight Call Groups (Stats)

Individual weight calls are grouped in the stats view:

| Group   | Weight Calls          |
|---------|-----------------------|
| Guard   | 1, 2, 3               |
| Draw    | 4, 5, 6, 7, 8, 9, 10 |
| Takeout | Hack, Board, Control, Normal, Peel |

## Throw Order

Ends follow standard curling throw order — Lead → Second → Vice → Skip, with away team throwing first in each pair:

```
Away Lead 1 → Home Lead 1 → Away Lead 2 → Home Lead 2
Away Second 1 → Home Second 1 → ...
Away Vice 1 → Home Vice 1 → ...
Away Skip 1 → Home Skip 1 → Away Skip 2 → Home Skip 2
```

If no away lineup is entered, only the 8 home throws are tracked per end.

## Setup

**Requirements:** Python 3.10+

```bash
cd "Curling Tracker"
pip install -r requirements.txt
python app.py
```

Open [http://localhost:5050](http://localhost:5050) on any device on the same network.

The SQLite database (`curling_stats.db`) is created automatically on first run in the same directory as `app.py`.

## Usage

1. **New Game** — enter team names, date, optional venue, who has hammer in end 1, and player names (Lead / Second / Vice / Skip for each team). Away player names are optional.
2. **Track** — for each throw, select the thrower (defaults to the expected player), weight call, turn, line, and result. Tap **Save Shot**.
3. **End Score** — after the last throw of an end, enter who scored and how many points.
4. **Stats** — available any time during or after the game from the nav bar or home screen.
5. **Export** — use the CSV or JSON buttons on the Stats page, or the date range export on the home screen.

## Roster

The **Roster** page (linked from the home screen) lets you maintain a saved list of players. Names saved here appear as autocomplete suggestions when setting up a new game. Players entered during game setup are **not** automatically added to the roster.

## Project Structure

```
Curling Tracker/
├── app.py              # Flask routes
├── db.py               # SQLite schema, queries, stats computation
├── requirements.txt
├── static/
│   └── style.css
└── templates/
    ├── base.html
    ├── index.html      # Home / game list / date range export
    ├── setup.html      # New game form
    ├── track.html      # Live shot entry
    ├── end_score.html  # End scoring
    ├── stats.html      # Post-game / in-game stats
    └── roster.html     # Player roster management
```
