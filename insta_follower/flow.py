"""The single end-to-end flow: discover -> filter -> follow.

    1. Pull reels from the Reels tab, repeatedly, until enough follow-eligible
       accounts are collected (or the reel-call cap is hit).
    2. For each reel, extract likers and keep only those passing the filter,
       excluding anyone connected to a friend of mine.
    3. Follow up to `max_follows` collected accounts, with a randomized delay.
"""

import time
import random

from .config import get_logger
from .session import shortcode_to_media_id
from .filters import parse_likers
from .instagram_api import extract_likers, next_reels, send_follow
from .relationships import get_my_followers, friend_connected

log = get_logger(__name__)


def collect_candidates(max_needed, max_reel_calls, my_followers):
    """Gather up to `max_needed` follow-eligible, non-friend-connected users."""
    candidates = []
    seen = set()

    for call in range(max_reel_calls):
        if len(candidates) >= max_needed:
            break

        log.info("reel batch %d/%d (have %d/%d candidates)",
                 call + 1, max_reel_calls, len(candidates), max_needed)
        reels = next_reels()
        if reels.get("status") != "ok":
            log.warning("stopping: next_reels failed: %s", reels.get("error"))
            break

        for shortcode in reels.get("body", []):
            if len(candidates) >= max_needed:
                break

            media_id = shortcode_to_media_id(shortcode)
            log.debug("processing reel %s (media %s)", shortcode, media_id)
            likers_res = extract_likers(media_id)
            if likers_res.get("status") != "ok":
                log.debug("skip reel %s: likers status %s", shortcode, likers_res.get("status"))
                continue

            for user in parse_likers(likers_res):
                uid = user["user_id"]
                if uid in seen:
                    continue
                seen.add(uid)

                connected = friend_connected(uid, my_followers)
                if connected is not None:
                    log.info("skip %s: friend-connected via %s", user["username"], connected)
                    continue

                candidates.append(user)
                log.info("candidate %d/%d: %s", len(candidates), max_needed, user["username"])
                if len(candidates) >= max_needed:
                    break

    return candidates


def run(max_follows=50, delay_min=30, delay_max=90, max_reel_calls=20, dry_run=False):
    """Execute the full flow. Returns a summary dict."""
    log.info(
        "run start: max_follows=%s delay=%s-%ss max_reel_calls=%s dry_run=%s",
        max_follows, delay_min, delay_max, max_reel_calls, dry_run,
    )

    my_followers = get_my_followers()
    log.info("my_followers set size: %d", len(my_followers))

    candidates = collect_candidates(max_follows, max_reel_calls, my_followers)
    if len(candidates) < max_follows:
        log.warning(
            "collected only %d/%d candidates (reels/likers exhausted or heavily filtered)",
            len(candidates), max_follows,
        )
    else:
        log.info("collected %d candidates", len(candidates))

    followed = []
    targets = candidates[:max_follows]
    for i, user in enumerate(targets):
        if dry_run:
            log.info("[dry_run] would follow %s (%s)", user["username"], user["user_id"])
            followed.append({"user_id": user["user_id"], "username": user["username"], "dry_run": True})
        else:
            log.info("following %s (%s) [%d/%d]", user["username"], user["user_id"], i + 1, len(targets))
            result = send_follow(user["user_id"])
            if result.get("status") == "error" or result.get("errors"):
                log.warning("follow failed for %s: %s", user["username"], result)
            followed.append({"user_id": user["user_id"], "username": user["username"], "result": result})
            if i < len(targets) - 1:
                time.sleep(random.uniform(delay_min, delay_max))

    log.info("run done: followed %d of %d candidates", len(followed), len(candidates))
    return {
        "status": "ok",
        "candidates_found": len(candidates),
        "followed_count": len(followed),
        "followed": followed,
    }
