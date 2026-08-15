"""Centralized follow-eligibility filter.

`follow_rejection_reason` is the single decision point. It works with both a
liker-list entry (only is_private / is_verified known) and a full profile
(follower/following counts known); checks needing an absent field are skipped.
"""

import json

from .config import FOLLOW_FILTER, get_logger

log = get_logger(__name__)


def _relationship_flags(profile):
    """Extract (already_following, followed_by_them) from an IG user object.
    Handles both the nested `friendship_status` block and top-level viewer
    flags. Returns (None, None) when unknown."""
    fs = profile.get("friendship_status") or {}

    already_following = (
        profile.get("following")
        if profile.get("following") is not None
        else fs.get("following")
    )
    if already_following is None:
        already_following = profile.get("followed_by_viewer")

    followed_by_them = fs.get("followed_by")
    if followed_by_them is None:
        followed_by_them = profile.get("follows_viewer")

    return already_following, followed_by_them


def _normalize_profile(profile):
    """Map a liker entry or full profile to a common shape. Missing fields are
    None so checks can be skipped gracefully."""
    already_following, followed_by_them = _relationship_flags(profile)
    return {
        "username": profile.get("username"),
        "user_id": profile.get("user_id") or profile.get("id") or profile.get("pk"),
        "is_private": profile.get("is_private"),
        "is_verified": profile.get("is_verified"),
        "followers": profile.get("follower_count"),
        "following": profile.get("following_count"),
        "already_following": already_following,
        "followed_by_them": followed_by_them,
    }


def follow_rejection_reason(profile):
    """Return a reason string if the profile should NOT be followed, else None."""
    cfg = FOLLOW_FILTER
    p = _normalize_profile(profile)

    if cfg.get("require_private") and p["is_private"] is False:
        return "not private"

    if cfg.get("skip_verified") and p["is_verified"] is True:
        return "verified account"

    if cfg.get("skip_already_following") and p["already_following"] is True:
        return "already following"

    if cfg.get("skip_followed_by") and p["followed_by_them"] is True:
        return "already follows you"

    followers = p["followers"]
    following = p["following"]

    if followers is not None:
        if cfg.get("max_followers") is not None and followers >= cfg["max_followers"]:
            return f"followers {followers} >= max {cfg['max_followers']}"
        if cfg.get("min_followers") is not None and followers < cfg["min_followers"]:
            return f"followers {followers} < min {cfg['min_followers']}"

    if following is not None:
        if cfg.get("max_following") is not None and following >= cfg["max_following"]:
            return f"following {following} >= max {cfg['max_following']}"

    if (
        followers is not None
        and following is not None
        and cfg.get("max_follower_following_gap") is not None
        and (followers - following) > cfg["max_follower_following_gap"]
    ):
        return (
            f"follower-following gap {followers - following} "
            f"> max {cfg['max_follower_following_gap']}"
        )

    return None


def should_follow(profile):
    """Boolean convenience wrapper around follow_rejection_reason()."""
    return follow_rejection_reason(profile) is None


def parse_likers(res):
    """Parse a likers response into a list of follow-eligible user dicts.

    Filters against the raw user object so relationship flags are visible.
    Full follower-count checks happen later once the profile is fetched.
    """
    try:
        data = json.loads(res["body"])
        likers = data.get("users", [])
    except (KeyError, TypeError, json.JSONDecodeError) as e:
        log.error("failed to parse likers JSON: %s", e)
        return []

    eligible = []
    for u in likers:
        reason = follow_rejection_reason(u)
        if reason is None:
            eligible.append(
                {
                    "username": u["username"],
                    "user_id": u["id"],
                    "is_private": u.get("is_private", False),
                    "is_verified": u.get("is_verified", False),
                }
            )
    log.info("parsed %d likers -> %d eligible", len(likers), len(eligible))
    return eligible
