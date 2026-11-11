"""Yahoo Fantasy Football via OAuth2. Finds every Yahoo NFL league you're in."""
from __future__ import annotations

import json
import os
import tempfile

from .model import lineup_from_slots

NON_STARTING = {"BN", "IR", "IR+", "NA"}
STATUS = {"O": "Out", "D": "Doubtful", "Q": "Questionable", "IR": "IR", "IR-R": "IR", "IR-NFI": "IR",
          "PUP-R": "PUP", "PUP-P": "PUP", "NFI-R": "IR", "NFI-A": "IR", "NA": "NA", "SUSP": "Suspended"}


def _oauth():
    from yahoo_oauth import OAuth2

    path = os.environ.get("YAHOO_OAUTH_FILE")
    if not path:
        creds = {"consumer_key": os.environ["YAHOO_CONSUMER_KEY"],
                 "consumer_secret": os.environ["YAHOO_CONSUMER_SECRET"],
                 "refresh_token": os.environ["YAHOO_REFRESH_TOKEN"],
                 "access_token": "expired", "token_type": "bearer", "token_time": 0, "guid": None}
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(creds, f)
    sc = OAuth2(None, None, from_file=path)
    if not sc.token_is_valid():
        sc.refresh_access_token()
    return sc


def fetch_leagues(season: int, schedule_for_week) -> list[dict]:
    import yahoo_fantasy_api as yfa

    sc = _oauth()
    gm = yfa.Game(sc, "nfl")
    out = []
    for key in gm.league_ids(game_codes=["nfl"], seasons=[str(season)]):
        lg = gm.to_league(key)
        week = lg.current_week()
        sched = schedule_for_week(week)
        positions = lg.positions()
        my_key = lg.team_key()
        standings = {t.get("team_key"): t for t in lg.standings()}
        names = {k: v.get("name") for k, v in lg.teams().items()}
        my_team = lg.to_team(my_key)
        lu, bn, ir = parse_roster(my_team.roster(week=week), positions, sched)
        opp = None
        try:
            ok = my_team.matchup(week)
            olu, _, _ = parse_roster(lg.to_team(ok).roster(week=week), positions, sched)
            opp = {"tm": names.get(ok, "Opponent"), "rec": _rec(standings.get(ok)), "lu": olu}
        except Exception:
            pass
        out.append({"pf": "Yahoo", "lg": lg.settings().get("name", key), "tm": names.get(my_key, "My team"),
                    "rec": _rec(standings.get(my_key)), "wk": week, "opp": opp,
                    "lu": lu, "bn": bn, "ir": ir, "url": _team_url(my_key)})
    return out


def _team_url(team_key: str) -> str:
    # team_key looks like "461.l.12345.t.7"
    parts = team_key.split(".")
    return f"https://football.fantasysports.yahoo.com/f1/{parts[2]}/{parts[4]}"


def _rec(st: dict | None) -> str:
    o = (st or {}).get("outcome_totals") or {}
    rec = f"{o.get('wins', 0)}-{o.get('losses', 0)}"
    return rec + (f"-{o['ties']}" if str(o.get("ties", "0")) not in ("0", "") else "")


def parse_roster(roster: list[dict], positions: dict, sched) -> tuple[list, list, list]:
    starters, bench, ir = [], [], []
    for r in roster:
        slot = r.get("selected_position", "BN")
        elig = r.get("eligible_positions") or ["?"]
        pos = "DEF" if elig[0] in ("DEF", "D/ST") else elig[0]
        p = sched.player(r.get("name", "?"), pos, r.get("editorial_team_abbr"),
                         STATUS.get((r.get("status") or "").upper()))
        if slot in ("IR", "IR+"):
            ir.append(p)
        elif slot in NON_STARTING:
            bench.append(p)
        else:
            starters.append((slot, p))
    order = [(pos, int(info.get("count", 0))) for pos, info in positions.items() if pos not in NON_STARTING]
    return lineup_from_slots(order, starters), bench, ir
