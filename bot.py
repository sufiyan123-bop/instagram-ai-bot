
"""
FACTZAI - FREE REAL PHOTO NEWS CAROUSEL

Creates:
    output/slide_1.jpg
    output/slide_2.jpg
    output/caption.txt
    output/news_id.txt

Uses Gemini for news text only.
Uses Wikimedia Commons for real illustrative photos.
Does NOT use Gemini image generation.
"""

import html
import io
import json
import os
import re
import subprocess
import tempfile
import time

from datetime import datetime, timezone
from pathlib import Path

import requests
from google import genai
from google.genai import types
from PIL import Image, ImageDraw, ImageFont, ImageOps


# ---------------------------------
# CONFIG
# ---------------------------------

ROOT = Path(__file__).resolve().parent
NEWS_FILE = ROOT / "latest_news.json"
OUT = ROOT / "output"

SIZE = 1080

NAVY = (7, 13, 27)
YELLOW = (255, 211, 45)
WHITE = (250, 251, 253)
GREY = (186, 194, 207)

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()

TEXT_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
)

COMMONS_API = "https://commons.wikimedia.org/w/api.php"

HEADERS = {
    "User-Agent": (
        "FACTZAI-NewsBot/1.0 "
        "(Instagram: @fac.tzai)"
    )
}

CATEGORY_SEARCH = {
    "india": "India skyline city",
    "world": "world city skyline",
    "politics": "parliament building",
    "technology": "computer data center servers",
    "science": "research science laboratory",
    "space": "space observatory telescope",
    "business": "financial district skyscrapers",
    "sports": "sports stadium",
    "entertainment": "cinema film studio",
    "health": "hospital medical laboratory",
    "education": "university library",
    "cybersecurity": "server racks",
    "environment": "forest landscape",
    "adult industry": "film production studio",
}


# ---------------------------------
# TEXT HELPERS
# ---------------------------------

def clean(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def metadata_text(value):
    value = re.sub(
        r"<[^>]*>",
        " ",
        str(value or "")
    )

    return clean(html.unescape(value))


# ---------------------------------
# HINDI + ENGLISH FONT
# ---------------------------------

def get_font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/noto/"
        "NotoSansDevanagari-Bold.ttf",

        "/usr/share/fonts/truetype/noto/"
        "NotoSansDevanagari-Regular.ttf",
    ]

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(
                path,
                size
            )

    try:
        path = subprocess.check_output(
            [
                "fc-match",
                "-f",
                "%{file}",
                "Noto Sans Devanagari"
            ],
            text=True,
            timeout=8
        ).strip()

        if (
            Path(path).exists()
            and "Devanagari" in path
        ):
            return ImageFont.truetype(
                path,
                size
            )

    except Exception:
        pass

    local = (
        Path(tempfile.gettempdir())
        / "factzai_devanagari.ttf"
    )

    if not local.exists():
        url = (
            "https://raw.githubusercontent.com/"
            "google/fonts/main/ofl/"
            "notosansdevanagari/"
            "NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
        )

        response = requests.get(
            url,
            timeout=45
        )

        response.raise_for_status()

        local.write_bytes(
            response.content
        )

    return ImageFont.truetype(
        str(local),
        size
    )


def wrap_text(draw, text, chosen_font, max_width):
    lines = []
    current = ""

    for word in clean(text).split():
        candidate = (
            current + " " + word
        ).strip()

        width = draw.textbbox(
            (0, 0),
            candidate,
            font=chosen_font
        )[2]

        if width <= max_width:
            current = candidate

        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def fit_text(
    draw,
    text,
    x,
    y,
    max_width,
    max_height,
    max_font=55,
    min_font=23,
    fill=WHITE,
):
    for size in range(
        max_font,
        min_font - 1,
        -2
    ):
        chosen = get_font(
            size,
            True
        )

        lines = wrap_text(
            draw,
            text,
            chosen,
            max_width
        )

        line_height = int(
            size * 1.48
        )

        fits_width = all(
            draw.textbbox(
                (0, 0),
                line,
                font=chosen
            )[2] <= max_width
            for line in lines
        )

        if (
            lines
            and fits_width
            and len(lines) * line_height <= max_height
        ):
            for line in lines:
                draw.text(
                    (x, y),
                    line,
                    font=chosen,
                    fill=fill
                )

                y += line_height

            return

    raise RuntimeError(
        "Text too long for slide: "
        + clean(text)[:100]
    )


# ---------------------------------
# LOAD NEWS
# ---------------------------------

def load_news():
    if not NEWS_FILE.exists():
        raise RuntimeError(
            "latest_news.json missing"
        )

    news = json.loads(
        NEWS_FILE.read_text(
            encoding="utf-8"
        )
    )

    required = (
        "id",
        "title",
        "source",
        "url",
        "category",
        "published_utc"
    )

    for key in required:
        if not clean(news.get(key)):
            raise RuntimeError(
                "News missing: " + key
            )

    published = datetime.fromisoformat(
        news["published_utc"].replace(
            "Z",
            "+00:00"
        )
    )

    if published.tzinfo is None:
        published = published.replace(
            tzinfo=timezone.utc
        )

    age = (
        datetime.now(timezone.utc)
        - published.astimezone(timezone.utc)
    ).total_seconds() / 3600

    if age < -0.1 or age > 24:
        raise RuntimeError(
            "Selected news is not from last 24 hours"
        )

    return news, published


# ---------------------------------
# AI NEWS TEXT
# ---------------------------------

def create_copy(client, news):
    prompt = f"""
You are FACTZAI, a premium Indian
Instagram news editor.

NEWS HEADLINE:
{news["title"]}

SOURCE:
{news["source"]}

CATEGORY:
{news["category"]}

You know ONLY the RSS headline.
You have NOT read the full article.

Create accurate, short news copy.

Use natural Hinglish:
Hindi Devanagari mixed with English.

Examples:
"AI Technology में आया नया Update"
"India में नई Policy पर चर्चा"
"Space Mission की बड़ी खबर"

Do not invent facts, numbers,
quotes, outcomes or extra details.

Preserve uncertainty.

Return JSON ONLY with these keys:

headline:
Maximum 88 characters.
Natural Hinglish.

point1:
Maximum 100 characters.
What the headline actually reports.

point2:
Maximum 100 characters.
Careful context.
If details are missing, tell readers
to check the original report.

caption:
Maximum 170 characters.
Natural Hinglish Instagram caption.

Do not use clickbait.
"""

    last_error = None

    for attempt in range(3):
        try:
            result = client.models.generate_content(
                model=TEXT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.3
                )
            )

            data = json.loads(
                result.text or "{}"
            )

            limits = {
                "headline": 88,
                "point1": 100,
                "point2": 100,
                "caption": 170
            }

            for key, limit in limits.items():
                value = clean(
                    data.get(key)
                )

                if (
                    not value
                    or len(value) > limit
                ):
                    raise ValueError(
                        "Invalid " + key
                    )

                data[key] = value

            # ---------------------------------
            # FIX: Hindi + English headline
            # ---------------------------------

            has_hindi = bool(
                re.search(
                    r"[\u0900-\u097f]",
                    data["headline"]
                )
            )

            has_english = bool(
                re.search(
                    r"[A-Za-z]",
                    data["headline"]
                )
            )

            if (
                not has_hindi
                and has_english
            ):
                data["headline"] = (
                    "आज की खबर: "
                    + data["headline"]
                )

            elif (
                has_hindi
                and not has_english
            ):
                data["headline"] = (
                    "News Update: "
                    + data["headline"]
                )

            elif (
                not has_hindi
                and not has_english
            ):
                raise ValueError(
                    "Headline has no readable text"
                )

            if len(data["headline"]) > 100:
                data["headline"] = (
                    data["headline"][:97].rstrip()
                    + "..."
                )

            return data

        except Exception as error:
            last_error = error

            print(
                "Text attempt failed:",
                attempt + 1,
                type(error).__name__,
                str(error)[:150]
            )

            if attempt < 2:
                time.sleep(3)

    raise RuntimeError(
        "News text generation failed: "
        + str(last_error)[:180]
    )


# ---------------------------------
# FREE WIKIMEDIA PHOTOS
# ---------------------------------

def search_commons(query):
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": query + " filetype:bitmap",
        "gsrnamespace": 6,
        "gsrlimit": 35,
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": 1600
    }

    response = requests.get(
        COMMONS_API,
        params=params,
        headers=HEADERS,
        timeout=35
    )

    response.raise_for_status()

    pages = (
        response.json()
        .get("query", {})
        .get("pages", {})
    )

    for page in pages.values():
        title = str(
            page.get("title") or ""
        )

        if not title.lower().endswith(
            (".jpg", ".jpeg", ".png")
        ):
            continue

        info = (
            page.get("imageinfo") or [{}]
        )[0]

        width = int(
            info.get("width") or 0
        )

        height = int(
            info.get("height") or 0
        )

        if width < 850 or height < 550:
            continue

        fields = (
            info.get("extmetadata") or {}
        )

        license_name = metadata_text(
            (
                fields.get("LicenseShortName")
                or {}
            ).get("value")
        )

        normalized = (
            license_name.lower()
            .replace(" ", "")
        )

        allowed = (
            normalized.startswith("ccby-")
            or normalized.startswith("ccby-sa-")
            or normalized in (
                "cc0",
                "publicdomain",
                "pd"
            )
        )

        if not allowed:
            continue

        photo_url = (
            info.get("thumburl")
            or info.get("url")
        )

        page_url = info.get(
            "descriptionurl"
        )

        if not photo_url or not page_url:
            continue

        author = metadata_text(
            (
                fields.get("Artist")
                or {}
            ).get("value")
        )[:180]

        yield {
            "url": photo_url,
            "page": page_url,
            "title": title,
            "license": license_name,
            "author": (
                author
                or "Wikimedia Commons contributor"
            )
        }


def get_photos(news):
    category = clean(
        news["category"]
    ).lower()

    search_term = CATEGORY_SEARCH.get(
        category,
        "city skyline architecture"
    )

    searches = [
        search_term,
        search_term.split()[0] + " photography",
        "modern city skyline"
    ]

    selected = []
    seen = set()

    for query in searches:
        try:
            candidates = search_commons(
                query
            )

            for item in candidates:
                if item["page"] in seen:
                    continue

                try:
                    response = requests.get(
                        item["url"],
                        headers=HEADERS,
                        timeout=40
                    )

                    response.raise_for_status()

                    image = Image.open(
                        io.BytesIO(
                            response.content
                        )
                    )

                    image.load()

                    if (
                        image.width < 800
                        or image.height < 500
                    ):
                        continue

                    image = image.convert(
                        "RGB"
                    )

                    selected.append(
                        (image, item)
                    )

                    seen.add(
                        item["page"]
                    )

                    print(
                        "Photo selected:",
                        item["title"],
                        item["license"]
                    )

                    if len(selected) == 2:
                        return selected

                except Exception as error:
                    print(
                        "Skipping photo:",
                        type(error).__name__,
                        str(error)[:100]
                    )

        except Exception as error:
            print(
                "Wikimedia search failed:",
                type(error).__name__,
                str(error)[:120]
            )

    raise RuntimeError(
        "Two suitable licensed photos "
        "were not available. "
        "Post skipped safely."
    )


# ---------------------------------
# PREMIUM FACTZAI DESIGN
# ---------------------------------

def base_slide(photo, slide_number):
    canvas = Image.new(
        "RGB",
        (SIZE, SIZE),
        NAVY
    )

    photo = ImageOps.fit(
        photo,
        (1080, 680),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )

    canvas.paste(
        photo,
        (0, 0)
    )

    draw = ImageDraw.Draw(
        canvas
    )

    # FACTZAI logo area
    draw.rounded_rectangle(
        (38, 36, 430, 123),
        radius=16,
        fill=NAVY,
        outline=YELLOW,
        width=3
    )

    draw.text(
        (63, 46),
        "FACTZAI",
        font=get_font(55, True),
        fill=YELLOW
    )

    # Slide number
    draw.rounded_rectangle(
        (750, 48, 1034, 108),
        radius=12,
        fill=NAVY
    )

    draw.text(
        (770, 60),
        f"NEWS / 0{slide_number}",
        font=get_font(29, True),
        fill=WHITE
    )

    # Real-photo disclosure
    draw.rounded_rectangle(
        (40, 609, 470, 660),
        radius=10,
        fill=NAVY
    )

    draw.text(
        (57, 619),
        "REAL PHOTO / COMMONS",
        font=get_font(24, True),
        fill=YELLOW
    )

    # Dark bottom panel
    draw.rectangle(
        (0, 680, 1080, 1080),
        fill=NAVY
    )

    draw.rectangle(
        (0, 680, 1080, 689),
        fill=YELLOW
    )

    # Footer
    draw.line(
        (48, 1025, 1032, 1025),
        fill=YELLOW,
        width=2
    )

    draw.text(
        (48, 1036),
        "@fac.tzai",
        font=get_font(24, True),
        fill=YELLOW
    )

    draw.text(
        (815, 1036),
        "FACTZAI NEWS",
        font=get_font(23, True),
        fill=GREY
    )

    return canvas, draw


def slide_one(news, copy, photo):
    canvas, draw = base_slide(
        photo,
        1
    )

    fit_text(
        draw,
        clean(news["category"]).upper(),
        48,
        710,
        980,
        48,
        max_font=30,
        min_font=22,
        fill=YELLOW
    )

    fit_text(
        draw,
        copy["headline"],
        48,
        765,
        980,
        225,
        max_font=61,
        min_font=29,
        fill=WHITE
    )

    return canvas


def slide_two(copy, photo):
    canvas, draw = base_slide(
        photo,
        2
    )

    fit_text(
        draw,
        "NEWS EXPLAINED",
        48,
        710,
        980,
        45,
        max_font=30,
        min_font=23,
        fill=YELLOW
    )

    fit_text(
        draw,
        "01  " + copy["point1"],
        48,
        770,
        980,
        100,
        max_font=36,
        min_font=22,
        fill=WHITE
    )

    fit_text(
        draw,
        "02  " + copy["point2"],
        48,
        890,
        980,
        105,
        max_font=36,
        min_font=22,
        fill=WHITE
    )

    return canvas


# ---------------------------------
# MAIN
# ---------------------------------

def main():
    if not API_KEY:
        raise RuntimeError(
            "GEMINI_API_KEY missing"
        )

    news, published = load_news()

    print(
        "FACTZAI headline:",
        news["title"]
    )

    client = genai.Client(
        api_key=API_KEY
    )

    # Generate news text only
    copy = create_copy(
        client,
        news
    )

    print(
        "News text generated successfully"
    )

    # Download free licensed photos
    print(
        "Finding free Wikimedia photographs..."
    )

    photos = get_photos(
        news
    )

    photo1, credit1 = photos[0]
    photo2, credit2 = photos[1]

    # Build carousel
    first = slide_one(
        news,
        copy,
        photo1
    )

    second = slide_two(
        copy,
        photo2
    )

    OUT.mkdir(
        parents=True,
        exist_ok=True
    )

    first.save(
        OUT / "slide_1.jpg",
        "JPEG",
        quality=94,
        subsampling=0
    )

    second.save(
        OUT / "slide_2.jpg",
        "JPEG",
        quality=94,
        subsampling=0
    )

    # Caption with photo credits
    caption = (
        copy["caption"]
        + "\n\n"
        + "📰 Source: "
        + clean(news["source"])
        + "\n"
        + "📅 "
        + published.strftime("%d %b %Y")
        + "\n"
        + "🔗 "
        + clean(news["url"])
        + "\n\n"
        + "📷 Real illustrative photographs. "
        + "These are not verified photos "
        + "of the reported event."
        + "\n\n"
        + "Photo 1: "
        + credit1["author"]
        + " | "
        + credit1["license"]
        + "\n"
        + credit1["page"]
        + "\n\n"
        + "Photo 2: "
        + credit2["author"]
        + " | "
        + credit2["license"]
        + "\n"
        + credit2["page"]
        + "\n\n"
        + "AI-assisted summary based on "
        + "RSS headline metadata. "
        + "Read original reporting "
        + "for complete context."
        + "\n\n"
        + "#FACTZAI #LatestNews "
        + "#HinglishNews #NewsUpdate"
    )

    (OUT / "caption.txt").write_text(
        caption,
        encoding="utf-8"
    )

    (OUT / "news_id.txt").write_text(
        clean(news["id"]),
        encoding="utf-8"
    )

    print(
        "SUCCESS: 2 FACTZAI "
        "real-photo carousel slides created"
    )


if __name__ == "__main__":
    main()
