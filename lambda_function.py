import json
import os
import boto3
import requests
from utils import *

LOCAL = os.environ.get("LOCAL", "0") == "1"


def likers_extract(event, context):
    cookies = get_instagram_cookies()

    url = f"https://www.instagram.com/api/v1/media/{event['media_id']}/likers/"

    headers = get_headers("media_likers_headers")
    headers["X-CSRFToken"] = cookies["csrftoken"]
    headers["X-IG-WWW-Claim"] = cookies.get("claim", "")
    headers["Cookie"] = (
        f'csrftoken={cookies["csrftoken"]}; sessionid={cookies["sessionid"]}; ds_user_id={cookies["ds_user_id"]}'
    )

    # IMPORTANT: don't auto-follow redirects
    response = requests.get(url, headers=headers, allow_redirects=False)

    if response.status_code == 302:
        send_alert_email("Instagram cookies expired.")
        return {"status": "expired"}

    return {"status": "ok", "status_code": response.status_code, "body": response.text}


# Allow local testing by running:
#   LOCAL=1 python3 lambda_function.py
if __name__ == "__main__" and LOCAL:
    media_id = shortcode_to_media_id("DNC0tV_JfLT")
    event = {"media_id": media_id}
    res = likers_extract(event, None)

    if res["status"] == "ok":
        # try to parse JSON
        save_user_list(res)
    # print(lambda_handler(event, None))
