import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "fund_tracker.db"


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS symbols (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol TEXT NOT NULL UNIQUE,
                type TEXT NOT NULL DEFAULT 'unknown',
                added_date TEXT NOT NULL DEFAULT (date('now')),
                active INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                symbol_id INTEGER NOT NULL,
                date TEXT NOT NULL,
                open REAL,
                high REAL,
                low REAL,
                close REAL,
                adj_close REAL,
                volume INTEGER,
                UNIQUE(symbol_id, date),
                FOREIGN KEY (symbol_id) REFERENCES symbols(id)
            );

            CREATE INDEX IF NOT EXISTS idx_prices_symbol_date ON prices(symbol_id, date);
        """)
        conn.commit()
    finally:
        conn.close()
