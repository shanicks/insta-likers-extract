"""Thin wrappers around the Instagram web endpoints used by the follow flow.

Each function loads auth, builds the request from a header template, and
returns parsed data. Cookie-expiry (HTTP 302) triggers an email alert.
"""

import json

import requests

from .config import get_logger
from .session import (
    get_instagram_cookies,
    get_headers,
    cookie_header,
    send_alert_email,
    update_cookies_from_response,
)
from .filters import follow_rejection_reason

log = get_logger(__name__)

GRAPHQL_URL = "https://www.instagram.com/graphql/query"
REQUEST_TIMEOUT = 30  # seconds


def extract_likers(media_id):
    """Return {"status": ..., "body": <raw json text>} for a media's likers."""
    cookies = get_instagram_cookies()
    url = f"https://www.instagram.com/api/v1/media/{media_id}/likers/"

    headers = get_headers("media_likers_headers")
    headers["X-CSRFToken"] = cookies["csrftoken"]
    headers["X-IG-WWW-Claim"] = cookies.get("claim", "")
    headers["Cookie"] = cookie_header(cookies)

    log.debug("fetching likers for media %s", media_id)
    try:
        response = requests.get(
            url, headers=headers, allow_redirects=False, timeout=REQUEST_TIMEOUT
        )
    except requests.RequestException as e:
        log.error("likers request for media %s failed: %s", media_id, e)
        return {"status": "error", "error": str(e)}

    update_cookies_from_response(response)

    if response.status_code == 302:
        log.warning("likers for media %s -> 302 (cookies expired)", media_id)
        send_alert_email("Instagram cookies expired.", cookies)
        return {"status": "expired"}

    if response.status_code != 200:
        log.warning("likers for media %s -> %s", media_id, response.status_code)
        return {"status": "error", "status_code": response.status_code}

    log.info("likers for media %s -> 200", media_id)
    return {"status": "ok", "status_code": response.status_code, "body": response.text}


def next_reels():
    """Return {"status": ..., "body": [shortcode, ...]} from the Reels tab."""
    cookies = get_instagram_cookies()

    headers = get_headers("get_reels_headers")
    headers["X-CSRFToken"] = cookies["csrftoken"]
    headers["X-FB-LSD"] = cookies.get("lsd", "")
    headers["Cookie"] = cookie_header(cookies)

    variables = {"data": {"container_module": "clips_tab_desktop_page"}, "first": 5}
    payload = {
        "doc_id": "25956561807372407",
        "variables": json.dumps(variables, separators=(",", ":")),
    }

    log.debug("fetching reels from clips tab")
    try:
        response = requests.post(
            GRAPHQL_URL, headers=headers, data=payload,
            allow_redirects=False, timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        log.error("reels request failed: %s", e)
        return {"status": "error", "error": str(e)}

    update_cookies_from_response(response)

    if response.status_code == 302:
        log.warning("reels request -> 302 (cookies expired)")
        send_alert_email("Instagram cookies expired.", cookies)
        return {"status": "expired"}

    if response.status_code != 200:
        log.warning("reels request -> %s", response.status_code)
        return {"status": "error", "error": f"reels failed ({response.status_code})"}

    try:
        parsed = json.loads(response.text)
        shortcodes = [
            edge["node"]["media"]["code"]
            for edge in parsed["data"]["xdt_api__v1__clips__home__connection_v2"]["edges"]
        ]
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        log.error("failed to parse reels response: %s", e)
        return {"status": "error", "error": "unexpected reels response shape"}

    log.info("fetched %d reel shortcodes", len(shortcodes))
    return {"status": "ok", "status_code": response.status_code, "body": shortcodes}


def fetch_profile(username, user_id):
    """Fetch a full profile and evaluate it against the follow filter."""
    if not username or not user_id:
        log.error("fetch_profile called without username/user_id")
        return {"status": "error", "error": "username and user_id required"}

    cookies = get_instagram_cookies()

    headers = get_headers("profile_query_headers")
    headers["X-CSRFToken"] = cookies["csrftoken"]
    headers["X-FB-LSD"] = cookies.get("lsd", "")
    headers["Cookie"] = cookie_header(cookies)
    headers["Referer"] = f"https://www.instagram.com/{username}/"

    payload = get_headers("profile_query_payload")
    payload["variables"]["id"] = user_id
    payload["variables"] = json.dumps(payload["variables"])

    log.debug("fetching profile %s (%s)", username, user_id)
    try:
        response = requests.post(
            GRAPHQL_URL, headers=headers, data=payload,
            allow_redirects=False, timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        log.error("profile request for %s failed: %s", username, e)
        return {"status": "error", "error": str(e)}

    update_cookies_from_response(response)

    if response.status_code == 302:
        log.warning("profile %s -> 302 (cookies expired)", username)
        send_alert_email("Instagram cookies expired.", cookies)
        return {"status": "expired"}

    if response.status_code != 200:
        log.warning("profile %s -> %s", username, response.status_code)
        return {"status": "error", "status_code": response.status_code}

    try:
        user = json.loads(response.text)["data"]["user"]
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        log.error("failed to parse profile response for %s: %s", username, e)
        return {"status": "error", "error": "unexpected profile response shape"}

    reason = follow_rejection_reason(user)
    log.info(
        "profile %s: should_follow=%s%s",
        username, reason is None, f" ({reason})" if reason else "",
    )
    return {
        "status": "ok",
        "status_code": response.status_code,
        "body": user,
        "should_follow": reason is None,
        "rejection_reason": reason,
    }


def send_follow(target_user_id):
    """Send a follow request to `target_user_id`. Returns the parsed response."""
    cookies = get_instagram_cookies()

    headers = get_headers("send_follow_headers")
    headers["X-CSRFToken"] = cookies["csrftoken"]
    headers["X-FB-LSD"] = cookies["lsd"]
    headers["Cookie"] = cookie_header(cookies)

    payload = get_headers("send_follow_payload")
    payload["lsd"] = cookies["lsd"]
    payload["variables"]["target_user_id"] = str(target_user_id)
    payload["variables"] = json.dumps(payload["variables"])

    log.debug("sending follow to %s", target_user_id)
    try:
        response = requests.post(
            f"{GRAPHQL_URL}/", headers=headers, data=payload,
            allow_redirects=False, timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        log.error("follow request for %s failed: %s", target_user_id, e)
        return {"status": "error", "error": str(e)}

    update_cookies_from_response(response)

    # Expired session / stale tokens: IG redirects to login or 401/403s.
    if response.status_code in (302, 401, 403):
        log.warning("follow %s -> %s (cookies expired)", target_user_id, response.status_code)
        send_alert_email("Instagram cookies expired.", cookies)
        return {"status": "expired"}

    try:
        data = response.json()
    except json.JSONDecodeError:
        log.error("follow %s -> %s but body was not JSON", target_user_id, response.status_code)
        return {"status": "error", "status_code": response.status_code}

    # A login_required message can also come back with a 200.
    if data.get("message") == "login_required" or data.get("require_login"):
        log.warning("follow %s reported login_required (cookies expired)", target_user_id)
        send_alert_email("Instagram cookies expired.", cookies)
        return {"status": "expired"}

    # The GraphQL follow mutation reports the resulting relationship here.
    friendship = (data.get("data") or {}).get("xdt_create_friendship") or {}
    result_state = friendship.get("friendship_status", {})
    if data.get("errors"):
        log.warning("follow %s returned errors: %s", target_user_id, data["errors"])
    else:
        log.info(
            "follow %s -> %s (following=%s, outgoing_request=%s)",
            target_user_id,
            response.status_code,
            result_state.get("following"),
            result_state.get("outgoing_request"),
        )
    return data
