"""Relationship-graph helpers for the "no friend connection" filter.

Definitions (from your account's perspective):
    my followers  - accounts that follow me
    my following  - accounts I follow
    friends       - my followers AND my following (mutual)
    C's mutuals   - accounts I follow that also follow C (Instagram's
                    "Followed by ... you follow" set; readable even when C
                    is private)

Rejection rule for a candidate C:
    Reject C if any of C's mutuals also follows me back (i.e. is a friend).
    -> reject if (C's mutuals ∩ my_followers) is non-empty.

Only my-side lists are needed, so the private-account wall on C is avoided.
"""

import time
from datetime import datetime, timezone

import requests

from .config import get_logger
from .session import get_instagram_cookies, get_headers, cookie_header, send_alert_email
from .storage import load_state, save_state

log = get_logger(__name__)

# Persisted my-followers set, refreshed at most once per calendar day (UTC).
FOLLOWERS_CACHE = "my_followers_cache.json"


def _today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _v1_headers(cookies, referer="https://www.instagram.com/"):
    """Auth headers for v1 friendships endpoints."""
    headers = get_headers("friendships_headers")
    headers["X-CSRFToken"] = cookies["csrftoken"]
    headers["X-IG-WWW-Claim"] = cookies.get("claim", "")
    headers["Cookie"] = cookie_header(cookies)
    headers["Referer"] = referer
    return headers


def _paginate_users(url, cookies, max_pages=None, page_size=100):
    """Walk a paginated v1 user list and return a set of string user ids."""
    users = set()
    max_id = None
    pages = 0

    while True:
        params = {"count": page_size, "search_surface": "follow_list_page"}
        if max_id:
            params["max_id"] = max_id

        try:
            resp = requests.get(
                url, headers=_v1_headers(cookies), params=params,
                allow_redirects=False, timeout=30,
            )
        except requests.RequestException as e:
            log.error("%s request failed: %s", url, e)
            break

        if resp.status_code == 302:
            log.warning("%s -> 302 (cookies expired)", url)
            send_alert_email("Instagram cookies expired.", cookies)
            break
        if resp.status_code != 200:
            log.warning("%s -> %s", url, resp.status_code)
            break

        try:
            data = resp.json()
        except ValueError as e:
            log.error("%s returned non-JSON body: %s", url, e)
            break

        for u in data.get("users", []):
            uid = u.get("pk") or u.get("id")
            if uid is not None:
                users.add(str(uid))

        max_id = data.get("next_max_id")
        pages += 1
        # Heartbeat at INFO for long multi-page crawls so there's no silent
        # pause; single-page calls (e.g. mutual_followers) stay quiet.
        if pages > 1 and pages % 3 == 0:
            log.info("still crawling %s: %d pages, %d ids so far",
                     url.rsplit("/friendships/", 1)[-1], pages, len(users))
        else:
            log.debug("paginated %s: page %d, %d ids so far", url, pages, len(users))
        if not max_id:
            break
        if max_pages and pages >= max_pages:
            log.debug("stopping pagination at max_pages=%d", max_pages)
            break
        time.sleep(1)  # be gentle with the API

    return users


def get_followers(user_id, max_pages=None):
    """Return the set of user ids that follow `user_id`."""
    cookies = get_instagram_cookies()
    url = f"https://www.instagram.com/api/v1/friendships/{user_id}/followers/"
    return _paginate_users(url, cookies, max_pages)


def get_my_followers(use_cache=True, max_pages=None):
    """Return the set of user ids that follow ME.

    The full crawl runs at most once per calendar day (UTC): if the cache was
    written today, the stored set is reused. Pass use_cache=False to force a
    refresh.
    """
    if use_cache:
        cached = load_state(FOLLOWERS_CACHE, None)
        if cached and cached.get("date") == _today():
            log.info("my_followers served from cache (%d)", len(cached.get("followers", [])))
            return set(cached.get("followers", []))

    cookies = get_instagram_cookies()
    log.info("no cache for today; crawling my followers from API (this may take a while)...")
    followers = get_followers(cookies["ds_user_id"], max_pages)

    if followers:
        save_state(
            FOLLOWERS_CACHE,
            {"date": _today(), "ts": time.time(), "followers": sorted(followers)},
        )
        log.info("my_followers refreshed from API (%d)", len(followers))
    return followers


def get_mutual_followers(user_id, max_pages=None):
    """Return the set of ids of accounts I follow that also follow `user_id`
    (Instagram's mutual-followers list). Readable even if `user_id` is private.
    """
    cookies = get_instagram_cookies()
    url = f"https://www.instagram.com/api/v1/friendships/{user_id}/mutual_followers/"
    return _paginate_users(url, cookies, max_pages)


def friend_connected(user_id, my_followers, max_pages=None):
    """Return the id of the first friend (a mutual follower who follows me back)
    that follows `user_id`, or None if there's no such connection.

    A non-None result means the candidate is connected to your friend circle
    and should be rejected.
    """
    mutuals = get_mutual_followers(user_id, max_pages=max_pages)
    for uid in mutuals:
        if uid in my_followers:
            log.debug("user %s friend-connected via %s", user_id, uid)
            return uid
    log.debug("user %s clear (%d mutuals, none are friends)", user_id, len(mutuals))
    return None
