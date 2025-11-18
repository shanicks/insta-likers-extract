import json
import os
import boto3
import requests

LOCAL = os.environ.get("LOCAL", "0") == "1"


def get_instagram_cookies():
    if LOCAL:
        # load from local file for easy testing
        with open("local_settings.json") as f:
            return json.load(f)

    else:
        secrets = boto3.client("secretsmanager")
        secret = secrets.get_secret_value(SecretId="instagram_cookies")["SecretString"]
        return json.loads(secret)


def send_alert_email(message):
    if LOCAL:
        print("[LOCAL] Email alert:", message)
        return

    ses = boto3.client("ses")
    ses.send_email(
        Source=f"{cookies['media_id']}",
        Destination={"ToAddresses": [f"{cookies['media_id']}"]},
        Message={
            "Subject": {"Data": "Instagram Cookies Expired"},
            "Body": {"Text": {"Data": message}},
        },
    )


def lambda_handler(event, context):
    cookies = get_instagram_cookies()

    url = f"https://www.instagram.com/api/v1/media/{cookies['media_id']}/likers/"

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "X-CSRFToken": cookies["csrftoken"],
        "X-IG-App-ID": "936619743392459",
        "X-ASBD-ID": "359341",
        "X-IG-WWW-Claim": cookies.get("claim", ""),
        "Cookie": f'csrftoken={cookies["csrftoken"]}; '
        f'sessionid={cookies["sessionid"]}; '
        f'ds_user_id={cookies["ds_user_id"]}',
        "X-Web-Session-ID": "bx6wd1:id03lb:ld0orq",
        "X-Requested-With": "XMLHttpRequest",
        "Alt-Used": "www.instagram.com",
        "Connection": "keep-alive",
        "Referer": "https://www.instagram.com/p/DQRZrddDN0y/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "Priority": "u=0",
        "TE": "trailers",
    }

    # IMPORTANT: don't auto-follow redirects
    response = requests.get(url, headers=headers, allow_redirects=False)

    if response.status_code == 302:
        send_alert_email("Instagram cookies expired.")
        return {"status": "expired"}

    return {"status": "ok", "status_code": response.status_code, "body": response.text}


# Allow local testing by running:
#   LOCAL=1 python3 lambda_function.py
if __name__ == "__main__" and LOCAL:
    event = {}
    res = lambda_handler(event, None)

    if res["status"] == "ok":
        # try to parse JSON
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
    # event = {}
    # print(lambda_handler(event, None))
