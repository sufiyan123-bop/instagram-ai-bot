import json
from pathlib import Path

NEWS_FILE = Path("latest_news.json")
HISTORY_FILE = Path("posted_news.json")


def main():
    if not NEWS_FILE.exists():
        raise RuntimeError("latest_news.json missing")

    news = json.loads(
        NEWS_FILE.read_text(encoding="utf-8")
    )

    news_id = news.get("id")

    if not news_id:
        raise RuntimeError("News ID missing")

    if HISTORY_FILE.exists():
        history = json.loads(
            HISTORY_FILE.read_text(encoding="utf-8")
        )
    else:
        history = []

    if isinstance(history, dict):
        history = list(history.keys())

    if news_id not in history:
        history.append(news_id)

    HISTORY_FILE.write_text(
        json.dumps(
            history,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("Saved published news ID:", news_id)


if __name__ == "__main__":
    main()
