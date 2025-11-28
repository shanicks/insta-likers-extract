from flask import Flask, render_template, redirect, request
import json
import requests
import os
from datetime import datetime
from profile_scraper import lambda_handler
from lambda_function import lambda_handler

app = Flask(__name__)

# -------------------------------
# Helpers
# -------------------------------


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except:
        return default


def save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


# -------------------------------
# Load persistent state
# -------------------------------

pending = load_json("user_list.json", [])  # queue of users to swipe
swipe_data = load_json("swipe_data.json", {})  # username -> left/right
state = load_json("state.json", {"last": None})  # for undo
daily = load_json("daily_swipes.json", {"date": "", "count": 0})


# -------------------------------
# Daily swipe limit logic
# -------------------------------

SWIPE_LIMIT = 100


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


# -------------------------------
# Main screen
# -------------------------------


@app.route("/")
def home():
    return redirect("/profile")


@app.route("/import", methods=["POST"])
def import_reel():
    data = request.json
    reel_url = data.get("url")

    if not reel_url:
        return {"status": "error", "error": "url missing"}

    # Extract shortcode from the URL
    # Example: https://www.instagram.com/reel/Cx9LmPpL1xy/
    try:
        import re

        m = re.search(r"(?:reel|p)/([A-Za-z0-9_-]+)", url)
        if not m:
            print("regex failed!")
            return {"error": "Invalid reel URL"}, 400

        shortcode = m.group(1)

        print(f"Extracted shortcode: {shortcode}")
        # shortcode = reel_url.rstrip("/").split("/")[-1]
    except:
        return {"status": "error", "error": "bad reel url"}

    # Call your scraper
    print("Importing reel:", reel_url, shortcode)

    # Modify your scraper to accept shortcode as media_id if needed
    res = lambda_handler({"media_id": shortcode}, None)

    return res


@app.route("/profile")
def show_profile():
    check_daily_reset()

    if not pending:
        return "No profiles left! Share a reel to load more."

    user = pending[0]  # next in queue

    event = {
        "username": user["username"],
        "user_id": user["user_id"],
    }

    res = lambda_handler(event, None)
    if res["status"] != "ok":
        return f"Error fetching profile: {res.get('error')}"

    user_data = res["body"]

    # Download profile picture
    url = (
        user_data.get("hd_profile_pic_url_info", {})
        .get("url", "")
        .replace("\\u0026", "&")
        .replace("&amp", "&")
        .strip('"')
        .strip()
    )

    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        print("Failed to fetch image")
        return "Image fetch error"

    filename = f"{user['user_id']}.jpg"
    static_path = os.path.join("static", filename)
    with open(static_path, "wb") as f:
        f.write(r.content)

    followers = user_data.get("follower_count", 0)
    following = user_data.get("following_count", 0)

    # Apply your criteria
    if followers >= 1000 or (followers - following) > 100:
        # Skip silently
        pending.pop(0)
        save_json("user_list.json", pending)
        return redirect("/profile")

    profile_data = {
        "username": user_data.get("username", ""),
        "full_name": user_data.get("full_name", ""),
        "biography": user_data.get("biography", ""),
        "edge_owner_to_timeline_media": {"count": user_data.get("media_count", 0)},
        "edge_followed_by": {"count": followers},
        "edge_follow": {"count": following},
        "profile_pic_filename": filename,
        "remaining": len(pending),
        "limit_left": SWIPE_LIMIT - daily["count"],
    }

    return render_template(
        "profile2.html", profile=profile_data, index=0, total=len(pending)
    )


# -------------------------------
# Swipe actions
# -------------------------------


@app.route("/swipe/<direction>")
def swipe(direction):
    if not pending:
        return redirect("/profile")

    check_daily_reset()

    if not can_swipe():
        return "Daily swipe limit reached (100). Come back tomorrow."

    # Pop the front of the queue
    user = pending.pop(0)
    save_json("user_list.json", pending)

    # Save swipe result
    swipe_data[user["username"]] = direction
    save_json("swipe_data.json", swipe_data)

    # Save last action for undo
    state["last"] = {
        "username": user["username"],
        "user_id": user["user_id"],
        "direction": direction,
    }
    save_json("state.json", state)

    # Increment daily count
    increment_swipe()

    return redirect("/profile")


# -------------------------------
# Undo swipe
# -------------------------------


@app.route("/undo")
def undo():
    if not state["last"]:
        return redirect("/profile")

    last = state["last"]
    username = last["username"]

    # Remove swipe entry
    if username in swipe_data:
        del swipe_data[username]
        save_json("swipe_data.json", swipe_data)

    # Reinsert to front
    pending.insert(0, {"username": username, "user_id": last["user_id"]})
    save_json("user_list.json", pending)

    # Fix daily counter
    decrement_swipe()

    # Clear undo state
    state["last"] = None
    save_json("state.json", state)

    return redirect("/profile")


# -------------------------------
# Start
# -------------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
