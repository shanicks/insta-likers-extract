# insta-follower

A single-Lambda Instagram auto-follow bot. It discovers accounts from the Reels
tab, filters them by follow-eligibility rules, and follows the ones that pass.

## Flow

1. Pull reels from the Reels tab, repeatedly, until enough follow-eligible
   accounts are collected.
2. For each reel, extract its likers and keep only those passing the centralized
   filter, excluding anyone connected to a friend of yours.
3. Follow up to `max_follows` accounts, with a randomized delay between each.

## Structure

```
handler.py                     Lambda entry point (handler.lambda_handler)
insta_follower/
  config.py                    env detection, logging, FOLLOW_FILTER thresholds
  session.py                   cookies, headers, email alerts, media-id helper
  filters.py                   follow-eligibility filter + liker parsing
  instagram_api.py             IG endpoints: likers, reels, profile, follow
  relationships.py             followers / mutual-followers graph
  flow.py                      orchestration: discover -> filter -> follow
tools/
  parse_curl.py                import cookies from a copied browser cURL
header_templates.json          per-endpoint request header/payload templates
local_settings.json            local auth cookies (gitignored)
local_settings_example.json    template for local_settings.json
```

## Local usage

```powershell
# Refresh cookies from a copied cURL (DevTools -> Copy as cURL)
venv\Scripts\python tools\parse_curl.py curl.txt --write

# Dry run (logs intended follows without sending them)
venv\Scripts\python handler.py
```

## Configuration

Event fields (all optional): `max_follows`, `delay_min`, `delay_max`,
`max_reel_calls`, `dry_run`.

Environment variables:
- `LOG_LEVEL` - logging level (default INFO)
- `HEADER_TEMPLATES`, `LOCAL_SETTINGS` - override default file paths

Filter thresholds live in `insta_follower/config.py` (`FOLLOW_FILTER`).
