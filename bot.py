"""FACTZAI news carousel. Reads latest_news.json; never uses fixed facts."""

import json
import os
import re
import subprocess
import tempfile

from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw, ImageFont, features
from google import genai
from google.genai import types


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "output"

BRAND = "FACTZAI"

NAVY = (8, 14, 28)
YELLOW = (255, 214, 49)
WHITE = (245, 247, 252)
MUTED = (168, 181, 205)

SIZE = 1080


# ==========================================
# FONTS
# ==========================================

def font(size, bold=False):

    if not features.check("raqm"):
        raise RuntimeError(
            "Pillow needs libraqm to render Hindi correctly"
        )

    paths = [
        "/usr/share/fonts/truetype/noto/NotoSansDevanagari-%s.ttf"
        % ("Bold" if bold else "Regular"),

        "/usr/share/fonts/truetype/noto/NotoSansDevanagariUI-%s.ttf"
        % ("Bold" if bold else "Regular"),
    ]

    for p in paths:
        if Path(p).is_file():
            return ImageFont.truetype(p, size)

    try:
        p = subprocess.check_output(
            [
                "fc-match",
                "-f",
                "%{file}",
                "Noto Sans Devanagari",
            ],
            text=True,
            timeout=5,
        ).strip()

        if "Devanagari" in p and Path(p).is_file():
            return ImageFont.truetype(p, size)

    except Exception:
        pass

    import requests

    target = (
        Path(tempfile.gettempdir())
        / "factzai_noto.ttf"
    )

    if not target.is_file():

        url = (
            "https://raw.githubusercontent.com/"
            "google/fonts/main/ofl/"
            "notosansdevanagari/"
            "NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
        )

        r = requests.get(url, timeout=35)
        r.raise_for_status()

        target.write_bytes(r.content)

    return ImageFont.truetype(
        str(target),
        size,
    )


# ==========================================
# TEXT HELPERS
# ==========================================

def clean(s):

    return re.sub(
        r"\s+",
        " ",
        str(s or ""),
    ).strip()


# ==========================================
# GEMINI NEWS WRITING
# ==========================================

def ai_copy(story):

    key = os.getenv("GEMINI_API_KEY")

    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY secret missing"
        )

    prompt = f"""
You are a cautious Hindi/Hinglish news editor.

Only the following RSS metadata is known,
NOT the full article.

Headline: {story['title']}
Source: {story['source']}
Category: {story['category']}
Published UTC: {story['published_utc']}

Do not invent quotes, numbers, details,
consequences, or claims not directly
supported by the headline.

Write in Devanagari Hindi mixed with
English words, simple and neutral.

If headline is uncertain,
preserve that uncertainty.

Return ONLY JSON with strings:

headline (40-105 chars)
point1 (35-105 chars)
point2 (35-105 chars)
caption (60-230 chars)

point1 should rephrase the confirmed headline.

point2 should state that more details
require the original report.

Do not fabricate why it matters.

Do not include hashtags, URLs,
emojis, or Markdown.

No explicit sexual content.
"""

    client = genai.Client(
        api_key=key
    )

    model = os.getenv(
        "GEMINI_MODEL",
        "gemini-3.5-flash-lite",
    )

    for attempt in range(3):

        response = client.models.generate_content(
            model=model,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                temperature=0.15,
            ),
        )

        data = json.loads(
            response.text or "{}"
        )

        limits = {
            "headline": (20, 130),
            "point1": (20, 135),
            "point2": (20, 135),
            "caption": (35, 260),
        }

        data = {
            k: clean(data.get(k))
            for k in limits
        }

        valid_lengths = all(
            lo <= len(data[k]) <= hi
            for k, (lo, hi) in limits.items()
        )

        has_hindi = any(
            "\u0900" <= c <= "\u097f"
            for c in data["headline"]
        )

        if valid_lengths and has_hindi:
            return data

        prompt += """
Your previous output was too long,
too short, or not Hindi.

Follow limits exactly.
"""

    raise RuntimeError(
        "Gemini did not produce valid Hindi "
        "news copy; refusing to publish"
    )


# ==========================================
# TEXT WRAPPING
# ==========================================

def wrapped(
    draw,
    text,
    face,
    max_width,
):

    lines = []
    current = ""

    for word in clean(text).split(" "):

        candidate = (
            current + " " + word
        ).strip()

        width = draw.textbbox(
            (0, 0),
            candidate,
            font=face,
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


def text_block(
    draw,
    text,
    xy,
    max_width,
    max_height,
    start_size=54,
    color=WHITE,
    bold=True,
):

    x, y = xy

    for size in range(
        start_size,
        25,
        -2,
    ):

        face = font(
            size,
            bold,
        )

        lines = wrapped(
            draw,
            text,
            face,
            max_width,
        )

        step = int(
            size * 1.48
        )

        fits_height = (
            len(lines) * step
            <= max_height
        )

        fits_width = all(
            draw.textbbox(
                (0, 0),
                line,
                font=face,
            )[2] <= max_width
            for line in lines
        )

        if fits_height and fits_width:

            for line in lines:

                draw.text(
                    (x, y),
                    line,
                    font=face,
                    fill=color,
                )

                y += step

            return y

    raise ValueError(
        "Text too long for slide; "
        "not publishing clipped text"
    )


# ==========================================
# FACTZAI SLIDE DESIGN
# ==========================================

def base(
    slide_no,
    category,
    date,
):

    img = Image.new(
        "RGB",
        (SIZE, SIZE),
        NAVY,
    )

    d = ImageDraw.Draw(img)

    # Yellow top border

    d.rectangle(
        (0, 0, SIZE, 18),
        fill=YELLOW,
    )

    # Brand

    d.text(
        (65, 48),
        BRAND,
        font=font(72, True),
        fill=YELLOW,
    )

    d.text(
        (70, 150),
        "LATEST NEWS  /  "
        + str(slide_no).zfill(2),
        font=font(29, True),
        fill=WHITE,
    )

    # Category box

    d.rounded_rectangle(
        (65, 215, 1015, 285),
        radius=16,
        fill=(25, 36, 57),
    )

    d.text(
        (88, 225),
        clean(category).upper()[:34],
        font=font(32, True),
        fill=YELLOW,
    )

    # Bottom border

    d.line(
        (65, 978, 1015, 978),
        fill=YELLOW,
        width=3,
    )

    d.text(
        (65, 998),
        date + "  •  AI-assisted news summary",
        font=font(23),
        fill=MUTED,
    )

    d.text(
        (890, 998),
        "@fac.tzai",
        font=font(23, True),
        fill=YELLOW,
    )

    return img, d


# ==========================================
# MAIN NEWS GENERATOR
# ==========================================

def main():

    story_file = (
        ROOT / "latest_news.json"
    )

    if not story_file.is_file():
        raise RuntimeError(
            "latest_news.json missing. "
            "Run news_bot.py first."
        )

    story = json.loads(
        story_file.read_text(
            encoding="utf-8"
        )
    )

    required_fields = (
        "id",
        "title",
        "url",
        "source",
        "published_utc",
        "category",
    )

    for key in required_fields:

        if not clean(story.get(key)):
            raise RuntimeError(
                "News metadata missing: "
                + key
            )

    date = datetime.fromisoformat(
        story["published_utc"]
    ).strftime("%d %b %Y")

    # Gemini news content

    copy = ai_copy(story)

    OUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    # ======================================
    # SLIDE 1 - HEADLINE
    # ======================================

    first, d1 = base(
        1,
        story["category"],
        date,
    )

    d1.text(
        (65, 327),
        "आज की बड़ी खबर",
        font=font(40, True),
        fill=YELLOW,
    )

    text_block(
        d1,
        copy["headline"],
        (65, 415),
        950,
        380,
        68,
    )

    d1.rounded_rectangle(
        (65, 835, 1015, 928),
        radius=22,
        fill=YELLOW,
    )

    d1.text(
        (95, 852),
        "SWIPE  →  पूरी जानकारी",
        font=font(35, True),
        fill=NAVY,
    )

    # ======================================
    # SLIDE 2 - NEWS DETAILS
    # ======================================

    second, d2 = base(
        2,
        story["category"],
        date,
    )

    d2.text(
        (65, 325),
        "क्या पता चला?",
        font=font(45, True),
        fill=YELLOW,
    )

    y = text_block(
        d2,
        "01  " + copy["point1"],
        (65, 415),
        945,
        200,
        43,
    )

    text_block(
        d2,
        "02  " + copy["point2"],
        (
            65,
            max(y + 42, 640),
        ),
        945,
        190,
        40,
    )

    d2.text(
        (65, 890),
        "SOURCE: "
        + clean(story["source"])[:38],
        font=font(28, True),
        fill=YELLOW,
    )

    d2.text(
        (65, 934),
        "Original report link in caption",
        font=font(24),
        fill=MUTED,
    )

    # ======================================
    # SAVE INSTAGRAM SLIDES
    # ======================================

    first.save(
        OUT / "slide_1.jpg",
        quality=93,
        subsampling=0,
    )

    second.save(
        OUT / "slide_2.jpg",
        quality=93,
        subsampling=0,
    )

    # ======================================
    # INSTAGRAM CAPTION
    # ======================================

    caption = (
        copy["caption"]
        + "\n\n"
        + "📰 Source: "
        + story["source"]
        + "\n"
        + "📅 Published: "
        + date
        + "\n"
        + "🔗 "
        + story["url"]
        + "\n\n"
        + "AI-assisted summary based on "
        + "a news headline; see original "
        + "report for details."
        + "\n\n"
        + "#FACTZAI #LatestNews #NewsUpdate"
    )

    (
        OUT / "caption.txt"
    ).write_text(
        caption,
        encoding="utf-8",
    )

    (
        OUT / "news_id.txt"
    ).write_text(
        story["id"],
        encoding="utf-8",
    )

    print(
        "FACTZAI news carousel generated:",
        story["title"],
    )


if __name__ == "__main__":
    main()
