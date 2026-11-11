#!/usr/bin/env python3
"""One-time Yahoo login. Run on your own computer:

    pip install -r requirements.txt
    python yahoo_setup.py

It opens Yahoo in your browser, you approve, paste the code back here, and it
prints the three values to save as GitHub secrets.
"""
import json
import os

from yahoo_oauth import OAuth2

key = input("Yahoo app Client ID (Consumer Key): ").strip()
secret = input("Yahoo app Client Secret: ").strip()
path = "yahoo_oauth.json"
with open(path, "w") as f:
    json.dump({"consumer_key": key, "consumer_secret": secret}, f)

OAuth2(None, None, from_file=path)  # interactive: opens browser, asks for the code

with open(path) as f:
    creds = json.load(f)
os.remove(path)
print("\nSave these as GitHub repository secrets:\n")
print(f"YAHOO_CONSUMER_KEY    = {creds['consumer_key']}")
print(f"YAHOO_CONSUMER_SECRET = {creds['consumer_secret']}")
print(f"YAHOO_REFRESH_TOKEN   = {creds['refresh_token']}")
