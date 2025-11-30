import json
import boto3
import os
from datetime import datetime

LOCAL = os.environ.get("LOCAL", "0") == "1"
SWIPE_LIMIT = 100


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default


daily = load_json("daily_swipes.json", {"date": "", "count": 0})


def save_user_list(res):
    try:
        data = json.loads(res["body"])
        likers = data.get("users", [])  # adjust key if different in response
        # build a list of dicts with only usernames
        user_list = [
            {
                "username": u["username"],
                "is_private": u.get("is_private", False),
                "user_id": u["id"],
            }
            for u in likers
            if u.get("is_private")
        ]
        # save to file
        with open("user_list.json", "w") as f:
            json.dump(user_list, f, indent=2)
        print(f"Saved {len(user_list)} usernames to user_list.json")
    except Exception as e:
        print("Failed to parse likers JSON:", e)


def get_headers(name):
    with open("header_templates.json") as f:
        headers = json.load(f)
    return headers[name].copy()


def send_alert_email(message, cookies):
    if LOCAL:
        print("[LOCAL] Email alert:", message)
        return
    else:
        ses = boto3.client("ses")
        ses.send_email(
            Source=f"{cookies['media_id']}",
            Destination={"ToAddresses": [f"{cookies['media_id']}"]},
            Message={
                "Subject": {"Data": "Instagram Cookies Expired"},
                "Body": {"Text": {"Data": message}},
            },
        )


def get_instagram_cookies():
    if LOCAL:
        # load from local file for easy testing
        with open("local_settings.json") as f:
            return json.load(f)

    else:
        secrets = boto3.client("secretsmanager")
        secret = secrets.get_secret_value(SecretId="instagram_cookies")["SecretString"]
        return json.loads(secret)


def shortcode_to_media_id(shortcode: str) -> int:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
    num = 0
    for char in shortcode:
        num = num * 64 + alphabet.index(char)
    return num


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def check_daily_reset():
    today = datetime.now().strftime("%Y-%m-%d")
    if daily["date"] != today:
        daily["date"] = today
        daily["count"] = 0
        save_json("daily_swipes.json", daily)


def can_swipe():
    check_daily_reset()
    return daily["count"] < SWIPE_LIMIT


def increment_swipe():
    daily["count"] += 1
    save_json("daily_swipes.json", daily)


def decrement_swipe():
    if daily["count"] > 0:
        daily["count"] -= 1
        save_json("daily_swipes.json", daily)
