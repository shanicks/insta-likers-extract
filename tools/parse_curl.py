"""
Parse a copied "Copy as cURL" command (from Firefox/Chrome DevTools) and
extract the Instagram auth values we need into local_settings.json shape.

Works with BOTH:
  - cmd.exe cURL  (caret-escaped: ^" , ^& , ^%^3A ...)
  - POSIX cURL    (single-quoted, %-literal)

Pure string parsing, so it also runs fine on AWS Lambda (no sqlite / browser).

Usage:
    # from a file containing the pasted curl
    python parse_curl.py curl.txt

    # from stdin (paste, then Ctrl-Z Enter on Windows / Ctrl-D on POSIX)
    python parse_curl.py -

    # write/merge straight into local_settings.json
    python parse_curl.py curl.txt --write
"""

import argparse
import json
import re
import sys
from urllib.parse import unquote, parse_qs


# Keys we can pull out of a request and where they come from.
# Anything not found in the curl is left untouched when merging.
COOKIE_KEYS = ("sessionid", "csrftoken", "ds_user_id")
HEADER_KEYS = {
    "x-csrftoken": "csrftoken",
    "x-ig-www-claim": "claim",
    "x-fb-lsd": "lsd",
}
DATA_KEYS = ("lsd", "fb_dtsg")


def _decmd(text: str) -> str:
    """Undo cmd.exe caret escaping. Removing every '^' turns ^" -> ", ^& -> &,
    and ^%^3A -> %3A (still URL-encoded, decoded later). POSIX curl has no
    carets so this is a no-op there."""
    return text.replace("^", "")


def _find_all(pattern: str, text: str):
    return re.findall(pattern, text, flags=re.IGNORECASE | re.DOTALL)


def _extract_quoted(flag: str, text: str):
    """Return list of values passed to a curl flag, handling both ' and " quotes."""
    # -H "Name: val"   or   -H 'Name: val'
    dq = _find_all(rf"{flag}\s+\"(.*?)\"", text)
    sq = _find_all(rf"{flag}\s+'(.*?)'", text)
    return dq + sq


def _parse_cookie_header(cookie_value: str) -> dict:
    jar = {}
    for part in cookie_value.split(";"):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        jar[k.strip()] = unquote(v.strip())
    return jar


def parse_curl(curl_text: str) -> dict:
    """Extract auth-relevant fields from a curl command string."""
    text = _decmd(curl_text)
    result = {}

    # --- Headers ---
    headers = {}
    for h in _extract_quoted("-H", text):
        if ":" not in h:
            continue
        name, _, value = h.partition(":")
        headers[name.strip().lower()] = value.strip()

    # Cookie header -> individual cookies
    if "cookie" in headers:
        jar = _parse_cookie_header(headers["cookie"])
        for key in COOKIE_KEYS:
            if key in jar:
                result[key] = jar[key]

    # Direct header -> setting mappings (csrftoken, claim, lsd)
    for header_name, setting_key in HEADER_KEYS.items():
        if header_name in headers and headers[header_name]:
            result[setting_key] = unquote(headers[header_name])

    # --- Body (--data-raw / --data / -d) ---
    body = None
    for flag in ("--data-raw", "--data-binary", "--data", "-d"):
        vals = _extract_quoted(flag, text)
        if vals:
            body = vals[0]
            break

    if body:
        form = parse_qs(body, keep_blank_values=True)
        for key in DATA_KEYS:
            if key in form and form[key]:
                result[key] = unquote(form[key][0])
        # av is the logged-in actor id; handy to keep in sync
        if "av" in form and form["av"]:
            result.setdefault("ds_user_id", unquote(form["av"][0]))

    return result


def merge_into_settings(parsed: dict, path: str = "local_settings.json") -> dict:
    try:
        with open(path) as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings = {}
    settings.update(parsed)
    with open(path, "w") as f:
        json.dump(settings, f, indent=2)
    return settings


def main():
    ap = argparse.ArgumentParser(description="Parse a cURL command into IG settings.")
    ap.add_argument("source", help="Path to a file with the curl command, or '-' for stdin.")
    ap.add_argument("--write", action="store_true", help="Merge into local_settings.json.")
    ap.add_argument("--settings", default="local_settings.json", help="Settings file path.")
    args = ap.parse_args()

    if args.source == "-":
        curl_text = sys.stdin.read()
    else:
        with open(args.source, encoding="utf-8") as f:
            curl_text = f.read()

    parsed = parse_curl(curl_text)
    if not parsed:
        print("No recognizable fields found. Is this a valid curl command?", file=sys.stderr)
        sys.exit(1)

    if args.write:
        merged = merge_into_settings(parsed, args.settings)
        print(f"Updated {args.settings} with: {', '.join(sorted(parsed))}")
        print(json.dumps(merged, indent=2))
    else:
        print("Parsed values (use --write to merge into local_settings.json):")
        print(json.dumps(parsed, indent=2))


if __name__ == "__main__":
    main()
