"""Shared data shape + the checks that turn lineups into alerts.

Every platform module returns a list of league dicts in this shape (the same
shape the dashboard page renders):

  {"pf": "ESPN", "lg": "League name", "tm": "My team", "rec": "4-5", "wk": 10,
   "opp": {"tm": "Their team", "rec": "6-3", "lu": [slot, ...]} or None,
   "lu": [{"sl": "RB", "pl": player or None}, ...],   # starting lineup
   "bn": [player, ...], "ir": [player, ...]}

  player = {"n": name, "p": "WR", "t": "DET", "s": "Questionable" or None,
            "b": "Knee" or None, "o": "@ GB" or None, "k": kickoff epoch ms or None,
            "y": True if on bye}
"""
from __future__ import annotations

import time

_ABBR_ALIASES = {"WSH": "WAS", "JAC": "JAX", "LA": "LAR", "OAK": "LV", "SD": "LAC", "STL": "LAR"}

BAD = {"OUT", "O", "IR", "PUP", "SUS", "SUSP", "SUSPENDED", "NA", "DNR", "COV", "DOUBTFUL", "D"}
WARN = {"QUESTIONABLE", "Q", "GTD", "DAY_TO_DAY"}

SLOT_LABEL = {"WRRB_FLEX": "W/R", "REC_FLEX": "W/T", "SUPER_FLEX": "SF", "W/R/T": "FLEX",
              "D/ST": "DEF", "Q/W/R/T": "SF", "OP": "SF"}
ELIGIBLE = {
    "QB": {"QB"}, "RB": {"RB"}, "WR": {"WR"}, "TE": {"TE"}, "K": {"K"},
    "DEF": {"DEF", "D/ST"}, "D/ST": {"DEF", "D/ST"},
    "FLEX": {"RB", "WR", "TE"}, "W/R/T": {"RB", "WR", "TE"}, "RB/WR/TE": {"RB", "WR", "TE"},
    "WRRB_FLEX": {"WR", "RB"}, "W/R": {"WR", "RB"}, "RB/WR": {"WR", "RB"},
    "REC_FLEX": {"WR", "TE"}, "W/T": {"WR", "TE"}, "WR/TE": {"WR", "TE"},
    "SUPER_FLEX": {"QB", "RB", "WR", "TE"}, "Q/W/R/T": {"QB", "RB", "WR", "TE"},
    "OP": {"QB", "RB", "WR", "TE"},
}


def norm_team(abbr: str | None) -> str | None:
    if not abbr:
        return None
    a = abbr.strip().upper()
    return _ABBR_ALIASES.get(a, a)


def severity(status: str | None) -> str | None:
    s = (status or "").upper()
    if s in BAD:
        return "bad"
    if s in WARN:
        return "warn"
    return None


class Schedule:
    """NFL schedule for one week: who each team plays, when, and who's on bye."""

    def __init__(self, games: dict[str, dict] | None = None, byes: dict[str, int] | None = None,
                 week: int = 0):
        self.games, self.byes, self.week = games or {}, byes or {}, week

    def player(self, name, pos, team, status=None, body=None) -> dict:
        team = norm_team(team)
        g = self.games.get(team) if team else None
        p = {"n": name, "p": pos, "t": team, "s": status or None, "b": body or None,
             "o": None, "k": None}
        if g:
            p["o"] = ("v " if g["home"] else "@ ") + g["opp"]
            p["k"] = g["date"]
        elif team and self.byes.get(team) == self.week:
            p["y"] = True
        return p


def _swaps(league: dict, slot: str, now_ms: float) -> list[str]:
    ok = ELIGIBLE.get(slot, {slot})
    out = []
    for b in league.get("bn", []):
        if (b and not b.get("y") and not severity(b.get("s")) and b.get("p") in ok
                and b.get("k") and b["k"] > now_ms):
            out.append(f"{b['n']} ({b['p']}, {b['o']})")
    return out[:3]


def check_league(league: dict, now_ms: float | None = None) -> list[dict]:
    """Return [{"sev": "bad"|"warn", "txt": ..., "swap": [...]}] for one league."""
    now_ms = now_ms if now_ms is not None else time.time() * 1000
    issues = []
    for row in league.get("lu", []):
        slot, p = row["sl"], row.get("pl")
        label = SLOT_LABEL.get(slot, slot)
        if not p:
            issues.append({"sev": "bad", "txt": f"Empty {label} slot", "swap": _swaps(league, slot, now_ms)})
            continue
        if p.get("k") and p["k"] < now_ms:
            continue  # game started - locked
        if p.get("y"):
            issues.append({"sev": "bad", "txt": f"{p['n']} is on bye ({label})",
                           "swap": _swaps(league, slot, now_ms)})
            continue
        sev = severity(p.get("s"))
        if sev:
            body = f" - {p['b']}" if p.get("b") else ""
            issues.append({"sev": sev, "txt": f"{p['n']} is {p['s']}{body} ({label})",
                           "swap": _swaps(league, slot, now_ms)})
    for p in league.get("ir", []):
        if p and not severity(p.get("s")):
            issues.append({"sev": "warn", "txt": f"{p['n']} is in your IR slot but listed healthy", "swap": []})
    issues.sort(key=lambda i: 0 if i["sev"] == "bad" else 1)
    return issues


def lineup_from_slots(slot_counts: list[tuple[str, int]], starters: list[tuple[str, dict]]) -> list[dict]:
    """Lay starters into the league's slot order; unfilled slots become None."""
    pool: dict[str, list[dict]] = {}
    for slot, p in starters:
        pool.setdefault(slot, []).append(p)
    lu = []
    for slot, count in slot_counts:
        for _ in range(count):
            lu.append({"sl": slot, "pl": pool.get(slot, []).pop(0) if pool.get(slot) else None})
    return lu
