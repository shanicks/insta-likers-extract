"""Central configuration: environment detection, logging, and filter thresholds."""

import os
import logging

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
# The AWS Lambda runtime always sets AWS_LAMBDA_FUNCTION_NAME. If it's absent,
# we're running locally.
LOCAL = "AWS_LAMBDA_FUNCTION_NAME" not in os.environ

# Path to the browser-captured header templates (relative to repo root).
HEADER_TEMPLATES = os.environ.get("HEADER_TEMPLATES", "header_templates.json")

# Local cookie file used when LOCAL is True.
LOCAL_SETTINGS = os.environ.get("LOCAL_SETTINGS", "local_settings.json")

# SSM Parameter Store name holding the Instagram cookies JSON (SecureString),
# used when running on Lambda.
COOKIES_PARAM = os.environ.get("COOKIES_PARAM", "/insta-follower/cookies")


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
def get_logger(name):
    """Return a module logger. On Lambda the runtime configures the root
    handler, so we only set a handler/level when running locally."""
    logger = logging.getLogger(name)
    if LOCAL and not logging.getLogger().handlers and not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    elif not LOCAL:
        logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))
    return logger


# ---------------------------------------------------------------------------
# Follow-eligibility filter thresholds
# ---------------------------------------------------------------------------
# Tune in one place. Set a value to None to disable that check.
FOLLOW_FILTER = {
    "require_private": True,             # only follow private accounts
    "max_followers": 1000,             # reject if follower_count >= this
    "min_followers": None,             # reject if follower_count < this
    "max_following": None,             # reject if following_count >= this
    "max_follower_following_gap": 100,  # reject if (followers - following) > this
    "skip_verified": True,             # reject verified accounts
    "skip_already_following": True,     # reject accounts you already follow
    "skip_followed_by": True,          # reject accounts that already follow you
    # The "no friend connection" check lives in relationships.py, since it
    # needs extra API calls (my followers + the candidate's mutual followers).
}
