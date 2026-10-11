"""Fail-closed Instagram API quota guard; no extra IG_USER_ID secret needed.

Output allowed=true/false to GitHub Actions. It does not publish anything.
"""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import requests


API_VERSION = os.getenv("IG_API_VERSION", "v26.0")
TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
MAX_POSTS_PER_24_HOURS = 50


def set_allowed(allowed: bool, message: str) -> None:
    print(f"Quota guard: {'ALLOW' if allowed else 'SKIP'} — {message}")
    output_path = os.environ.get("GITHUB_OUTPUT")
    if output_path:
        with open(output_path, "a", encoding="utf-8") as output:
            output.write(f"allowed={'true' if allowed else 'false'}\n")


def get_json(path: str, params: dict[str, str]) -> dict:
    response = requests.get(
        f"https://graph.instagram.com/{API_VERSION}/{path}",
        headers={"Authorization": f"Bearer {TOKEN}"},
        params=params,
        timeout=30,
    )
    response.raise_for_status()
    return response.json()


def main() -> None:
    if os.environ.get("CHECK_SCHEDULE_HOURS") == "true":
        # GitHub Actions cron isn't guaranteed to start at the requested minute.
        now = datetime.now(ZoneInfo("Asia/Kolkata"))
        if not (7 <= now.hour < 22):
            set_allowed(False, f"Outside 07:00–21:59 IST (now {now:%H:%M})")
            return

    if not TOKEN:
        set_allowed(False, "Instagram access-token secret missing")
        return
    if not (API_VERSION.startswith("v") and all(part.isdigit() for part in API_VERSION[1:].split("."))):
        set_allowed(False, "Invalid IG_API_VERSION")
        return

    try:
        account = get_json("me", {"fields": "id"})
        user_id = str(account["id"])
        if not user_id.isdecimal():
            raise ValueError("Instagram user ID isn't numeric")
        limit = get_json(f"{user_id}/content_publishing_limit", {"fields": "quota_usage,config"})
        if isinstance(limit.get("data"), list):
            records = limit["data"]
            if not records:
                raise ValueError("No quota records")
            limit = records[0]
        used = int(limit["quota_usage"])
        config = limit["config"]
        total = int(config["quota_total"])
        duration = int(config["quota_duration"])
        if used < 0 or total < 1 or duration != 86400:
            raise ValueError("Unexpected API quota fields")
    except (requests.RequestException, ValueError, KeyError, TypeError, IndexError) as exc:
        # Never log raw API response/headers; they could reveal sensitive details.
        set_allowed(False, f"Could not verify quota ({type(exc).__name__})")
        return

    cap = min(total, MAX_POSTS_PER_24_HOURS)
    if used >= cap:
        set_allowed(False, f"Rolling 24-hour quota already {used}/{cap}")
    else:
        set_allowed(True, f"Current rolling quota {used}/{cap} (Meta account limit {total})")


if __name__ == "__main__":
    main()
