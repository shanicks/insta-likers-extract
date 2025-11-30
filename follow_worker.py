import time
import random
import threading
from utils import save_json, load_json
from profile_scraper import send_follow


def follow_worker():
    print("FOLLOW WORKER STARTED")

    while True:
        try:
            data = load_json("swipe_data.json", [])  # always reload the newest file
            changed = False
            now = time.time()

            for entry in data:
                # print(entry)
                # Only process right-swiped users not followed yet
                if entry.get("direction") != "right":
                    continue
                if entry.get("followed"):
                    continue

                # Ensure follow_at is set once (15–35 seconds after timestamp)
                if "follow_at" not in entry:
                    timestamp = entry.get("timestamp", now)
                    entry["follow_at"] = timestamp + 15 + (random.random() * 20)
                    changed = True
                    continue

                # Not time yet → skip
                if now < entry["follow_at"]:
                    continue

                # Time to follow
                user_id = entry["user_id"]
                username = entry["username"]
                print(f"[FOLLOW] Following {username} ({user_id}) ...")

                res = send_follow(user_id)
                print("FOLLOW RESULT:", res)

                entry["followed"] = True
                changed = True

                # Wait between requests for safety
                time.sleep(15)

            # Save only if anything changed
            if changed:
                save_json("swipe_data.json", data)

        except Exception as e:
            print("Worker error:", e)

        # Main loop throttle
        time.sleep(3)
