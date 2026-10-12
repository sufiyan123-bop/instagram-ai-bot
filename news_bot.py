import json
import random
import hashlib
import xml.etree.ElementTree as ET

from pathlib import Path
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests


# FACTZAI NEWS BOT
# Fetch latest news from the past 24 hours

NEWS_FILE = Path("latest_news.json")
HISTORY_FILE = Path("posted_news.json")

SEARCHES = [
    "India breaking news",
    "World breaking news",
    "Politics news",
    "Technology AI news",
    "Science space news",
    "Business economy news",
    "Sports news",
    "Bollywood Hollywood news",
    "Entertainment celebrity news",
    "Health medical news",
    "Education news",
    "Crime cybersecurity news",
    "Environment climate news",
    "Adult entertainment industry business news",
]


def get_news_id(title):
    clean = title.strip().lower()
    return hashlib.sha256(
        clean.encode("utf-8")
    ).hexdigest()


def load_history():
    if not HISTORY_FILE.exists():
        return set()

    try:
        data = json.loads(
            HISTORY_FILE.read_text(encoding="utf-8")
        )
        return set(data)
    except (ValueError, OSError):
        return set()


def fetch_news(query):
    url = "https://news.google.com/rss/search"

    params = {
        "q": f"{query} when:1d",
        "hl": "en-IN",
        "gl": "IN",
        "ceid": "IN:en",
    }

    response = requests.get(
        url,
        params=params,
        timeout=25,
        headers={
            "User-Agent": "Mozilla/5.0 FACTZAI-NewsBot/1.0"
        },
    )

    response.raise_for_status()

    root = ET.fromstring(response.content)

    results = []

    cutoff = datetime.now(timezone.utc) - timedelta(
        hours=24
    )

    for item in root.findall(".//item"):
        title = item.findtext("title", "").strip()
        link = item.findtext("link", "").strip()
        pub_date = item.findtext("pubDate", "").strip()

        if not title or not link or not pub_date:
            continue

        try:
            published = parsedate_to_datetime(pub_date)

            if published.tzinfo is None:
                published = published.replace(
                    tzinfo=timezone.utc
                )

            if published < cutoff:
                continue

            if published > datetime.now(timezone.utc):
                continue

        except (ValueError, TypeError):
            continue

        news_id = get_news_id(title)

        results.append({
            "id": news_id,
            "title": title,
            "url": link,
            "published": published.isoformat(),
            "category": query,
        })

    return results


def main():
    history = load_history()
    available = []
    seen = set()

    for query in SEARCHES:
        try:
            news_list = fetch_news(query)

            for news in news_list:
                news_id = news["id"]

                if news_id in history:
                    continue

                if news_id in seen:
                    continue

                seen.add(news_id)
                available.append(news)

        except Exception as error:
            print(
                "News fetch failed:",
                query,
                type(error).__name__,
            )

    if not available:
        print("No fresh news available.")
        return

    random.shuffle(available)

    selected = available[0]

    NEWS_FILE.write_text(
        json.dumps(
            selected,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("FACTZAI NEWS SELECTED")
    print("Title:", selected["title"])
    print("Published:", selected["published"])
    print("Category:", selected["category"])
    print("Source:", selected["url"])

    print("News saved to latest_news.json")


if __name__ == "__main__":
    main()
