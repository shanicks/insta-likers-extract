from flask import Flask, render_template, redirect
import json
import html
import requests
import os
from profile_scraper import lambda_handler

app = Flask(__name__)

# Load user list and swipe data
with open("user_list.json") as f:
    users = json.load(f)

try:
    with open("swipe_data.json") as f:
        swipe_data = json.load(f)
except FileNotFoundError:
    swipe_data = {}


@app.route("/profile/<int:index>")
def show_profile(index):
    if index >= len(users):
        return "No more profiles!"

    username = users[index]["username"]

    event = {
        "username": users[index]["username"],
        "user_id": users[index]["user_id"],
    }  # numeric IG ID
    res = lambda_handler(event, None)
    # print("prooooooooo:", profile)
    if res["status"] != "ok":
        return f"Error fetching profile: {res.get('error')}"

    user = res["body"]  # the "user" dict from GraphQL
    url = (
        user.get("hd_profile_pic_url_info", {})
        .get("url", "")
        .replace("\\u0026", "&")
        .replace("&amp", "&")
        .strip('"')
        .strip()
    )
    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("Failed to fetch image")
        return None
    filename = users[index]["user_id"] + ".jpg"
    # Save to static folder
    static_path = os.path.join("static", filename)
    with open(static_path, "wb") as f:
        f.write(r.content)

    followers = user.get("follower_count", 0)
    following = user.get("following_count", 0)

    if followers >= 1000 or (followers - following) > 100:
        print(f"Skipping {username} due to follower/following criteria")
        return redirect(f"/profile/{index + 1}")

    profile_data = {
        "edge_owner_to_timeline_media": {"count": user.get("media_count", 0)},
        "edge_followed_by": {"count": followers},
        "edge_follow": {"count": following},
        "full_name": user.get("full_name", ""),
        "biography": user.get("biography", ""),
        "profile_pic_filename": filename,
        "username": user.get("username", ""),
    }
    # profile_data = {
    #     "edge_owner_to_timeline_media": {"count": user.get("media_count", 0)},
    #     "edge_followed_by": {"count": user.get("follower_count", 0)},
    #     "edge_follow": {"count": user.get("following_count", 0)},
    #     "full_name": user.get("full_name", ""),
    #     "biography": user.get("biography", ""),
    #     # "profile_pic_url": html.unescape(
    #     #     user.get("hd_profile_pic_url_info", {}).get("url", "")
    #     # ),
    #     "profile_pic_filename": filename,
    #     "username": user.get("username", ""),
    # }

    return render_template(
        "profile.html", profile=profile_data, index=index, total=len(users)
    )


@app.route("/swipe/<int:index>/<direction>")
def swipe(index, direction):
    username = users[index]["username"]
    swipe_data[username] = direction
    with open("swipe_data.json", "w") as f:
        json.dump(swipe_data, f, indent=2)

    return redirect(f"/profile/{index + 1}")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
