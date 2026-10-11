"""One-test, two-image carousel publisher for Instagram Login (no Facebook Page).

The images are publicly hosted in this GitHub repository's posts/ folder,
using raw.githubusercontent.com. Run only for a public repository.
Access token is read from Actions secret IG_ACCESS_TOKEN and never printed.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

VERSION = os.getenv("IG_API_VERSION", "v26.0")
API = f"https://graph.instagram.com/{VERSION}"
TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
BASE = os.getenv("PUBLIC_BASE", "").rstrip("/")
CAPTION_FILE = Path("output/caption.txt")


def call(method: str, path: str, **kwargs) -> dict:
    response = requests.request(
        method,
        f"{API}/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=40,
        **kwargs,
    )
    try:
        payload = response.json()
    except ValueError:
        raise RuntimeError(f"Instagram API returned HTTP {response.status_code} (not JSON)")
    if not response.ok or payload.get("error"):
        detail = payload.get("error", {})
        msg = detail.get("message", str(detail)) if isinstance(detail, dict) else str(detail)
        code = detail.get("code", "?") if isinstance(detail, dict) else "?"
        raise RuntimeError(f"Instagram API error {response.status_code} (code {code}): {msg}")
    return payload


def wait_public_image(url: str) -> None:
    # GitHub raw links can take a few seconds after commit to become available.
    for attempt in range(1, 19):
        try:
            res = requests.get(url, timeout=20)
            if res.ok and res.content[:3] == b"\xff\xd8\xff":
                print(f"Public JPEG is ready ({attempt}/18)")
                return
        except requests.RequestException:
            pass
        time.sleep(7)
    raise RuntimeError("Image URL is not publicly reachable as a JPEG. Confirm repo is PUBLIC.")


def wait_container(cid: str) -> None:
    for attempt in range(20):
        state = call("GET", cid, params={"fields": "status_code"}).get("status_code")
        if state == "FINISHED":
            return
        if state in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram couldn't process a carousel container: {state}")
        print(f"Waiting for Instagram image processing ({state or 'pending'})...")
        time.sleep(12)
    raise RuntimeError("Instagram processing timed out. Review Actions logs before retrying.")


def main():
    if not TOKEN:
        raise RuntimeError("Missing IG_ACCESS_TOKEN. Add it to GitHub repository Actions Secrets.")
    if not BASE.startswith("https://raw.githubusercontent.com/"):
        raise RuntimeError("PUBLIC_BASE must be the public image URL on raw.githubusercontent.com")
    if not CAPTION_FILE.exists():
        raise RuntimeError("Caption missing. Step 4 bot.py must generate output/caption.txt first.")

    image_urls = [f"{BASE}/slide_1.jpg", f"{BASE}/slide_2.jpg"]
    for image_url in image_urls:
        wait_public_image(image_url)

    info = call("GET", "me", params={"fields": "id,username"})
    user_id = str(info["id"])
    print("Instagram connected as @" + info.get("username", "unknown"))

    # Stop rather than exceed the account's current published-post quota.
    quota = call("GET", f"{user_id}/content_publishing_limit", params={"fields": "quota_usage,config"})
    if isinstance(quota.get("data"), list) and quota["data"]:
        quota = quota["data"][0]
    usage = quota.get("quota_usage")
    total = (quota.get("config") or {}).get("quota_total")
    if isinstance(usage, int) and isinstance(total, int):
        print(f"Publishing quota: {usage}/{total} in the last 24 hours")
        if usage >= total:
            raise RuntimeError("Instagram 24-hour publishing quota reached; try again later.")

    children = []
    for number, url in enumerate(image_urls, 1):
        item = call("POST", f"{user_id}/media", data={"image_url": url, "is_carousel_item": "true"})
        cid = str(item["id"])
        wait_container(cid)
        children.append(cid)
        print(f"Slide {number}/2 ready")

    caption = CAPTION_FILE.read_text(encoding="utf-8").strip()[:2200]
    parent = call("POST", f"{user_id}/media", data={
        "media_type": "CAROUSEL",
        "children": ",".join(children),
        "caption": caption,
    })
    wait_container(str(parent["id"]))

    published = call("POST", f"{user_id}/media_publish", data={"creation_id": str(parent["id"])})
    post_id = str(published["id"])
    print("SUCCESS: Published one Instagram carousel with two slides.")
    print("Instagram Media ID:", post_id)
    try:
        permalink = call("GET", post_id, params={"fields": "permalink"}).get("permalink")
        if permalink:
            print("View post:", permalink)
    except (requests.RequestException, RuntimeError):
        pass


if __name__ == "__main__":
    main()
