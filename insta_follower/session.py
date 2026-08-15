"""Instagram session concerns: cookies, request headers, alerts, and helpers."""

import json

from .config import LOCAL, HEADER_TEMPLATES, LOCAL_SETTINGS, get_logger

log = get_logger(__name__)


def get_instagram_cookies():
    """Load the Instagram auth cookies/tokens.

    Locally from LOCAL_SETTINGS; on Lambda from Secrets Manager.
    """
    if LOCAL:
        with open(LOCAL_SETTINGS) as f:
            return json.load(f)

    import boto3

    secrets = boto3.client("secretsmanager")
    secret = secrets.get_secret_value(SecretId="instagram_cookies")["SecretString"]
    return json.loads(secret)


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
