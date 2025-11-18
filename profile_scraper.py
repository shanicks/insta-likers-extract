import json
import os
import requests
from lambda_function import get_instagram_cookies, send_alert_email

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

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.5",
        # "Accept-Encoding": "gzip, deflate, br, zstd",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-FB-Friendly-Name": "PolarisProfilePageContentQuery",
        "X-BLOKS-VERSION-ID": "e931ff03adc522742d788ba659da2ded4fb760f51c8576b5cd93cdaf3987e4b0",
        "X-CSRFToken": cookies["csrftoken"],
        "X-IG-App-ID": "936619743392459",
        "X-Root-Field-Name": "fetch__XDTUserDict",
        "X-FB-LSD": cookies.get("lsd", "vum9kzmW-Yud3Iuagl8mmo"),
        "X-ASBD-ID": "359341",
        "Origin": "https://www.instagram.com",
        "Alt-Used": "www.instagram.com",
        "Connection": "keep-alive",
        "Referer": f"https://www.instagram.com/{username}/",
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
        "TE": "trailers",
        "Cookie": (
            f'csrftoken={cookies["csrftoken"]}; '
            f'sessionid={cookies["sessionid"]}; '
            f'ds_user_id={cookies["ds_user_id"]}'
        ),
    }

    # Build POST payload
    payload = {
        "fb_api_caller_class": "RelayModern",
        "fb_api_req_friendly_name": "PolarisProfilePageContentQuery",
        "variables": json.dumps(
            {
                "enable_integrity_filters": True,
                "id": user_id,
                "render_surface": "PROFILE",
                "__relay_internal__pv__PolarisProjectCannesEnabledrelayprovider": True,
                "__relay_internal__pv__PolarisProjectCannesLoggedInEnabledrelayprovider": True,
                "__relay_internal__pv__PolarisCannesGuardianExperienceEnabledrelayprovider": True,
                "__relay_internal__pv__PolarisCASB976ProfileEnabledrelayprovider": False,
                "__relay_internal__pv__PolarisRepostsConsumptionEnabledrelayprovider": False,
            }
        ),
        "doc_id": "25585291164389315",
    }

    # IMPORTANT: do not follow redirects
    response = requests.post(url, headers=headers, data=payload, allow_redirects=False)

    if response.status_code == 302:
        send_alert_email("Instagram cookies expired.", cookies)
        return {"status": "expired"}
    parsed = json.loads(response.text)
    user = parsed["data"]["user"]
    return {"status": "ok", "status_code": response.status_code, "body": user}


if __name__ == "__main__" and LOCAL:

    res = lambda_handler(
        {"username": "akankshayadav000001", "user_id": "53563587329"}, None
    )

    # print(
    #     "image_url:",
    #     user["hd_profile_pic_url_info"]["url"],
    #     "Name:",
    #     user["full_name"],
    #     "Bio:",
    #     user["biography"],
    #     "Posts:",
    #     user["media_count"],
    #     "Followers:",
    #     user["follower_count"],
    #     "Following:",
    #     user["following_count"],
    # )
