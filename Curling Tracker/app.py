from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from datetime import date
import csv
import io
import db

app = Flask(__name__)
db.init_db()


@app.route("/")
def index():
    conn = db.get_db()
    games = conn.execute(
        "SELECT g.*, "
        "(SELECT COUNT(*) FROM ends WHERE game_id = g.id) as ends_played "
        "FROM games g ORDER BY g.created_at DESC"
    ).fetchall()
    conn.close()
    return render_template("index.html", games=games, today=date.today().isoformat())


@app.route("/game/new", methods=["GET", "POST"])
def new_game():
    if request.method == "POST":
        f = request.form
        conn = db.get_db()
        cur = conn.execute(
            "INSERT INTO games (date, home_team, away_team, venue, hammer_first_end, notes) "
            "VALUES (?,?,?,?,?,?)",
            (f["date"], f["home_team"], f["away_team"],
             f.get("venue", ""), f["hammer_first_end"], f.get("notes", ""))
        )
        game_id = cur.lastrowid

        for team in ["home", "away"]:
            for pos in db.POSITIONS:
                name = f.get(f"{team}_{pos}", "").strip()
                if name:
                    conn.execute(
                        "INSERT INTO players (game_id, name, team, position) VALUES (?,?,?,?)",
                        (game_id, name, team, pos)
                    )
        conn.commit()
        conn.close()
        return redirect(url_for("track", game_id=game_id))

    return render_template("setup.html", today=date.today().isoformat(),
                           positions=db.POSITIONS, roster=db.get_roster())


@app.route("/game/<int:game_id>/track")
def track(game_id):
    game = db.get_game(game_id)
    home_players, away_players = db.get_players_by_team(game_id)
    throw_order = db.get_effective_throw_order(game_id)
    max_throws = len(throw_order)
    end_num, throw_num = db.get_next_throw(game_id)
    ends = db.get_ends(game_id)

    throw_idx = throw_num - 1
    if throw_idx >= len(throw_order):
        return redirect(url_for("end_score", game_id=game_id, end_num=end_num))
    pos, stone, team = throw_order[throw_idx]
    hammer = db.get_hammer_for_end(game_id, end_num)

    players_map = home_players if team == "home" else away_players
    current_player = players_map.get(pos)

    shots_this_end = db.get_shots_for_end(game_id, end_num)

    home_score = sum(e["home_score"] for e in ends)
    away_score = sum(e["away_score"] for e in ends)

    return render_template(
        "track.html",
        game=game,
        end_num=end_num,
        throw_num=throw_num,
        max_throws=max_throws,
        throw_idx=throw_idx,
        current_team=team,
        current_position=pos,
        current_player=current_player,
        hammer=hammer,
        home_players=home_players,
        away_players=away_players,
        shots_this_end=shots_this_end,
        home_score=home_score,
        away_score=away_score,
        ends=ends,
        weight_calls=db.WEIGHT_CALLS,
        turns=db.TURNS,
        lines=db.LINES,
        result_labels=db.RESULT_LABELS,
        positions=db.POSITIONS,
        throw_order=throw_order,
        all_players=db.get_players(game_id),
    )


@app.route("/game/<int:game_id>/shot", methods=["POST"])
def save_shot(game_id):
    f = request.form
    db.save_shot(
        game_id=game_id,
        end_number=int(f["end_number"]),
        throw_number=int(f["throw_number"]),
        player_id=int(f["player_id"]),
        team=f["team"],
        weight_call=f["weight_call"],
        turn=f["turn"],
        result_score=int(f["result_score"]),
        line=f.get("line", "Unknown"),
        actual_weight=f.get("actual_weight") or None,
        notes=f.get("notes", ""),
    )
    max_throws = len(db.get_effective_throw_order(game_id))
    prev_throw = int(f["throw_number"])
    prev_end = int(f["end_number"])
    if prev_throw >= max_throws:
        return redirect(url_for("end_score", game_id=game_id, end_num=prev_end))
    return redirect(url_for("track", game_id=game_id))


@app.route("/game/<int:game_id>/end/<int:end_num>/score", methods=["GET", "POST"])
def end_score(game_id, end_num):
    game = db.get_game(game_id)
    hammer = db.get_hammer_for_end(game_id, end_num)
    shots = db.get_shots_for_end(game_id, end_num)
    ends = db.get_ends(game_id)
    home_cum = sum(e["home_score"] for e in ends)
    away_cum = sum(e["away_score"] for e in ends)

    if request.method == "POST":
        f = request.form
        db.save_end_score(
            game_id=game_id,
            end_number=end_num,
            home_score=int(f["home_score"]),
            away_score=int(f["away_score"]),
            hammer=hammer,
        )
        return redirect(url_for("track", game_id=game_id))

    return render_template(
        "end_score.html",
        game=game,
        end_num=end_num,
        hammer=hammer,
        shots=shots,
        home_cum=home_cum,
        away_cum=away_cum,
        result_labels=db.RESULT_LABELS,
    )


@app.route("/game/<int:game_id>/end/<int:end_num>/score/manual")
def manual_end_score(game_id, end_num):
    """Trigger end score entry manually (e.g. blank end or early score)."""
    return redirect(url_for("end_score", game_id=game_id, end_num=end_num))


@app.route("/game/<int:game_id>/stats")
def game_stats(game_id):
    game = db.get_game(game_id)
    stats = db.compute_stats(game_id)
    return render_template("stats.html", game=game, positions=db.POSITIONS, **stats)


@app.route("/game/<int:game_id>/delete", methods=["POST"])
def delete_game(game_id):
    db.delete_game(game_id)
    return redirect(url_for("index"))


CSV_FIELDS = [
    "game_date", "home_team", "away_team", "venue",
    "end_number", "throw_number", "team", "player_name", "position",
    "weight_call", "actual_weight", "turn", "line", "result_score", "notes",
]


def _shots_csv(shots, filename):
    si = io.StringIO()
    writer = csv.writer(si)
    writer.writerow(CSV_FIELDS)
    for s in shots:
        sd = dict(s)
        # all_shots rows use 'name'/'position' from the JOIN; bulk export uses 'player_name'
        row = [
            sd.get("game_date", ""),
            sd.get("home_team", ""),
            sd.get("away_team", ""),
            sd.get("venue", ""),
            sd.get("end_number", ""),
            sd.get("throw_number", ""),
            sd.get("team", ""),
            sd.get("player_name") or sd.get("name", ""),
            sd.get("position", ""),
            sd.get("weight_call", ""),
            sd.get("actual_weight") or "",
            sd.get("turn", ""),
            sd.get("line", ""),
            sd.get("result_score", ""),
            sd.get("notes") or "",
        ]
        writer.writerow(row)
    return Response(
        si.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@app.route("/game/<int:game_id>/shots.json")
def shots_json(game_id):
    shots = db.get_all_shots(game_id)
    return jsonify([dict(s) for s in shots])


@app.route("/game/<int:game_id>/shots.csv")
def shots_csv(game_id):
    game = db.get_game(game_id)
    shots = db.get_all_shots(game_id)
    # Attach game fields so _shots_csv can find them
    enriched = []
    for s in shots:
        sd = dict(s)
        sd["game_date"] = game["date"]
        sd["home_team"] = game["home_team"]
        sd["away_team"] = game["away_team"]
        sd["venue"] = game["venue"] or ""
        enriched.append(sd)
    filename = (
        f"shots_{game['date']}_{game['home_team']}_vs_{game['away_team']}.csv"
        .replace(" ", "_").replace("/", "-").replace("\\", "-")
    )
    return _shots_csv(enriched, filename)


@app.route("/export")
def export_range():
    date_from = request.args.get("date_from", "")
    date_to = request.args.get("date_to", "")
    fmt = request.args.get("format", "csv")
    if not date_from or not date_to:
        return redirect(url_for("index"))
    shots = db.get_shots_by_date_range(date_from, date_to)
    filename = f"curling_shots_{date_from}_to_{date_to}"
    if fmt == "json":
        return jsonify([dict(s) for s in shots])
    return _shots_csv(shots, f"{filename}.csv")


@app.route("/roster")
def roster():
    return render_template("roster.html", roster=db.get_roster(),
                           positions=db.POSITIONS)


@app.route("/roster/add", methods=["POST"])
def roster_add():
    name = request.form.get("name", "").strip()
    position = request.form.get("default_position", "").strip() or None
    if name:
        db.add_to_roster(name, position)
    return redirect(url_for("roster"))


@app.route("/roster/<int:roster_id>/delete", methods=["POST"])
def roster_delete(roster_id):
    db.delete_from_roster(roster_id)
    return redirect(url_for("roster"))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5050)
