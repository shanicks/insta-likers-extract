import json
import os
import requests
from lambda_function import get_instagram_cookies, send_alert_email, get_headers

LOCAL = os.environ.get("LOCAL", "0") == "1"


def lambda_handler(event, context):

    cookies = get_instagram_cookies()

    username = event.get("username")
    if not username:
        return {"status": "error", "error": "username missing"}

    # You MUST supply this id per username — IG needs numeric id
    # Expect the frontend to resolve this ID earlier
    user_id = event.get("user_id")
    if not user_id:
        return {"status": "error", "error": "user_id missing"}

    url = "https://www.instagram.com/graphql/query"

    headers = get_headers("profile_query_headers")
    headers["X-CSRFToken"] = cookies["csrftoken"]
    headers["X-FB-LSD"] = cookies.get("lsd", "")
    headers["Cookie"] = (
        f'csrftoken={cookies["csrftoken"]}; sessionid={cookies["sessionid"]}; ds_user_id={cookies["ds_user_id"]}'
    )
    headers["Referer"] = f"https://www.instagram.com/{username}/"

    # Build POST payload
    payload = get_headers("profile_query_payload")
    payload["variables"]["id"] = user_id

    # Convert 'variables' dict to string
    payload["variables"] = json.dumps(payload["variables"])
    # IMPORTANT: do not follow redirects
    response = requests.post(url, headers=headers, data=payload, allow_redirects=False)

    if response.status_code == 302:
        send_alert_email("Instagram cookies expired.", cookies)
        return {"status": "expired"}
    parsed = json.loads(response.text)
    user = parsed["data"]["user"]
    return {"status": "ok", "status_code": response.status_code, "body": user}


if __name__ == "__main__" and LOCAL:
    res = lambda_handler({"username": "username", "user_id": "id"}, None)
