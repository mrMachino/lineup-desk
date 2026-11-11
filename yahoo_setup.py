#!/usr/bin/env python3
"""One-time Yahoo login for Lineup Desk. Run on your own computer:

    python yahoo_setup.py

1. Paste your Yahoo app's Client ID and Client Secret.
2. Approve access in the browser window that opens.
3. Yahoo then sends you to a page that won't load (https://localhost:8000/...).
   That's expected: copy the whole address from the address bar and paste it here.
4. It prints the three values to save as GitHub secrets.
"""
import base64
import json
import urllib.parse
import urllib.request
import webbrowser

REDIRECT = "https://localhost:8000"

print(__doc__)
key = input("Client ID (Consumer Key): ").strip()
secret = input("Client Secret (Consumer Secret): ").strip()

url = "https://api.login.yahoo.com/oauth2/request_auth?" + urllib.parse.urlencode(
    {"client_id": key, "redirect_uri": REDIRECT, "response_type": "code", "language": "en-us"})
print("\nOpening Yahoo in your browser. If nothing opens, paste this into the browser:\n" + url + "\n")
webbrowser.open(url)

pasted = input("Paste the full address of the page Yahoo sent you to (starts with https://localhost): ").strip()
code = urllib.parse.parse_qs(urllib.parse.urlparse(pasted).query).get("code", [pasted])[0]

req = urllib.request.Request(
    "https://api.login.yahoo.com/oauth2/get_token",
    data=urllib.parse.urlencode({"grant_type": "authorization_code", "redirect_uri": REDIRECT, "code": code}).encode(),
    headers={"Authorization": "Basic " + base64.b64encode(f"{key}:{secret}".encode()).decode(),
             "Content-Type": "application/x-www-form-urlencoded"})
try:
    tok = json.load(urllib.request.urlopen(req, timeout=30))
except urllib.error.HTTPError as e:
    print("\nYahoo said no:", e.read().decode()[:300])
    print("Run this again and paste the address right after approving (the code expires quickly).")
    input("\nPress Enter to close.")
    raise SystemExit(1)

print("\nDone. Save these three as GitHub secrets (repo -> Settings -> Secrets and variables -> Actions):\n")
print(f"YAHOO_CONSUMER_KEY    = {key}")
print(f"YAHOO_CONSUMER_SECRET = {secret}")
print(f"YAHOO_REFRESH_TOKEN   = {tok['refresh_token']}")
with open("yahoo_secrets.txt", "w") as f:
    f.write(f"YAHOO_CONSUMER_KEY\n{key}\n\nYAHOO_CONSUMER_SECRET\n{secret}\n\nYAHOO_REFRESH_TOKEN\n{tok['refresh_token']}\n")
print("\nAlso saved to yahoo_secrets.txt in this folder so you can copy them. Delete that file when you're done.")
input("\nPress Enter to close.")
