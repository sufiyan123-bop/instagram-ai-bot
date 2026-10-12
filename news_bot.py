import json
import random
import hashlib
import re
import html
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote

import requests


# ==========================================
# FACTZAI NEWS COLLECTOR
# ==========================================

NEWS_FILE = Path("latest_news.json")
HISTORY_FILE = Path("posted_news.json")

MAX_NEWS_AGE_HOURS = 24

CATEGORIES = {
    "India": "India latest news",
    "World": "world international news",
    "Politics": "politics government elections news",
    "Technology": "technology artificial intelligence news",
    "Science": "science research discoveries news",
    "Space": "space NASA ISRO news",
    "Business": "business economy markets news",
    "Sports": "sports cricket football news",
    "Entertainment": "Bollywood Hollywood entertainment news",
    "Health": "health medical research news",
    "Education": "education students exams news",
    "Cybersecurity": "cybersecurity data breach news",
    "Environment": "environment climate news",
    "Adult Industry": "adult entertainment industry business regulation news",
}


def normalize_title(title):
    title = html.unescape(title)
    title = re.sub(r"\s+", " ", title)
    return title.strip().lower()


def make_news_id(title):
    normalized = normalize_title(title)

    return hashlib.sha256(
        normalized.encode("utf-8")
    ).hexdigest()


def load_history():
    if not HISTORY_FILE.exists():
        return set()

    try:
        data = json.loads(
            HISTORY_FILE.read_text(encoding="utf-8")
        )

        if isinstance(data, list):
            return set(str(item) for item in data)

        if isinstance(data, dict):
            return set(data.keys())

    except (OSError, ValueError):
        pass

    return set()


def parse_publication_date(date_text):
    try:
        published = parsedate_to_datetime(date_text)

        if published.tzinfo is None:
            published = published.replace(
                tzinfo=timezone.utc
            )

        return published.astimezone(timezone.utc)

    except (ValueError, TypeError, IndexError):
        return None


def fetch_category_news(category, search_query):
    encoded_query = quote(
        f"{search_query} when:1d"
    )

    url = (
        "https://news.google.com/rss/search"
        f"?q={encoded_query}"
        "&hl=en-IN&gl=IN&ceid=IN:en"
    )

    response = requests.get(
        url,
        timeout=30,
        headers={
            "User-Agent": "Mozilla/5.0"
        },
    )

    response.raise_for_status()

    root = ET.fromstring(response.content)

    now = datetime.now(timezone.utc)

    cutoff = now - timedelta(
        hours=MAX_NEWS_AGE_HOURS
    )

    results = []

    for item in root.findall(".//channel/item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        date_text = (
            item.findtext("pubDate") or ""
        ).strip()

        source_element = item.find("source")

        source_name = ""

        if source_element is not None:
            source_name = (
                source_element.text or ""
            ).strip()

        if not title or not link or not date_text:
            continue

        published = parse_publication_date(
            date_text
        )

        if published is None:
            continue

        if published < cutoff or published > now:
            continue

        clean_title = html.unescape(title)

        if source_name:
            suffix = f" - {source_name}"

            if clean_title.endswith(suffix):
                clean_title = clean_title[
                    :-len(suffix)
                ].strip()

        if len(clean_title) < 20:
            continue

        news_id = make_news_id(clean_title)

        results.append({
            "id": news_id,
            "title": clean_title,
            "source": source_name or "Google News",
            "url": link,
            "published_utc": published.isoformat(),
            "category": category,
            "collected_utc": now.isoformat(),
        })

    return results


def collect_fresh_news():
    history = load_history()

    collected = []
    seen_ids = set()

    for category, query in CATEGORIES.items():
        print(f"Checking category: {category}")

        try:
            stories = fetch_category_news(
                category,
                query
            )

        except Exception as error:
            print(
                f"Failed {category}: "
                f"{type(error).__name__}: {error}"
            )
            continue

        for story in stories:
            news_id = story["id"]

            if news_id in history:
                continue

            if news_id in seen_ids:
                continue

            seen_ids.add(news_id)
            collected.append(story)

    return collected


def choose_news(stories):
    if not stories:
        return None

    # Prioritize newer stories without always
    # selecting the exact newest headline.

    stories.sort(
        key=lambda item: item["published_utc"],
        reverse=True,
    )

    top_stories = stories[:30]

    return random.choice(top_stories)


def main():
    print("=" * 45)
    print("FACTZAI - LATEST NEWS COLLECTOR")
    print("=" * 45)

    stories = collect_fresh_news()

    print(f"Fresh stories found: {len(stories)}")

    selected = choose_news(stories)

    if selected is None:
        # Prevent downstream steps from using
        # a stale result from a previous run.
        NEWS_FILE.unlink(missing_ok=True)

        print(
            "No suitable fresh news available."
        )
        raise SystemExit(1)

    NEWS_FILE.write_text(
        json.dumps(
            selected,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nSELECTED NEWS")
    print("Title:", selected["title"])
    print("Category:", selected["category"])
    print("Source:", selected["source"])
    print("Published:", selected["published_utc"])
    print("URL:", selected["url"])

    print("\nSaved: latest_news.json")


if __name__ == "__main__":
    main()
