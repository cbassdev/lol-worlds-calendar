"""Build an auto-updating .ics feed with every League of Legends Worlds 2026 match.

Data: the lolesports.com schedule (same request the site itself makes), so team
names fill in as soon as matchups are drawn and scores appear once a match is played.

Usage:
  python build_ics.py                 # dry run: print what the feed would contain, write nothing
  python build_ics.py --write [DIR]   # write worlds2026.ics (+ index.html) into DIR (default: _site)
"""
import json
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORLDS_LEAGUE_ID = "98767975604431411"
# Persisted query hash of the site's "homeEvents" GraphQL operation. If Riot redeploys
# lolesports.com with a changed query, this hash stops working and the run fails loudly
# (the last good feed stays published). Grab the new hash from the site's network tab.
HOME_EVENTS_HASH = "a4ca0434b4c3af4f3f95b4d7b03fe2a3fcdda0a36887d4f181da99cf3786f664"

WATCH_URL = "https://www.twitch.tv/caedrel"
ALARM_MINUTES = 15
SHOW_RESULTS = True  # put final scores in titles of finished matches (spoilers!)
DURATION_H = {1: 1, 3: 3, 5: 5}  # approximate broadcast slot per series length

VENUES = {
    "Play-Ins": "Riot Games Arena, 12312 W Olympic Blvd, Los Angeles, CA 90064",
    "Finals": "Barclays Center, 620 Atlantic Ave, Brooklyn, NY 11217",
}
DEFAULT_VENUE = "Credit Union of Texas Event Center, 200 E Stacy Rd, Allen, TX 75002"

# Swiss rounds by US Central match day (from the published schedule).
SWISS_ROUNDS = {
    "2026-10-23": "R1", "2026-10-24": "R2", "2026-10-25": "R3", "2026-10-26": "R3",
    "2026-10-28": "R4", "2026-10-29": "R4", "2026-10-30": "R4", "2026-10-31": "R5",
}
NUMBERED = {"Quarterfinals": "Quarterfinal", "Semifinals": "Semifinal"}


def fetch_matches():
    variables = {
        "hl": "en-US", "sport": "lol", "leagues": [WORLDS_LEAGUE_ID],
        "eventDateStart": "2026-10-01T00:00:00.000Z", "eventDateEnd": "2026-12-01T00:00:00.000Z",
        "eventState": ["completed", "inProgress", "unstarted"], "eventType": "match", "pageSize": 300,
    }
    extensions = {"persistedQuery": {"version": 1, "sha256Hash": HOME_EVENTS_HASH}}
    query = urllib.parse.urlencode({
        "operationName": "homeEvents",
        "variables": json.dumps(variables),
        "extensions": json.dumps(extensions),
    })
    req = urllib.request.Request(
        f"https://lolesports.com/api/gql?{query}",
        headers={
            "apollographql-client-name": "Esports Web",
            "apollographql-client-version": "1",
            "x-apollo-operation-name": "homeEvents",
            "User-Agent": "lol-worlds-calendar/1.0 (+https://github.com/cbassdev/lol-worlds-calendar)",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    if data.get("errors"):
        raise SystemExit(f"lolesports API error: {data['errors']}")
    events = data["data"]["esports"]["events"]
    if not events:
        raise SystemExit("lolesports API returned no Worlds matches - refusing to publish an empty feed")
    return sorted(events, key=lambda e: e["startTime"])


def stage_label(ev, index_in_block):
    block = ev["blockName"]
    if block == "Swiss":
        central_day = (parse(ev["startTime"]) - timedelta(hours=7)).date().isoformat()
        rnd = SWISS_ROUNDS.get(central_day)
        return f"Swiss {rnd}" if rnd else "Swiss"
    if block in NUMBERED:
        return f"{NUMBERED[block]} {index_in_block}"
    if block == "Finals":
        return "Grand Final"
    if block == "Play-Ins":
        return "Play-In"
    return block


def matchup(ev):
    a, b = ev["matchTeams"]
    ra, rb = a.get("result") or {}, b.get("result") or {}
    if SHOW_RESULTS and ev["state"] != "unstarted" and ra.get("gameWins") is not None:
        score = f"{a['code']} {ra['gameWins']}–{rb.get('gameWins', 0)} {b['code']}"
        return score + (" (live)" if ev["state"] == "inProgress" else "")
    return f"{a['code']} vs {b['code']}"


def parse(ts):
    return datetime.strptime(ts, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def fmt(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def esc(s):
    return s.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def fold(line):
    # RFC 5545: lines longer than 75 octets are folded with CRLF + space.
    out, b = [], line.encode("utf-8")
    while len(b) > 75:
        cut = 75
        while (b[cut] & 0xC0) == 0x80:  # don't split a UTF-8 sequence
            cut -= 1
        out.append(b[:cut].decode("utf-8"))
        b = b[cut:]
        cut = 74
    out.append(b.decode("utf-8"))
    return "\r\n ".join(out)


def to_events(raw):
    counters = defaultdict(int)
    for ev in raw:
        counters[ev["blockName"]] += 1
        bo = ev["match"]["strategy"]["count"]
        stage = stage_label(ev, counters[ev["blockName"]])
        start = parse(ev["startTime"])
        names = " vs ".join(t["name"] for t in ev["matchTeams"])
        yield {
            "uid": f"worlds2026-{ev['match']['id']}@lol-worlds-calendar",
            "start": start,
            "end": start + timedelta(hours=DURATION_H.get(bo, bo)),
            "summary": f"Worlds 2026 · {stage} · {matchup(ev)} (Bo{bo})",
            "location": VENUES.get(ev["blockName"], DEFAULT_VENUE),
            "description": (
                f"League of Legends World Championship 2026 - {stage}, best of {bo}.\n"
                f"{names}\n"
                "TBD teams fill in automatically once the matchup is set.\n"
                f"Watch: {WATCH_URL}"
            ),
        }


def build_ics(events):
    stamp = fmt(datetime.now(timezone.utc))
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//lol-worlds-calendar//Worlds 2026//EN",
        "CALSCALE:GREGORIAN", "METHOD:PUBLISH", "X-WR-CALNAME:LoL Worlds 2026",
        "REFRESH-INTERVAL;VALUE=DURATION:PT15M", "X-PUBLISHED-TTL:PT15M",
    ]
    for e in events:
        lines += [
            "BEGIN:VEVENT", f"UID:{e['uid']}", f"DTSTAMP:{stamp}",
            f"DTSTART:{fmt(e['start'])}", f"DTEND:{fmt(e['end'])}",
            f"SUMMARY:{esc(e['summary'])}", f"LOCATION:{esc(e['location'])}",
            f"DESCRIPTION:{esc(e['description'])}", f"URL:{WATCH_URL}",
            "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{esc(e['summary'])}",
            f"TRIGGER:-PT{ALARM_MINUTES}M", "END:VALARM", "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold(l) for l in lines) + "\r\n"


INDEX_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>LoL Worlds 2026 calendar</title>
<style>body{font:16px/1.6 system-ui,sans-serif;max-width:32rem;margin:3rem auto;padding:0 1rem}
a.btn{display:inline-block;padding:.7rem 1.1rem;border-radius:.6rem;background:#0a84ff;color:#fff;text-decoration:none}</style>
</head><body>
<h1>LoL Worlds 2026 calendar</h1>
<p>All Worlds 2026 matches. Teams and scores update automatically every ~15 minutes.</p>
<p><a class="btn" id="sub" href="worlds2026.ics">Subscribe on iPhone</a></p>
<p>Last updated: {updated} UTC</p>
<script>var a=document.getElementById('sub');a.href='webcal://'+location.host+location.pathname.replace(/[^/]*$/,'')+'worlds2026.ics';</script>
</body></html>
"""


def dry_run(events):
    # Shown in this machine's local time zone, the same way iOS converts the UTC times.
    print(f"DRY RUN - feed would contain {len(events)} events (local time)\n")
    day = None
    for e in events:
        s, en = e["start"].astimezone(), e["end"].astimezone()
        if s.date() != day:
            day = s.date()
            print(f"\n{s:%a %d %b %Y}")
        print(f"  {s:%H:%M}-{en:%H:%M}  {e['summary']}")
    print("\nNothing written.")


if __name__ == "__main__":
    events = list(to_events(fetch_matches()))
    if "--write" in sys.argv:
        args = [a for a in sys.argv[1:] if a != "--write"]
        out = Path(args[0] if args else "_site")
        out.mkdir(parents=True, exist_ok=True)
        (out / "worlds2026.ics").write_text(build_ics(events), encoding="utf-8", newline="")
        updated = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
        (out / "index.html").write_text(INDEX_HTML.replace("{updated}", updated), encoding="utf-8")
        print(f"Wrote {len(events)} events to {out / 'worlds2026.ics'}")
    else:
        dry_run(events)
