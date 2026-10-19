"""Publish a single numbered YouTube Automation promo on Instagram.

Uses the existing IG_ACCESS_TOKEN secret (Instagram Login for professional accounts).
Requires the public GitHub raw promo JPEG URL, shared via PUBLIC_IMAGE_URL.
"""
import os
import time
from pathlib import Path
import requests

API_VERSION = os.getenv("IG_API_VERSION", "v26.0")
API = f"https://graph.instagram.com/{API_VERSION}"
TOKEN = os.getenv("IG_ACCESS_TOKEN", "").strip()
IMAGE_URL = os.getenv("PUBLIC_IMAGE_URL", "").strip()


def api(method, path, **kwargs):
    response = requests.request(
        method,
        f"{API}/{path.lstrip('/')}",
        headers={"Authorization": f"Bearer {TOKEN}"},
        timeout=40,
        **kwargs,
    )
    try:
        data = response.json()
    except ValueError:
        raise RuntimeError(f"Instagram returned HTTP {response.status_code}")
    if not response.ok or data.get("error"):
        info = data.get("error") or {}
        raise RuntimeError(
            f"Instagram HTTP {response.status_code}: "
            f"{info.get('message', 'Unknown API error')}"
        )
    return data


def main():
    if not TOKEN:
        raise RuntimeError("IG_ACCESS_TOKEN missing in GitHub Actions secrets")
    if not IMAGE_URL.startswith("https://raw.githubusercontent.com/"):
        raise RuntimeError("PUBLIC_IMAGE_URL must be a public raw.githubusercontent.com URL")
    caption_path = Path("output/caption.txt")
    if not caption_path.exists():
        raise RuntimeError("Missing output/caption.txt")
    caption = caption_path.read_text(encoding="utf-8").strip()[:2200]

    # Wait for GitHub raw CDN to make committed JPEG available.
    for attempt in range(20):
        try:
            response = requests.get(IMAGE_URL, timeout=20)
            if response.ok and response.content[:3] == b"\xff\xd8\xff":
                break
        except requests.RequestException:
            pass
        if attempt == 19:
            raise RuntimeError("Hosted promotional JPEG is not publicly accessible")
        time.sleep(6)

    user = api("GET", "me", params={"fields": "id,username"})
    uid = str(user["id"])
    print("Publishing for @" + user.get("username", "unknown"))

    # Fail closed if Instagram's quota status cannot be read.
    quota = api("GET", f"{uid}/content_publishing_limit", params={"fields": "quota_usage,config"})
    if isinstance(quota.get("data"), list):
        quota = quota["data"][0]
    used = int(quota["quota_usage"])
    total = int(quota["config"]["quota_total"])
    if used >= min(total, 50):
        raise RuntimeError(f"Posting quota reached: {used}/{total}")

    container = api("POST", f"{uid}/media", data={"image_url": IMAGE_URL, "caption": caption})
    cid = str(container["id"])
    for attempt in range(30):
        status = api("GET", cid, params={"fields": "status_code"}).get("status_code")
        if status == "FINISHED":
            break
        if status in ("ERROR", "EXPIRED"):
            raise RuntimeError(f"Instagram container failed: {status}")
        time.sleep(10)
    else:
        raise RuntimeError("Media processing timed out")

    published = api("POST", f"{uid}/media_publish", data={"creation_id": cid})
    pid = str(published["id"])
    print("SUCCESS: promotional image published, Instagram Media ID:", pid)
    try:
        link = api("GET", pid, params={"fields": "permalink"}).get("permalink")
        if link:
            print("Published URL:", link)
    except (requests.RequestException, RuntimeError):
        pass

if __name__ == "__main__":
    main()
