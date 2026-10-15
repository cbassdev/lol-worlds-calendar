# LoL Worlds 2026 calendar

An auto-updating iCalendar feed with every League of Legends Worlds 2026 match
(Play-In, Swiss, Knockouts). Every 15 minutes a GitHub Action pulls the
lolesports.com schedule and republishes the feed to GitHub Pages, so "TBD vs TBD"
turns into the real matchup once it's drawn and scores appear after each match.

## Subscribe

On iPhone, open <https://cbassdev.github.io/lol-worlds-calendar/> and tap
**Subscribe on iPhone**, or add this URL under
Settings → Apps → Calendar → Calendar Accounts → Add Account → Other → Add Subscribed Calendar:

```
webcal://cbassdev.github.io/lol-worlds-calendar/worlds2026.ics
```

Turn **Remove Alerts** off when subscribing to keep the 15-minute reminders.

## Settings

Top of `build_ics.py`: `WATCH_URL`, `ALARM_MINUTES`, `SHOW_RESULTS` (scores in titles
are spoilers), `DURATION_H`.

## Local preview

```
python build_ics.py            # dry run, prints the feed in local time
python build_ics.py --write    # writes _site/worlds2026.ics
```

## If the Action starts failing

The feed uses the same persisted GraphQL query as lolesports.com. If Riot changes
the site, the hash in `HOME_EVENTS_HASH` stops working; the last good feed stays
published. Copy the new `sha256Hash` of the `homeEvents` request from the site's
network tab into `build_ics.py`.

After the final (Nov 14), disable the workflow under Actions → Update Worlds 2026 feed → ⋯ → Disable.
