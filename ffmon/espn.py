"""ESPN Fantasy Football. Private leagues need the espn_s2 + SWID cookies.

Also supplies the NFL schedule (opponents, kickoffs, byes) used for every platform.
"""
from __future__ import annotations

import datetime as dt

import requests

from .model import Schedule, lineup_from_slots, norm_team

BASE = "https://lm-api-reads.fantasy.espn.com/apis/v3/games/ffl/seasons/{season}"
SLOTS = {0: "QB", 2: "RB", 3: "W/R", 4: "WR", 5: "W/T", 6: "TE", 7: "OP", 16: "DEF", 17: "K",
         20: "BE", 21: "IR", 23: "FLEX", 24: "ER"}
SLOT_ORDER = [0, 2, 4, 6, 3, 5, 23, 7, 16, 17]
NON_STARTING = {20, 21, 24}
POSITIONS = {1: "QB", 2: "RB", 3: "WR", 4: "TE", 5: "K", 16: "DEF"}
STATUS = {"OUT": "Out", "DOUBTFUL": "Doubtful", "QUESTIONABLE": "Questionable",
          "DAY_TO_DAY": "Questionable", "INJURY_RESERVE": "IR", "SUSPENSION": "Suspended"}


def _session(espn_s2=None, swid=None) -> requests.Session:
    s = requests.Session()
    s.headers["User-Agent"] = "lineup-desk/1.0"
    if espn_s2 and swid:
        s.cookies.set("espn_s2", espn_s2, domain=".espn.com")
        s.cookies.set("SWID", swid, domain=".espn.com")
    return s


def fetch_pro_schedule(season: int) -> dict:
    r = _session().get(BASE.format(season=season), params={"view": "proTeamSchedules_wl"}, timeout=30)
    r.raise_for_status()
    return r.json()


def schedule_for_week(pro: dict, week: int) -> Schedule:
    teams = pro.get("settings", {}).get("proTeams", [])
    abbr = {t["id"]: norm_team(t["abbrev"]) for t in teams}
    games, byes = {}, {}
    for t in teams:
        if not t.get("id"):
            continue
        byes[abbr[t["id"]]] = t.get("byeWeek")
        for g in (t.get("proGamesByScoringPeriod") or {}).get(str(week), []):
            home = g["homeProTeamId"] == t["id"]
            games[abbr[t["id"]]] = {"opp": abbr[g["awayProTeamId"] if home else g["homeProTeamId"]],
                                    "home": home, "date": g["date"]}
    return Schedule(games, byes, week)


def pro_abbrevs(pro: dict) -> dict[int, str]:
    return {t["id"]: norm_team(t["abbrev"]) for t in pro.get("settings", {}).get("proTeams", [])}


def fetch_league(league_id: int, season: int, swid: str, espn_s2: str | None, pro: dict) -> dict:
    s = _session(espn_s2, swid)
    r = s.get(f"{BASE.format(season=season)}/segments/0/leagues/{league_id}",
              params=[("view", v) for v in ("mTeam", "mRoster", "mMatchup", "mSettings")], timeout=30)
    if r.status_code in (401, 403):
        raise RuntimeError("not authorized - ESPN cookies (ESPN_S2 / ESPN_SWID) missing or expired")
    r.raise_for_status()
    return parse_league(r.json(), swid, pro)


def _record(t: dict) -> str:
    o = (t.get("record") or {}).get("overall") or {}
    rec = f"{o.get('wins', 0)}-{o.get('losses', 0)}"
    return rec + (f"-{o['ties']}" if o.get("ties") else "")


def _team_name(t: dict) -> str:
    return t.get("name") or f"{t.get('location', '')} {t.get('nickname', '')}".strip() or f"Team {t.get('id')}"


def _roster(team: dict, counts: dict[int, int], sched: Schedule, abbr: dict[int, str]):
    starters, bench, ir = [], [], []
    for e in team.get("roster", {}).get("entries", []):
        sid = e["lineupSlotId"]
        pp = e["playerPoolEntry"]["player"]
        p = sched.player(pp.get("fullName", "?"), POSITIONS.get(pp.get("defaultPositionId"), "?"),
                         abbr.get(pp.get("proTeamId")), STATUS.get(pp.get("injuryStatus")))
        if sid == 21:
            ir.append(p)
        elif sid in NON_STARTING:
            bench.append(p)
        else:
            starters.append((SLOTS.get(sid, str(sid)), p))
    order = [(SLOTS.get(sid, str(sid)), counts[sid]) for sid in SLOT_ORDER if counts.get(sid)]
    order += [(SLOTS.get(sid, str(sid)), n) for sid, n in counts.items()
              if n and sid not in SLOT_ORDER and sid not in NON_STARTING]
    return lineup_from_slots(order, starters), bench, ir


def parse_league(data: dict, swid: str, pro: dict) -> dict:
    swid_n = swid.strip().upper()
    teams = data.get("teams", [])
    mine = next((t for t in teams if swid_n in [o.upper() for o in t.get("owners", [])]), None)
    name = data.get("settings", {}).get("name", f"ESPN {data.get('id')}")
    if mine is None:
        raise RuntimeError(f"'{name}': couldn't find your team for that SWID")
    week = data.get("scoringPeriodId") or 0
    period = (data.get("status") or {}).get("currentMatchupPeriod") or week
    sched = schedule_for_week(pro, week)
    abbr = pro_abbrevs(pro)
    counts = {int(k): v for k, v in data["settings"]["rosterSettings"]["lineupSlotCounts"].items() if v}

    lu, bn, ir = _roster(mine, counts, sched, abbr)
    opp = None
    for m in data.get("schedule", []):
        if m.get("matchupPeriodId") != period:
            continue
        ids = [(m.get("home") or {}).get("teamId"), (m.get("away") or {}).get("teamId")]
        if mine["id"] in ids:
            oid = next((i for i in ids if i != mine["id"]), None)
            ot = next((t for t in teams if t["id"] == oid), None)
            if ot:
                olu, _, _ = _roster(ot, counts, sched, abbr)
                opp = {"tm": _team_name(ot), "rec": _record(ot), "lu": olu}
            break
    return {"pf": "ESPN", "lg": name, "tm": _team_name(mine), "rec": _record(mine), "wk": week,
            "opp": opp, "lu": lu, "bn": bn, "ir": ir}


def season_now() -> int:
    t = dt.date.today()
    return t.year if t.month >= 3 else t.year - 1
