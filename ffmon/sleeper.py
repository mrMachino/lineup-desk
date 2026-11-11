"""Sleeper (public API - just your username)."""
from __future__ import annotations

import json
import os
import time

import requests

API = "https://api.sleeper.app/v1"
NON_STARTING = {"BN", "IR", "TAXI"}
CACHE = os.environ.get("SLEEPER_CACHE", ".cache/sleeper_players.json")


def _get(path: str):
    r = requests.get(f"{API}{path}", timeout=60)
    r.raise_for_status()
    return r.json()


def _players_db() -> dict:
    """Sleeper asks that the 5 MB player dump be pulled at most once a day."""
    if os.path.exists(CACHE) and time.time() - os.path.getmtime(CACHE) < 20 * 3600:
        with open(CACHE) as f:
            return json.load(f)
    data = _get("/players/nfl")
    os.makedirs(os.path.dirname(CACHE) or ".", exist_ok=True)
    with open(CACHE, "w") as f:
        json.dump(data, f)
    return data


def current_week() -> tuple[int, str]:
    st = _get("/state/nfl")
    return int(st.get("display_week") or st["week"]), st["season"]


def fetch_leagues(username: str, schedule_for_week) -> list[dict]:
    user = _get(f"/user/{username}")
    if not user:
        raise RuntimeError(f"Sleeper user '{username}' not found")
    uid = user["user_id"]
    week, season = current_week()
    sched = schedule_for_week(week)
    db = _players_db()
    out = []
    for lg in _get(f"/user/{uid}/leagues/nfl/{season}"):
        lid = lg["league_id"]
        rosters = _get(f"/league/{lid}/rosters")
        mine = next((r for r in rosters if r.get("owner_id") == uid or uid in (r.get("co_owners") or [])), None)
        if not mine:
            continue
        users = {u["user_id"]: u for u in _get(f"/league/{lid}/users")}
        matchups = _get(f"/league/{lid}/matchups/{week}") or []
        out.append(parse_league(lg, mine, rosters, users, matchups, db, sched, week))
    return out


def _name(users, roster):
    u = users.get(roster.get("owner_id"), {})
    return (u.get("metadata") or {}).get("team_name") or u.get("display_name") or f"Team {roster['roster_id']}"


def _rec(r):
    s = r.get("settings") or {}
    return f"{s.get('wins', 0)}-{s.get('losses', 0)}" + (f"-{s['ties']}" if s.get("ties") else "")


def parse_league(lg, mine, rosters, users, matchups, db, sched, week) -> dict:
    slots = [p for p in lg["roster_positions"] if p not in NON_STARTING]

    def mk(pid):
        p = db.get(pid, {})
        is_def = p.get("position") == "DEF" or (pid.isalpha() and not p)
        name = (p.get("full_name") or f"{p.get('first_name', '')} {p.get('last_name', '')}".strip()
                or (f"{pid} D/ST" if is_def else pid))
        team = p.get("team") or (pid if is_def else None)
        status = p.get("injury_status")
        return sched.player(name, p.get("position") or ("DEF" if is_def else "?"), team,
                            status, p.get("injury_body_part") if status else None)

    def lineup(starters):
        return [{"sl": s, "pl": mk(starters[i]) if i < len(starters) and starters[i] not in ("0", None, "") else None}
                for i, s in enumerate(slots)]

    my_mu = next((m for m in matchups if m.get("roster_id") == mine["roster_id"]), None)
    starters = (my_mu or {}).get("starters") or mine.get("starters") or []
    reserve, taxi = set(mine.get("reserve") or []), set(mine.get("taxi") or [])
    bench = [mk(pid) for pid in (mine.get("players") or [])
             if pid not in starters and pid not in reserve and pid not in taxi]

    opp = None
    if my_mu:
        om = next((m for m in matchups if m.get("matchup_id") == my_mu.get("matchup_id")
                   and m.get("roster_id") != mine["roster_id"]), None)
        orr = om and next((r for r in rosters if r["roster_id"] == om["roster_id"]), None)
        if orr:
            opp = {"tm": _name(users, orr), "rec": _rec(orr), "lu": lineup(om.get("starters") or [])}

    return {"pf": "Sleeper", "lg": lg["name"], "tm": _name(users, mine), "rec": _rec(mine), "wk": week,
            "opp": opp, "lu": lineup(starters), "bn": bench, "ir": [mk(pid) for pid in reserve],
            "url": f"https://sleeper.com/leagues/{lg.get('league_id')}/team",
            "src": {"type": "sleeper", "lid": lg.get("league_id"), "rid": mine["roster_id"]}}
