# Fund Tracker

A command-line tool that builds and maintains a local SQLite database of daily
mutual fund and ETF prices. Backfills 10 years of history for new symbols and
does cheap incremental updates on symbols you're already tracking.

## Setup

**Requirements:** Python 3.10+

```bash
cd "Fund Tracker"
pip install -r requirements.txt
```

The SQLite database (`fund_tracker.db`) is created automatically on first run.

## Usage

**Add symbols and backfill their history** (10 years by default):

```bash
python update.py --add SPY VFIAX VTSAX QQQ
```

Fund type (`etf` vs `mutualfund`) is detected automatically from Yahoo Finance.

**Daily update** — refresh all tracked symbols since their last recorded date:

```bash
python update.py
```

Running `update.py` with no arguments is idempotent and safe to run multiple
times a day — each symbol's fetch window overlaps the last 5 stored days to
catch late price corrections, and duplicate `(symbol, date)` rows are
overwritten rather than duplicated.

`--add` and a full update can be combined in one call — newly added symbols
get backfilled, existing ones get their incremental refresh, in the same run:

```bash
python update.py --add IVV
```

## Schema

```
symbols(id, symbol, type, added_date, active)
prices(id, symbol_id, date, open, high, low, close, adj_close, volume)
```

`adj_close` reflects dividend reinvestment and is the right column to use for
total-return comparisons over time — mutual funds in particular should be
compared on `adj_close`, not `close`. Mutual fund `volume` is always `0`; that's
expected, not a bug.

## Scheduling

To run automatically once a day after market close, use `launchd`
(more reliable across sleep/wake than `cron` on macOS). Example
`~/Library/LaunchAgents/com.fundtracker.update.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.fundtracker.update</string>
  <key>ProgramArguments</key>
  <array>
    <string>/Users/maas/Documents/GitHub/Python/.venv/bin/python</string>
    <string>/Users/maas/Documents/GitHub/Python/Fund Tracker/update.py</string>
  </array>
  <key>WorkingDirectory</key>
  <string>/Users/maas/Documents/GitHub/Python/Fund Tracker</string>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key><integer>18</integer>
    <key>Minute</key><integer>0</integer>
  </dict>
  <key>StandardOutPath</key><string>/tmp/fund_tracker.log</string>
  <key>StandardErrorPath</key><string>/tmp/fund_tracker.log</string>
</dict>
</plist>
```

Load it with `launchctl load ~/Library/LaunchAgents/com.fundtracker.update.plist`.

## Project Structure

```
Fund Tracker/
├── db.py              # SQLite schema and connection helper
├── update.py          # add symbols, backfill, and daily update logic
├── requirements.txt
└── fund_tracker.db    # created on first run (gitignored)
```
