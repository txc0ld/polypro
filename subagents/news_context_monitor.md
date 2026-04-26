# Subagent — `news_context_monitor`

**Cadence:** every 60s with a 48-hour lookback window.
**PRD section:** §16.2, §9.1.

## Purpose

Read approved public feeds (X API, RSS, sportsbook updates, polling aggregator
deltas, official agency pages) and identify new public information that should
move event probability. Trigger `news_probability_delta` evaluation only when
the integrity rules pass.

## Allowed sources (positive list)

- Official APIs of feeds that permit programmatic access (X, GDELT, NewsAPI,
  AP/Reuters licensed, official government feeds, regulated sportsbooks,
  Kalshi public data)
- Public web pages explicitly marked as crawlable per `robots.txt` and ToS

## Disallowed (hard refusal)

- Anything labeled confidential, embargoed, leaked, hacked, or stolen
- Sources controlled by a participant who can influence the outcome (campaign
  staff on an election market, team-employee accounts on a sports market)
- Private channels (closed Telegram groups, paid leak feeds, restricted Slack
  exports)
- Scraping anything that prohibits scraping in robots.txt or ToS

## Outputs

For each detected change, the monitor writes:

- a candidate trigger that names the market(s) it potentially affects
- the evidence pack: source URL(s), fetched body hash, timestamp, source
  reliability prior, and a short rationale string
- log entries with `actor="news_context_monitor"` for both triggers and
  rejections

The monitor never emits an order — it only invites `news_probability_delta` to
look.
