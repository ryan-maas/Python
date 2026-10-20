import sqlite3
from pathlib import Path

import pandas as pd

FUND_TRACKER_DB = Path(__file__).parent.parent / "Fund Tracker" / "fund_tracker.db"


def _get_price_db():
    conn = sqlite3.connect(f"file:{FUND_TRACKER_DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def get_tracked_symbols():
    """Returns [(symbol, type), ...] for all actively tracked symbols in Fund Tracker."""
    conn = _get_price_db()
    try:
        rows = conn.execute(
            "SELECT symbol, type FROM symbols WHERE active = 1 ORDER BY symbol"
        ).fetchall()
        return [(r["symbol"], r["type"]) for r in rows]
    finally:
        conn.close()


def missing_symbols(symbols):
    """Subset of `symbols` not currently tracked in Fund Tracker."""
    tracked = {s for s, _ in get_tracked_symbols()}
    return [s for s in symbols if s not in tracked]


def load_price_series(symbols):
    """Loads adj_close history for `symbols` as a DataFrame (date index, one column per symbol).

    Raises ValueError listing any symbols not yet tracked in Fund Tracker.
    """
    missing = missing_symbols(symbols)
    if missing:
        raise ValueError(
            f"Not tracked in Fund Tracker yet: {', '.join(missing)}. "
            f"Run `python update.py --add {' '.join(missing)}` in the Fund Tracker project first."
        )

    conn = _get_price_db()
    try:
        placeholders = ",".join("?" * len(symbols))
        query = f"""
            SELECT s.symbol, p.date, p.adj_close
            FROM prices p
            JOIN symbols s ON s.id = p.symbol_id
            WHERE s.symbol IN ({placeholders})
            ORDER BY p.date
        """
        df = pd.read_sql_query(query, conn, params=symbols, parse_dates=["date"])
    finally:
        conn.close()

    wide = df.pivot(index="date", columns="symbol", values="adj_close")
    # forward-fill mismatched trading-day gaps (e.g. mutual fund vs ETF holiday quirks),
    # then drop rows before every symbol has data (truncates to the shortest common history)
    wide = wide.ffill().dropna()
    return wide
