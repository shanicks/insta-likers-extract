import json
import os
import requests
from utils import get_instagram_cookies, send_alert_email, get_headers

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


def send_follow(target_user_id):
    cookies = get_instagram_cookies()

    url = "https://www.instagram.com/graphql/query/"

    # load base template
    headers = get_headers("send_follow_headers")

    # Inject dynamic cookies
    headers["Cookie"] = (
        f'csrftoken={cookies["csrftoken"]}; '
        f'sessionid={cookies["sessionid"]}; '
        f'ds_user_id={cookies["ds_user_id"]}'
    )
    headers["X-CSRFToken"] = cookies["csrftoken"]
    headers["X-FB-LSD"] = cookies["lsd"]

    payload = get_headers("send_follow_payload")
    payload["lsd"] = cookies["lsd"]
    payload["variables"]["target_user_id"] = str(target_user_id)
    payload["variables"] = json.dumps(payload["variables"])
    # payload = {
    #     "av": cookies["actor_id"],  # from your logged-in cookies
    #     "__d": "www",
    #     "fb_api_caller_class": "RelayModern",
    #     "fb_api_req_friendly_name": "usePolarisFollowMutation",
    #     "server_timestamps": "true",
    #     "variables": json.dumps(
    #         {
    #             "target_user_id": str(target_user_id),
    #             "container_module": "profile",
    #             "nav_chain": "PolarisProfilePostsTabRoot:profilePage:1:via_cold_start",
    #         }
    #     ),
    #     "doc_id": "9740159112729312",
    # }

    r = requests.post(url, headers=headers, data=payload)
    return r.json()


if __name__ == "__main__" and LOCAL:
    res = send_follow("74544447490")
    print(res)
