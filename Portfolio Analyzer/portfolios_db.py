import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "portfolios.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS portfolios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                rebalance_freq TEXT NOT NULL DEFAULT 'annual',
                created_date TEXT NOT NULL DEFAULT (date('now'))
            );

            CREATE TABLE IF NOT EXISTS holdings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                portfolio_id INTEGER NOT NULL,
                symbol TEXT NOT NULL,
                weight_pct REAL NOT NULL,
                UNIQUE(portfolio_id, symbol),
                FOREIGN KEY (portfolio_id) REFERENCES portfolios(id) ON DELETE CASCADE
            );
        """)
        conn.commit()
    finally:
        conn.close()


def list_portfolios(conn):
    return conn.execute("SELECT * FROM portfolios ORDER BY name").fetchall()


def get_holdings(conn, portfolio_id):
    return conn.execute(
        "SELECT symbol, weight_pct FROM holdings WHERE portfolio_id = ? ORDER BY symbol",
        (portfolio_id,),
    ).fetchall()


def save_portfolio(conn, name, rebalance_freq, holdings):
    """holdings: dict[symbol] -> weight_pct. Creates the portfolio, or replaces its holdings if the name exists."""
    existing = conn.execute("SELECT id FROM portfolios WHERE name = ?", (name,)).fetchone()
    if existing:
        portfolio_id = existing["id"]
        conn.execute(
            "UPDATE portfolios SET rebalance_freq = ? WHERE id = ?",
            (rebalance_freq, portfolio_id),
        )
        conn.execute("DELETE FROM holdings WHERE portfolio_id = ?", (portfolio_id,))
    else:
        cur = conn.execute(
            "INSERT INTO portfolios (name, rebalance_freq) VALUES (?, ?)",
            (name, rebalance_freq),
        )
        portfolio_id = cur.lastrowid

    conn.executemany(
        "INSERT INTO holdings (portfolio_id, symbol, weight_pct) VALUES (?, ?, ?)",
        [(portfolio_id, symbol, weight) for symbol, weight in holdings.items()],
    )
    conn.commit()
    return portfolio_id


def delete_portfolio(conn, portfolio_id):
    conn.execute("DELETE FROM holdings WHERE portfolio_id = ?", (portfolio_id,))
    conn.execute("DELETE FROM portfolios WHERE id = ?", (portfolio_id,))
    conn.commit()
