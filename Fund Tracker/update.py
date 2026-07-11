import argparse
import time
from datetime import date, timedelta

import pandas as pd
import yfinance as yf

from db import get_db, init_db

YEARS_BACK = 10
OVERLAP_DAYS = 5  # re-fetch a few trailing days on incremental updates to catch late corrections
REQUEST_DELAY = 0.3  # seconds between yfinance calls


def add_symbols(conn, symbols):
    added = []
    for raw in symbols:
        symbol = raw.strip().upper()
        if not symbol:
            continue

        fund_type = "unknown"
        try:
            info = yf.Ticker(symbol).info
            quote_type = info.get("quoteType")
            if quote_type:
                fund_type = quote_type.lower()
        except Exception as e:
            print(f"  warning: could not look up {symbol}: {e}")

        cur = conn.execute(
            "INSERT OR IGNORE INTO symbols (symbol, type) VALUES (?, ?)",
            (symbol, fund_type),
        )
        if cur.rowcount:
            added.append(symbol)
        else:
            conn.execute("UPDATE symbols SET active = 1 WHERE symbol = ?", (symbol,))

        time.sleep(REQUEST_DELAY)

    conn.commit()
    return added


def fetch_prices(symbol, start, end):
    return yf.Ticker(symbol).history(
        start=start.isoformat(), end=end.isoformat(), auto_adjust=False
    )


def upsert_prices(conn, symbol_id, df):
    if df is None or df.empty:
        return 0

    rows = []
    for idx, row in df.iterrows():
        close = row.get("Close")
        if pd.isna(close):
            continue
        rows.append((
            symbol_id,
            idx.strftime("%Y-%m-%d"),
            _clean(row.get("Open")),
            _clean(row.get("High")),
            _clean(row.get("Low")),
            _clean(close),
            _clean(row.get("Adj Close")),
            _clean(row.get("Volume")),
        ))

    if not rows:
        return 0

    conn.executemany(
        """INSERT OR REPLACE INTO prices
           (symbol_id, date, open, high, low, close, adj_close, volume)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        rows,
    )
    conn.commit()
    return len(rows)


def _clean(value):
    if value is None or pd.isna(value):
        return None
    return float(value)


def update_all(conn):
    today = date.today()
    symbols = conn.execute(
        "SELECT id, symbol FROM symbols WHERE active = 1 ORDER BY symbol"
    ).fetchall()

    for row in symbols:
        symbol_id, symbol = row["id"], row["symbol"]
        last_date = conn.execute(
            "SELECT MAX(date) AS max_date FROM prices WHERE symbol_id = ?",
            (symbol_id,),
        ).fetchone()["max_date"]

        if last_date is None:
            start = today - timedelta(days=365 * YEARS_BACK)
        else:
            start = date.fromisoformat(last_date) - timedelta(days=OVERLAP_DAYS)

        try:
            df = fetch_prices(symbol, start, today + timedelta(days=1))
            n = upsert_prices(conn, symbol_id, df)
            print(f"  {symbol}: {n} rows ({start} -> {today})")
        except Exception as e:
            print(f"  {symbol}: FAILED - {e}")

        time.sleep(REQUEST_DELAY)


def main():
    parser = argparse.ArgumentParser(
        description="Track daily mutual fund / ETF prices in a local SQLite database"
    )
    parser.add_argument(
        "--add", nargs="+", metavar="SYMBOL",
        help="Add new symbol(s) to track (e.g. --add VFIAX SPY) and backfill their history",
    )
    args = parser.parse_args()

    init_db()
    conn = get_db()
    try:
        if args.add:
            added = add_symbols(conn, args.add)
            print(f"Added: {', '.join(added)}" if added else "No new symbols added (already tracked).")

        print("Updating prices...")
        update_all(conn)
        print("Done.")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
