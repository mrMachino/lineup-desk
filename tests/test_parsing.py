"""Offline tests: realistic API payloads -> league dicts -> alerts + site."""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ffmon import espn, sleeper, yahoo
from ffmon.model import Schedule, check_league
from monitor import report, write_site

FUTURE = 4_000_000_000_000  # kickoff far in the future
PRO = {"settings": {"proTeams": [
    {"id": 0, "abbrev": "FA", "byeWeek": 0},
    {"id": 8, "abbrev": "Det", "byeWeek": 8, "proGamesByScoringPeriod": {"12": [{"homeProTeamId": 8, "awayProTeamId": 17, "date": FUTURE}]}},
    {"id": 17, "abbrev": "NE", "byeWeek": 14, "proGamesByScoringPeriod": {"12": [{"homeProTeamId": 8, "awayProTeamId": 17, "date": FUTURE}]}},
    {"id": 24, "abbrev": "LAC", "byeWeek": 5, "proGamesByScoringPeriod": {"12": [{"homeProTeamId": 33, "awayProTeamId": 24, "date": FUTURE}]}},
    {"id": 33, "abbrev": "Bal", "byeWeek": 7, "proGamesByScoringPeriod": {"12": [{"homeProTeamId": 33, "awayProTeamId": 24, "date": FUTURE}]}},
    {"id": 28, "abbrev": "Wsh", "byeWeek": 12},
    {"id": 15, "abbrev": "Mia", "byeWeek": 12},
]}}


def ent(slot, name, pos, team, status=None):
    p = {"fullName": name, "defaultPositionId": pos, "proTeamId": team}
    if status:
        p["injuryStatus"] = status
    return {"lineupSlotId": slot, "playerPoolEntry": {"player": p}}


def test_espn():
    data = {"id": 1, "scoringPeriodId": 12, "status": {"currentMatchupPeriod": 12},
            "settings": {"name": "Salary Cap League", "rosterSettings": {"lineupSlotCounts": {
                "0": 1, "2": 2, "4": 2, "6": 1, "23": 1, "16": 1, "20": 6, "21": 1}}},
            "schedule": [{"matchupPeriodId": 12, "home": {"teamId": 3}, "away": {"teamId": 2}}],
            "teams": [
                {"id": 2, "name": "Rival", "owners": ["{ZZZ}"], "record": {"overall": {"wins": 6, "losses": 3}},
                 "roster": {"entries": [ent(0, "Other QB", 1, 8)]}},
                {"id": 3, "name": "Juan's Team", "owners": ["{aaaa-bbbb}"], "record": {"overall": {"wins": 4, "losses": 5}},
                 "roster": {"entries": [
                     ent(0, "Justin Herbert", 1, 24), ent(2, "De'Von Achane", 2, 15),
                     ent(4, "Amon-Ra St. Brown", 3, 8, "QUESTIONABLE"), ent(4, "Terry McLaurin", 3, 28, "OUT"),
                     ent(6, "Trey McBride", 4, 17), ent(23, "Ladd McConkey", 3, 24, "DOUBTFUL"),
                     ent(20, "Kyle Williams", 3, 17), ent(21, "Healed Guy", 2, 8, "ACTIVE")]}}]}
    L = espn.parse_league(data, "{AAAA-BBBB}", PRO)
    assert L["tm"] == "Juan's Team" and L["rec"] == "4-5" and L["opp"]["tm"] == "Rival"
    assert [r["sl"] for r in L["lu"]] == ["QB", "RB", "RB", "WR", "WR", "TE", "FLEX", "DEF"]
    assert L["lu"][0]["pl"]["o"] == "@ BAL"
    txt = " | ".join(i["txt"] for i in check_league(L))
    for want in ["Empty RB", "Empty DEF", "Achane is on bye", "McLaurin is on bye",
                 "McConkey is Doubtful", "St. Brown is Questionable", "Healed Guy is in your IR"]:
        assert want in txt, (want, txt)
    flex = next(i for i in check_league(L) if "McConkey" in i["txt"])
    assert flex["swap"] == ["Kyle Williams (WR, @ DET)"]
    return L


def test_yahoo():
    sched = espn.schedule_for_week(PRO, 12)
    roster = [
        {"name": "Josh Allen", "eligible_positions": ["QB"], "selected_position": "QB", "status": "", "editorial_team_abbr": "NE"},
        {"name": "Bijan Robinson", "eligible_positions": ["RB", "W/R/T"], "selected_position": "RB", "status": "O", "editorial_team_abbr": "Det"},
        {"name": "Puka Nacua", "eligible_positions": ["WR", "W/R/T"], "selected_position": "IR", "status": "IR", "editorial_team_abbr": "LAR"},
    ]
    positions = {"QB": {"count": 1}, "RB": {"count": 2}, "W/R/T": {"count": 1}, "BN": {"count": 6}, "IR": {"count": 1}}
    lu, bn, ir = yahoo.parse_roster(roster, positions, sched)
    L = {"pf": "Yahoo", "lg": "Office", "tm": "Machinos", "rec": "5-4", "wk": 12, "opp": None, "lu": lu, "bn": bn, "ir": ir}
    assert [r["sl"] for r in lu] == ["QB", "RB", "RB", "W/R/T"]
    txt = " | ".join(i["txt"] for i in check_league(L))
    assert "Bijan Robinson is Out" in txt and "Empty RB" in txt and "Empty FLEX" in txt
    assert ir[0]["n"] == "Puka Nacua" and "Puka" not in txt
    return L


def test_sleeper():
    sched = Schedule({"BUF": {"opp": "NYJ", "home": True, "date": FUTURE}}, {"DET": 8}, 8)
    db = {"4984": {"full_name": "Josh Allen", "position": "QB", "team": "BUF"},
          "9509": {"full_name": "Bijan Robinson", "position": "RB", "team": "ATL", "injury_status": "Questionable", "injury_body_part": "Ankle"},
          "DET": {"first_name": "Detroit", "last_name": "Lions", "position": "DEF", "team": "DET"},
          "1111": {"full_name": "Hurt Guy", "position": "WR", "team": "MIA", "injury_status": "IR"}}
    lg = {"name": "In Remembrance of Lane of Haas", "roster_positions": ["QB", "RB", "FLEX", "DEF", "BN", "IR"]}
    mine = {"roster_id": 1, "owner_id": "u1", "starters": ["4984", "9509", "0", "DET"],
            "players": ["4984", "9509", "DET", "1111"], "reserve": ["1111"], "settings": {"wins": 4, "losses": 5}}
    other = {"roster_id": 2, "owner_id": "u2", "settings": {"wins": 6, "losses": 3}}
    users = {"u1": {"display_name": "MrMachino", "metadata": {"team_name": "1-800-INJURY"}}, "u2": {"display_name": "Quasar"}}
    mus = [{"roster_id": 1, "matchup_id": 3, "starters": mine["starters"]}, {"roster_id": 2, "matchup_id": 3, "starters": ["4984"]}]
    L = sleeper.parse_league(lg, mine, [mine, other], users, mus, db, sched, 8)
    assert L["tm"] == "1-800-INJURY" and L["opp"]["tm"] == "Quasar" and L["rec"] == "4-5"
    txt = " | ".join(i["txt"] for i in check_league(L))
    assert "Empty FLEX" in txt and "Detroit Lions is on bye" in txt and "Bijan Robinson is Questionable - Ankle" in txt
    assert "Hurt Guy" not in txt
    return L


if __name__ == "__main__":
    leagues = [test_espn(), test_yahoo(), test_sleeper()]
    out = tempfile.mkdtemp()
    write_site(out, leagues, ["ESPN league 999 (boom)"], "#")
    d = json.load(open(os.path.join(out, "data.json")))
    assert len(d["leagues"]) == 3 and d["errors"] == ["ESPN league 999"]
    print("All tests passed.\n")
    print(report(leagues, [], "WARNING")[0])
    print("\nsite:", out)
