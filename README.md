# Lineup Desk

One page with every fantasy team you own on ESPN, Yahoo and Sleeper: this week's lineup, each player's NFL opponent and kickoff, injury tags, byes, empty slots, your fantasy opponent, and bench players you could swap in.

**Page:** https://mrmachino.github.io/lineup-desk/

GitHub pulls your leagues every 10 minutes (Actions → *Lineup Desk*). The page picks up each pull on its own. To force a pull right now: Actions → Lineup Desk → **Run workflow**.

## Logins (GitHub secrets)

Repo → Settings → Secrets and variables → Actions → **New repository secret**. Secrets are never shown to anyone, even in a public repo.

| Secret | Where to get it |
|---|---|
| `ESPN_SWID` | Chrome on espn.com (logged in) → F12 → Application → Cookies → `https://www.espn.com` → `SWID` (keep the `{ }`) |
| `ESPN_S2` | Same list → `espn_s2` |
| `YAHOO_CONSUMER_KEY`, `YAHOO_CONSUMER_SECRET`, `YAHOO_REFRESH_TOKEN` | Run `python yahoo_setup.py` once on your computer (needs a free app from developer.yahoo.com, permission *Fantasy Sports: Read*) |
| `NTFY_TOPIC` (optional) | Phone alerts: install the ntfy app, subscribe to a hard-to-guess topic name, save the same name here |

Then in `config.yaml`: add your ESPN league IDs and set `yahoo: enabled: true`.

ESPN cookies last about a year. If the page says *Couldn't load ESPN*, refresh those two secrets.

## Run locally
```
pip install -r requirements.txt
python monitor.py --dry-run
python tests/test_parsing.py
```
