import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "curling_stats.db"

THROW_ORDER = [
    # (position_index 0-3, stone 1-2, team 'away'/'home')
    # Throw 1-16: away/home alternating, lead->second->vice->skip
    ("lead",   1, "away"),
    ("lead",   1, "home"),
    ("lead",   2, "away"),
    ("lead",   2, "home"),
    ("second", 1, "away"),
    ("second", 1, "home"),
    ("second", 2, "away"),
    ("second", 2, "home"),
    ("vice",   1, "away"),
    ("vice",   1, "home"),
    ("vice",   2, "away"),
    ("vice",   2, "home"),
    ("skip",   1, "away"),
    ("skip",   1, "home"),
    ("skip",   2, "away"),
    ("skip",   2, "home"),
]

POSITIONS = ["lead", "second", "vice", "skip"]

WEIGHT_CALLS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10",
                "Hack", "Board", "Control", "Normal", "Peel"]

# (stored value, display label, rotation note)
TURNS = [
    ("In-turn",  "In-turn",  "↻ Clockwise"),
    ("Out-turn", "Out-turn", "↺ Counter-clockwise"),
]

LINES = ["Inside", "On Line", "Outside", "Unknown"]
RESULT_LABELS = {0: "Miss", 1: "Poor", 2: "Fair", 3: "Good", 4: "Perfect"}


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    conn = get_db()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            venue TEXT,
            hammer_first_end TEXT NOT NULL DEFAULT 'home',
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            team TEXT NOT NULL,
            position TEXT NOT NULL,
            FOREIGN KEY (game_id) REFERENCES games(id)
        );

        CREATE TABLE IF NOT EXISTS shots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            end_number INTEGER NOT NULL,
            throw_number INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            team TEXT NOT NULL,
            weight_call TEXT NOT NULL,
            turn TEXT NOT NULL,
            result_score INTEGER NOT NULL,
            notes TEXT,
            FOREIGN KEY (game_id) REFERENCES games(id),
            FOREIGN KEY (player_id) REFERENCES players(id)
        );

        CREATE TABLE IF NOT EXISTS ends (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            game_id INTEGER NOT NULL,
            end_number INTEGER NOT NULL,
            home_score INTEGER NOT NULL DEFAULT 0,
            away_score INTEGER NOT NULL DEFAULT 0,
            hammer TEXT NOT NULL,
            UNIQUE(game_id, end_number),
            FOREIGN KEY (game_id) REFERENCES games(id)
        );

        CREATE TABLE IF NOT EXISTS roster (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_position TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)
    # Migrate shots table for columns added after initial release
    for col_sql in [
        "ALTER TABLE shots ADD COLUMN line TEXT NOT NULL DEFAULT 'Unknown'",
        "ALTER TABLE shots ADD COLUMN actual_weight TEXT",
    ]:
        try:
            conn.execute(col_sql)
        except Exception:
            pass
    conn.commit()
    conn.close()


def get_game(game_id):
    conn = get_db()
    game = conn.execute("SELECT * FROM games WHERE id = ?", (game_id,)).fetchone()
    conn.close()
    return game


def get_players(game_id):
    conn = get_db()
    players = conn.execute(
        "SELECT * FROM players WHERE game_id = ? ORDER BY team, position",
        (game_id,)
    ).fetchall()
    conn.close()
    return players


def get_players_by_team(game_id):
    players = get_players(game_id)
    home = {p["position"]: p for p in players if p["team"] == "home"}
    away = {p["position"]: p for p in players if p["team"] == "away"}
    return home, away


def has_away_players(game_id):
    conn = get_db()
    count = conn.execute(
        "SELECT COUNT(*) FROM players WHERE game_id = ? AND team = 'away'",
        (game_id,)
    ).fetchone()[0]
    conn.close()
    return count > 0


def get_effective_throw_order(game_id):
    if has_away_players(game_id):
        return THROW_ORDER
    return [(pos, stone, "home") for pos, stone, team in THROW_ORDER if team == "home"]


def get_shots_for_end(game_id, end_number):
    conn = get_db()
    shots = conn.execute(
        "SELECT s.*, p.name, p.position FROM shots s JOIN players p ON s.player_id = p.id "
        "WHERE s.game_id = ? AND s.end_number = ? ORDER BY s.throw_number",
        (game_id, end_number)
    ).fetchall()
    conn.close()
    return shots


def get_all_shots(game_id):
    conn = get_db()
    shots = conn.execute(
        "SELECT s.*, p.name, p.position FROM shots s JOIN players p ON s.player_id = p.id "
        "WHERE s.game_id = ? ORDER BY s.end_number, s.throw_number",
        (game_id,)
    ).fetchall()
    conn.close()
    return shots


def get_ends(game_id):
    conn = get_db()
    ends = conn.execute(
        "SELECT * FROM ends WHERE game_id = ? ORDER BY end_number",
        (game_id,)
    ).fetchall()
    conn.close()
    return ends


def get_next_throw(game_id):
    """Return (end_number, throw_number) for the next shot to be entered."""
    max_throws = len(get_effective_throw_order(game_id))
    conn = get_db()
    row = conn.execute(
        "SELECT end_number, throw_number FROM shots WHERE game_id = ? ORDER BY end_number DESC, throw_number DESC LIMIT 1",
        (game_id,)
    ).fetchone()
    conn.close()
    if row is None:
        return 1, 1
    end, throw = row["end_number"], row["throw_number"]
    if throw >= max_throws:
        return end + 1, 1
    return end, throw + 1


def get_hammer_for_end(game_id, end_number):
    conn = get_db()
    game = conn.execute("SELECT hammer_first_end FROM games WHERE id = ?", (game_id,)).fetchone()
    ends = conn.execute(
        "SELECT * FROM ends WHERE game_id = ? AND end_number < ? ORDER BY end_number",
        (game_id, end_number)
    ).fetchall()
    conn.close()

    hammer = game["hammer_first_end"]
    for end in ends:
        # Team that scores gives up hammer; blank end keeps hammer
        if end["home_score"] > 0:
            hammer = "away"
        elif end["away_score"] > 0:
            hammer = "home"
        # blank end: hammer stays same
    return hammer


def save_shot(game_id, end_number, throw_number, player_id, team,
              weight_call, turn, result_score, line="Unknown",
              actual_weight=None, notes=""):
    conn = get_db()
    conn.execute(
        "INSERT INTO shots (game_id, end_number, throw_number, player_id, team, "
        "weight_call, turn, result_score, line, actual_weight, notes) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (game_id, end_number, throw_number, player_id, team,
         weight_call, turn, result_score, line, actual_weight or None, notes)
    )
    conn.commit()
    conn.close()


def delete_game(game_id):
    conn = get_db()
    conn.execute("DELETE FROM shots WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM ends WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM players WHERE game_id = ?", (game_id,))
    conn.execute("DELETE FROM games WHERE id = ?", (game_id,))
    conn.commit()
    conn.close()


def get_shots_by_date_range(date_from, date_to):
    conn = get_db()
    shots = conn.execute(
        "SELECT s.*, p.name AS player_name, p.position, p.team AS player_team, "
        "g.date AS game_date, g.home_team, g.away_team, g.venue "
        "FROM shots s "
        "JOIN players p ON s.player_id = p.id "
        "JOIN games g ON s.game_id = g.id "
        "WHERE g.date >= ? AND g.date <= ? "
        "ORDER BY g.date, s.game_id, s.end_number, s.throw_number",
        (date_from, date_to)
    ).fetchall()
    conn.close()
    return shots


def get_roster():
    conn = get_db()
    players = conn.execute(
        "SELECT * FROM roster ORDER BY name"
    ).fetchall()
    conn.close()
    return players


def add_to_roster(name, default_position=None):
    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO roster (name, default_position) VALUES (?,?)",
            (name.strip(), default_position or None)
        )
        conn.commit()
        success = True
    except Exception:
        success = False
    conn.close()
    return success


def delete_from_roster(roster_id):
    conn = get_db()
    conn.execute("DELETE FROM roster WHERE id = ?", (roster_id,))
    conn.commit()
    conn.close()


def save_end_score(game_id, end_number, home_score, away_score, hammer):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO ends (game_id, end_number, home_score, away_score, hammer) "
        "VALUES (?,?,?,?,?)",
        (game_id, end_number, home_score, away_score, hammer)
    )
    conn.commit()
    conn.close()


def compute_stats(game_id):
    shots = get_all_shots(game_id)
    players = get_players(game_id)
    ends = get_ends(game_id)

    # Per-player stats
    player_stats = {}
    for p in players:
        player_stats[p["id"]] = {
            "name": p["name"],
            "team": p["team"],
            "position": p["position"],
            "shots": 0,
            "total_score": 0,
            "by_weight": {},
            "by_result": {0: 0, 1: 0, 2: 0, 3: 0, 4: 0},
        }

    for shot in shots:
        pid = shot["player_id"]
        if pid not in player_stats:
            continue
        ps = player_stats[pid]
        ps["shots"] += 1
        ps["total_score"] += shot["result_score"]
        wc = shot["weight_call"]
        ps["by_weight"].setdefault(wc, {"shots": 0, "total": 0})
        ps["by_weight"][wc]["shots"] += 1
        ps["by_weight"][wc]["total"] += shot["result_score"]
        ps["by_result"][shot["result_score"]] += 1

    for ps in player_stats.values():
        if ps["shots"] > 0:
            ps["pct"] = round((ps["total_score"] / (ps["shots"] * 4)) * 100, 1)
        else:
            ps["pct"] = 0.0
        for wc, data in ps["by_weight"].items():
            data["pct"] = round((data["total"] / (data["shots"] * 4)) * 100, 1)

    # Scoreline
    home_total, away_total = 0, 0
    scoreline = []
    for end in ends:
        home_total += end["home_score"]
        away_total += end["away_score"]
        scoreline.append({
            "end": end["end_number"],
            "home": end["home_score"],
            "away": end["away_score"],
            "home_cum": home_total,
            "away_cum": away_total,
            "hammer": end["hammer"],
        })

    return {
        "player_stats": player_stats,
        "scoreline": scoreline,
        "home_total": home_total,
        "away_total": away_total,
        "result_labels": RESULT_LABELS,
    }
