"""Persistent state store.

Locally  -> a JSON file in the working directory.
On Lambda -> an object in S3 (the filesystem is read-only except /tmp, which is
             wiped on cold start, so it can't hold once-per-day state).
"""

import json

from .config import LOCAL, STATE_BUCKET, STATE_PREFIX, get_logger

log = get_logger(__name__)


def load_json(path, default=None):
    """Read a JSON file, returning `default` if it's missing or unreadable."""
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.debug("load_json(%s) failed: %s", path, e)
        return default


def save_json(path, data):
    """Write `data` as pretty JSON to `path`."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def load_state(name, default=None):
    """Load a JSON state blob by logical name. Returns `default` if missing."""
    if LOCAL:
        return load_json(name, default)

    import boto3

    try:
        s3 = boto3.client("s3")
        obj = s3.get_object(Bucket=STATE_BUCKET, Key=f"{STATE_PREFIX}{name}")
        return json.loads(obj["Body"].read())
    except Exception as e:
        log.debug("load_state(%s) miss: %s", name, e)
        return default


def save_state(name, data):
    """Persist a JSON state blob by logical name."""
    if LOCAL:
        save_json(name, data)
        return

    import boto3

    s3 = boto3.client("s3")
    s3.put_object(
        Bucket=STATE_BUCKET,
        Key=f"{STATE_PREFIX}{name}",
        Body=json.dumps(data).encode(),
        ContentType="application/json",
    )
    log.info("saved state %s to s3://%s/%s%s", name, STATE_BUCKET, STATE_PREFIX, name)
