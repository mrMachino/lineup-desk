#!/usr/bin/env python3
"""Lineup Desk: pulls every ESPN, Yahoo and Sleeper league, builds the one-page
dashboard, and pushes alerts for injured / bye / empty starters.

  python monitor.py --site site   # write site/index.html + site/data.json, send alerts
  python monitor.py --dry-run     # print the report only
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import shutil
import sys

import yaml

from ffmon import espn, notify, sleeper, yahoo
from ffmon.model import Schedule, check_league

STATE = ".cache/last_alert.txt"
HERE = os.path.dirname(os.path.abspath(__file__))


def collect(cfg: dict) -> tuple[list[dict], list[str]]:
    season = espn.season_now()
    leagues, errors = [], []
    try:
        pro = espn.fetch_pro_schedule(season)
    except Exception as e:
        pro = {}
        errors.append(f"NFL schedule ({e})")
    weeks: dict[int, Schedule] = {}

    def sched(week: int) -> Schedule:
        if week not in weeks:
            weeks[week] = espn.schedule_for_week(pro, week) if pro else Schedule(week=week)
        return weeks[week]

    swid, s2 = os.environ.get("ESPN_SWID"), os.environ.get("ESPN_S2")
    for lid in (cfg.get("espn") or {}).get("league_ids") or []:
        try:
            if not swid:
                raise RuntimeError("ESPN_SWID secret is not set")
            leagues.append(espn.fetch_league(int(lid), season, swid, s2, pro))
        except Exception as e:
            errors.append(f"ESPN league {lid} ({e})")

    if (cfg.get("yahoo") or {}).get("enabled"):
        try:
            leagues += yahoo.fetch_leagues(season, sched)
        except Exception as e:
            errors.append(f"Yahoo ({e})")

    for user in [u for u in [(cfg.get("sleeper") or {}).get("username")] if u]:
        try:
            leagues += sleeper.fetch_leagues(user, sched)
        except Exception as e:
            errors.append(f"Sleeper ({e})")
    return leagues, errors


def report(leagues: list[dict], errors: list[str], min_level: str) -> tuple[str, int, int]:
    keep = {"bad"} if min_level == "CRITICAL" else {"bad", "warn"}
    lines, n_bad, n_all = [], 0, 0
    for L in leagues:
        iss = [i for i in check_league(L) if i["sev"] in keep]
        if not iss:
            continue
        lines.append(f"\n{L['pf']} · {L['lg']} — {L['tm']}")
        for i in iss:
            lines.append(f"  {'🚨' if i['sev'] == 'bad' else '⚠️'} {i['txt']}")
            if i["swap"]:
                lines.append(f"     swap in: {', '.join(i['swap'])}")
        n_bad += sum(i["sev"] == "bad" for i in iss)
        n_all += len(iss)
    if errors:
        lines.append("\nCouldn't load:")
        lines += [f"  ❌ {e}" for e in errors]
    return "\n".join(lines).strip(), n_bad, n_all


def write_site(out: str, leagues: list[dict], errors: list[str], refresh_url: str) -> None:
    os.makedirs(out, exist_ok=True)
    shutil.copy(os.path.join(HERE, "ffmon", "dashboard.html"), os.path.join(out, "index.html"))
    data = {"updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "wk": max((L.get("wk") or 0 for L in leagues), default=0),
            "leagues": leagues, "errors": [e.split(" (")[0] for e in errors], "refresh": refresh_url}
    with open(os.path.join(out, "data.json"), "w") as f:
        json.dump(data, f, separators=(",", ":"))
    with open(os.path.join(out, ".nojekyll"), "w"):
        pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--site", help="folder to write the dashboard into")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    with open(args.config) as f:
        cfg = yaml.safe_load(f) or {}
    leagues, errors = collect(cfg)
    body, n_bad, n_all = report(leagues, errors, cfg.get("min_level", "WARNING"))
    print(body or f"All {len(leagues)} lineups set.")
    for e in errors:
        print(f"ERROR: {e}", file=sys.stderr)

    if args.site:
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        refresh = f"https://github.com/{repo}/actions/workflows/monitor.yml" if repo else "#"
        write_site(args.site, leagues, errors, refresh)
    if args.dry_run or (n_all == 0 and not errors):
        return 0

    digest = hashlib.sha256(body.encode()).hexdigest()
    force = args.force or os.environ.get("FORCE_SEND") == "1"
    if not force and os.path.exists(STATE) and open(STATE).read().strip() == digest:
        print("(No change since last alert - not re-sending.)")
        return 0
    title = (f"🚨 {n_bad} lineup problem{'s' * (n_bad != 1)}" if n_bad
             else f"⚠️ {n_all} player{'s' * (n_all != 1)} to watch" if n_all
             else "❌ Lineup Desk couldn't load a league")
    site = cfg.get("site_url")
    for f in notify.deliver(title, body + (f"\n\n{site}" if site else ""), urgent=n_bad > 0, click=site):
        print(f"Notify failed - {f}", file=sys.stderr)
    os.makedirs(".cache", exist_ok=True)
    with open(STATE, "w") as f:
        f.write(digest)
    return 0


if __name__ == "__main__":
    sys.exit(main())
