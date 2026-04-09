# 🎯 Dartboard Bracket Tournament App

An interactive Streamlit application for running a college basketball tournament bracket using dartboard throws to determine winners. Instead of predicting winners, each matchup winner is determined by throwing darts at a dartboard and matching the thrown number to team assignments.

## Overview

This app streamlines the dartboard bracket experience by:
- **Reading CBB Rankings** to calculate win probabilities for each matchup
- **Assigning dartboard numbers** to each team based on those probabilities (better teams get more favorable numbers)
- **Walking you through each matchup** one at a time
- **Recording dart throws and winners** with clickable buttons
- **Automatically progressing** through all tournament rounds (64 → 32 → 16 → 8 → 4 → 2 → 1)
- **Logging results** to a timestamped file with round information
- **Supporting undo** if you misclick

## Data Inputs Required

The app requires one CSV file in the same directory:

### `CBB Rankings - 2026.csv`
A CSV file with the following columns:
- `Team` - Team name
- `Bracket Order` - Initial bracket ordering
- `Seed` - Tournament seed
- `Ken Pom` - KenPom ranking
- `Off Eff` - Offensive efficiency ranking
- `Def Eff` - Defensive efficiency ranking
- `NET Ranking` - NET ranking

**Example structure:**
```
Team,Bracket Order,Seed,Ken Pom,Off Eff,Def Eff,NET Ranking
Duke,1,1,1,4,2,1
Siena,2,16,192,210,175,183
Ohio St.,3,8,26,17,54,29
...
```

The app uses the first 64 teams from this file for the initial Round of 64 bracket.

## Setup & Installation

### 1. Install Dependencies
```bash
pip install streamlit pandas
```

### 2. Quick Start - Using the Launcher Script
```bash
cd /path/to/Dartboard\ Bracket
./run_app.sh
```

### 3. Alternative - Manual Launch
```bash
cd /path/to/Dartboard\ Bracket
source ../.venv/bin/activate
streamlit run dartboard_app.py
```

The app will open automatically in your default browser at `http://localhost:8501`

## How to Use the App

### Main Tournament Screen
1. **See the current matchup** with two teams
2. **View win probabilities** for each team (calculated from rankings)
3. **See assigned dartboard numbers** - each team gets specific numbers (1-20) distributed by probability

### Recording a Dart Throw
1. **Throw your dart** at the physical dartboard
2. **Click the button** corresponding to the number hit with the team name displayed
   - Example: If you hit 7 and it's assigned to Duke, click the "7 - Duke" button
3. The app automatically records the winner and moves to the next matchup

### Tournament Progression
- **Round of 64** → 32 matchups
- **Round of 32** → 16 matchups
- **Sweet 16** → 8 matchups
- **Elite 8** → 4 matchups
- **Final 4** → 2 matchups
- **Championship** → 1 matchup
- **Champion** → Tournament complete!

### Sidebar Status
The sidebar shows:
- Current round name and matchup number
- Recent tournament log entries (last 10)

### Undo Feature
- Click **↶ Undo** to revert the last result
- Returns to the previous matchup
- Removes the entry from your log file

## Output Files

When you initialize the app, it creates a timestamped log file:
```
bracket_results_20260409_143022.txt
```

This file contains:
```
Dartboard Bracket Tournament Log
Started: 2026-04-09 14:30:22
============================================================

Round of 64 - Duke vs Siena: Dart #20 → Duke wins
Round of 64 - Ohio St. vs TCU: Dart #1 → Ohio St. wins
Round of 32 - Duke vs Ohio St.: Dart #19 → Duke wins
...
============================================================
CHAMPION: Duke
Tournament Completed: 2026-04-09 15:47:33
```

## Algorithm Details

### Win Probability Calculation
For each matchup, probabilities are calculated from rankings:
```
team_score = Seed*4 + KenPom + Off_Eff + Def_Eff + NET_Ranking
(lower scores are better)

win_probability = 1 - (team_score / total_score)
```

### Dartboard Number Assignment
- The app uses an optimization algorithm to distribute dartboard numbers (1-20) between teams
- Better teams (higher win probability) get more dartboard numbers
- Numbers are weighted by their value on a standard dartboard (inner/outer rings)
- The distribution tries to match the win probability as closely as possible

## Features

✅ Interactive matchup-by-matchup gameplay  
✅ Clickable dartboard buttons with team names  
✅ Automatic probability and number calculations  
✅ Timestamped tournament logging  
✅ Undo functionality  
✅ Tournament progress tracking  
✅ Beautiful Streamlit UI  

## File Structure

```
Dartboard Bracket/
├── dartboard_app.py              # Main Streamlit app
├── run_app.sh                    # Launcher script (executable)
├── CBB Rankings - 2026.csv       # Input: Team rankings data
├── README.md                     # This file
├── bracket_results_*.txt         # Output: Tournament logs (created each run)
└── [other supporting files]
```

## Troubleshooting

### "command not found: streamlit"
Make sure you've installed streamlit and are using the correct Python environment:
```bash
pip install streamlit
```

### "No such file or directory: CBB Rankings - 2026.csv"
Make sure the CSV file is in the same directory as `dartboard_app.py` (the Dartboard Bracket folder).

### App won't open
Try running directly with:
```bash
streamlit run dartboard_app.py
```

## Tips for Best Experience

- Have your physical dartboard set up and ready
- Run the app full-screen for easier button clicking
- Keep a notebook handy if you want to track other stats
- The undo button is your friend if you misclick!

## Version

Dartboard Bracket v1.0 | CBB Tournament 2026

## Author

Created for an interactive college basketball tournament experience using dartboard throws.
