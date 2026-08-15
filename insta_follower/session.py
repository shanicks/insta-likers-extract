"""Instagram session concerns: cookies, request headers, alerts, and helpers.

Cookies are loaded once per run and cached in memory. Session values are kept
fresh in two ways:

  * update_cookies_from_response() captures values IG rotates on API responses
    (csrftoken/sessionid via Set-Cookie, claim via x-ig-set-www-claim).
  * refresh_page_tokens() loads the Instagram HTML homepage once at the start
    of a run and scrapes the short-lived page tokens (lsd, fb_dtsg, csrftoken)
    that are embedded in the page but never returned by API endpoints.

Together these let a pasted session sustain itself until sessionid itself dies.
"""

import re
import json

import requests

from .config import LOCAL, HEADER_TEMPLATES, LOCAL_SETTINGS, COOKIES_PARAM, get_logger

log = get_logger(__name__)

# In-memory cookie cache for the current run.
_cookies = None
_dirty = False  # True once a refreshed value has been captured

# Auth-relevant cookies IG rotates via Set-Cookie that we persist. We
# deliberately skip volatile routing hints like `rur`/`mid`, which change on
# almost every request and aren't needed for auth.
_REFRESHABLE_COOKIES = ("csrftoken", "sessionid")


def _load_cookies():
    """Load the cookie dict from the backing store (local file or SSM)."""
    if LOCAL:
        with open(LOCAL_SETTINGS) as f:
            return json.load(f)

    import boto3

    ssm = boto3.client("ssm")
    param = ssm.get_parameter(Name=COOKIES_PARAM, WithDecryption=True)
    return json.loads(param["Parameter"]["Value"])


def get_instagram_cookies():
    """Return the cached cookie dict, loading it on first use."""
    global _cookies
    if _cookies is None:
        _cookies = _load_cookies()
    return _cookies


def update_cookies_from_response(response):
    """Capture any refreshed session values from a response.

    Reads rotated cookies (Set-Cookie) and the refreshed claim
    (x-ig-set-www-claim header), updating the in-memory cache. Marks the cache
    dirty so persist_cookies() will write it back at the end of the run.
    """
    global _dirty
    cookies = get_instagram_cookies()

    for name in _REFRESHABLE_COOKIES:
        new_val = response.cookies.get(name)
        if new_val and new_val != cookies.get(name):
            log.info("refreshed cookie: %s", name)
            cookies[name] = new_val
            _dirty = True

    new_claim = response.headers.get("x-ig-set-www-claim")
    if new_claim and new_claim != cookies.get("claim"):
        log.info("refreshed claim from response header")
        cookies["claim"] = new_claim
        _dirty = True


def persist_cookies():
    """Write the (possibly refreshed) cookie cache back to the store if dirty."""
    global _dirty
    if not _dirty or _cookies is None:
        return

    if LOCAL:
        with open(LOCAL_SETTINGS, "w") as f:
            json.dump(_cookies, f, indent=2)
        log.info("persisted refreshed cookies to %s", LOCAL_SETTINGS)
    else:
        import boto3

        ssm = boto3.client("ssm")
        ssm.put_parameter(
            Name=COOKIES_PARAM,
            Value=json.dumps(_cookies),
            Type="SecureString",
            Overwrite=True,
        )
        log.info("persisted refreshed cookies to SSM %s", COOKIES_PARAM)
    _dirty = False


# Patterns for the tokens IG embeds in the homepage HTML/JS bootstrap.
_TOKEN_PATTERNS = {
    "lsd": re.compile(r'"LSD",\[\],\{"token":"([^"]+)"'),
    "fb_dtsg": re.compile(r'"DTSGInitialData",\[\],\{"token":"([^"]+)"'),
    "csrftoken": re.compile(r'"csrf_token":"([^"]+)"'),
}
# Fallback patterns (IG markup varies between builds/logged-in states).
_TOKEN_FALLBACKS = {
    "lsd": [re.compile(r'name="lsd"\s+value="([^"]+)"'), re.compile(r'\\"lsd\\":\\"([^"]+)\\"')],
    "fb_dtsg": [re.compile(r'name="fb_dtsg"\s+value="([^"]+)"')],
}


def _search_token(patterns, html):
    for pat in patterns:
        m = pat.search(html)
        if m:
            return m.group(1)
    return None


def refresh_page_tokens():
    """Scrape fresh lsd/fb_dtsg/csrftoken from the Instagram homepage HTML.

    These page tokens are embedded in the HTML bootstrap and are never returned
    by API endpoints, so they can't be picked up by update_cookies_from_response.
    Loading the page once per run keeps them fresh until sessionid itself dies.

    Returns {"status": "ok"} on success, {"status": "expired"} if the session
    is no longer logged in, or {"status": "error"} on any failure. Never raises.
    """
    global _dirty
    cookies = get_instagram_cookies()

    headers = get_headers("get_reels_headers")  # a browser-like header set
    # Strip POST/XHR-specific headers — this is a GET document navigation.
    # (Content-Length in particular makes the server await a body -> 408.)
    for h in (
        "Content-Type", "Content-Length", "X-CSRFToken", "X-FB-LSD",
        "X-Root-Field-Name", "X-FB-Friendly-Name", "X-FB-Friendly-Name",
        "X-BLOKS-VERSION-ID", "X-IG-App-ID", "X-ASBD-ID", "TE",
    ):
        headers.pop(h, None)
    headers["Cookie"] = cookie_header(cookies)
    headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    headers["Sec-Fetch-Dest"] = "document"
    headers["Sec-Fetch-Mode"] = "navigate"
    headers["Sec-Fetch-Site"] = "none"

    try:
        resp = requests.get(
            "https://www.instagram.com/",
            headers=headers,
            allow_redirects=False,
            timeout=(10, 60),  # (connect, read): the homepage HTML is large
        )
    except requests.RequestException as e:
        log.error("token refresh request failed: %s", e)
        return {"status": "error"}

    update_cookies_from_response(resp)

    if resp.status_code in (301, 302):
        log.warning("token refresh -> %s (cookies expired)", resp.status_code)
        return {"status": "expired"}
    if resp.status_code != 200:
        log.warning("token refresh -> %s", resp.status_code)
        return {"status": "error"}

    html = resp.text
    # If we were served a logged-out page, the session is dead.
    if '"viewerId":null' in html or '"viewer":null' in html:
        log.warning("token refresh: served logged-out page (cookies expired)")
        return {"status": "expired"}

    found = 0
    for key, pattern in _TOKEN_PATTERNS.items():
        value = pattern.search(html)
        value = value.group(1) if value else _search_token(_TOKEN_FALLBACKS.get(key, []), html)
        if value and value != cookies.get(key):
            log.info("refreshed page token: %s", key)
            cookies[key] = value
            _dirty = True
            found += 1
        elif value:
            found += 1

    if not found:
        log.warning("token refresh: no tokens found in page (markup may have changed)")
        return {"status": "error"}

    log.info("token refresh ok (%d/%d tokens present)", found, len(_TOKEN_PATTERNS))
    return {"status": "ok"}


def get_headers(name):
    """Return a copy of a named header template.

    `requests` only decodes gzip/deflate without extra packages. Templates
    copied from the browser may advertise br/zstd, which yields undecodable
    bytes -> JSON errors, so we force a safe Accept-Encoding everywhere.
    """
    with open(HEADER_TEMPLATES) as f:
        templates = json.load(f)
    headers = templates[name].copy()
    if "Accept-Encoding" in headers:
        headers["Accept-Encoding"] = "gzip, deflate"
    return headers


def cookie_header(cookies):
    """Build the `Cookie:` header value from the core auth cookies."""
    return (
        f'csrftoken={cookies["csrftoken"]}; '
        f'sessionid={cookies["sessionid"]}; '
        f'ds_user_id={cookies["ds_user_id"]}'
    )


def send_alert_email(message, cookies=None):
    """Email an alert (e.g. expired cookies). No-op logging when local."""
    if LOCAL:
        log.warning("[LOCAL] email alert suppressed: %s", message)
        return

    import boto3

    address = (cookies or {}).get("email")
    ses = boto3.client("ses")
    ses.send_email(
        Source=address,
        Destination={"ToAddresses": [address]},
        Message={
            "Subject": {"Data": "Instagram Cookies Expired"},
            "Body": {"Text": {"Data": message}},
        },
    )


def shortcode_to_media_id(shortcode: str) -> int:
    """Convert an Instagram media shortcode (from a URL) to its numeric id."""
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    num = 0
    for char in shortcode:
        num = num * 64 + alphabet.index(char)
    return num
