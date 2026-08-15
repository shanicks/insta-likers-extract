"""AWS Lambda entry point.

Configure the Lambda's handler as:  handler.lambda_handler

Event fields (all optional):
    max_follows    - accounts to follow this run (default 50)
    delay_min      - min seconds between follows (default 30)
    delay_max      - max seconds between follows (default 90)
    max_reel_calls - safety cap on Reels-tab calls (default 20)
    dry_run        - if true, log intended follows without sending them
"""

import json

from insta_follower.config import get_logger
from insta_follower.flow import run

log = get_logger(__name__)


def lambda_handler(event, context=None):
    event = event or {}

    # Support API Gateway style events with a JSON string body.
    if isinstance(event.get("body"), str):
        try:
            event = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            pass

    return run(
        max_follows=event.get("max_follows", 50),
        delay_min=event.get("delay_min", 30),
        delay_max=event.get("delay_max", 90),
        max_reel_calls=event.get("max_reel_calls", 20),
        dry_run=event.get("dry_run", False),
    )


if __name__ == "__main__":
    # Local smoke test: dry run so nothing is actually followed.
    print(json.dumps(lambda_handler({"dry_run": True, "max_follows": 5}), indent=2, default=str))
