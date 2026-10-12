"""
FACTZAI NEWS CAROUSEL GENERATOR

Input:
    latest_news.json

Outputs:
    output/slide_1.jpg
    output/slide_2.jpg
    output/caption.txt
    output/news_id.txt

Features:
    - Hindi + Hinglish news
    - FACTZAI black/yellow branding
    - AI-generated news illustration when available
    - Safe graphic fallback
    - No old random facts
"""

import io
import json
import os
import re
import subprocess
import tempfile
import time

from pathlib import Path
from datetime import datetime, timezone

import requests

from PIL import (
    Image,
    ImageDraw,
    ImageFont,
    ImageOps,
    features,
)

from google import genai
from google.genai import types


# ==========================================
# SETTINGS
# ==========================================

ROOT = Path(__file__).resolve().parent

OUTPUT = ROOT / "output"

NEWS_FILE = ROOT / "latest_news.json"

BRAND = "FACTZAI"

INSTAGRAM = "@fac.tzai"

SIZE = 1080

NAVY = (8, 14, 28)

DARK = (18, 29, 49)

YELLOW = (255, 215, 50)

WHITE = (247, 249, 252)

MUTED = (174, 186, 206)

TEXT_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite",
)

IMAGE_MODEL = os.getenv(
    "GEMINI_IMAGE_MODEL",
    "gemini-2.5-flash-image",
)

ENABLE_AI_IMAGE = os.getenv(
    "ENABLE_AI_IMAGE",
    "true",
).lower() == "true"


# ==========================================
# FONTS
# ==========================================

def get_font(size, bold=False):

    if not features.check("raqm"):
        raise RuntimeError(
            "Pillow libraqm is required "
            "for Hindi text rendering."
        )

    style = "Bold" if bold else "Regular"

    candidates = [
        (
            "/usr/share/fonts/truetype/noto/"
            f"NotoSansDevanagari-{style}.ttf"
        ),
        (
            "/usr/share/fonts/truetype/noto/"
            f"NotoSansDevanagariUI-{style}.ttf"
        ),
    ]

    for path in candidates:

        if Path(path).is_file():
            return ImageFont.truetype(
                path,
                size,
            )

    try:

        matched = subprocess.check_output(
            [
                "fc-match",
                "-f",
                "%{file}",
                "Noto Sans Devanagari",
            ],
            text=True,
            timeout=5,
        ).strip()

        if (
            "Devanagari" in matched
            and Path(matched).is_file()
        ):

            return ImageFont.truetype(
                matched,
                size,
            )

    except Exception:
        pass

    font_path = (
        Path(tempfile.gettempdir())
        / "factzai_hindi_font.ttf"
    )

    if not font_path.exists():

        url = (
            "https://raw.githubusercontent.com/"
            "google/fonts/main/ofl/"
            "notosansdevanagari/"
            "NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
        )

        response = requests.get(
            url,
            timeout=40,
        )

        response.raise_for_status()

        font_path.write_bytes(
            response.content
        )

    return ImageFont.truetype(
        str(font_path),
        size,
    )


# ==========================================
# TEXT HELPERS
# ==========================================

def clean_text(value):

    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def has_hindi(text):

    return bool(
        re.search(
            r"[\u0900-\u097f]",
            text,
        )
    )


def wrap_text(
    draw,
    text,
    font,
    max_width,
):

    words = clean_text(text).split()

    lines = []

    current = ""

    for word in words:

        candidate = (
            current + " " + word
        ).strip()

        width = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
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


def draw_fitted_text(
    draw,
    text,
    x,
    y,
    width,
    height,
    max_size=58,
    min_size=25,
    color=WHITE,
    bold=True,
):

    for size in range(
        max_size,
        min_size - 1,
        -2,
    ):

        font = get_font(
            size,
            bold,
        )

        lines = wrap_text(
            draw,
            text,
            font,
            width,
        )

        line_height = int(
            size * 1.55
        )

        total_height = (
            len(lines) * line_height
        )

        all_fit = all(
            draw.textbbox(
                (0, 0),
                line,
                font=font,
            )[2] <= width
            for line in lines
        )

        if (
            total_height <= height
            and all_fit
        ):

            for line in lines:

                draw.text(
                    (x, y),
                    line,
                    font=font,
                    fill=color,
                )

                y += line_height

            return y

    raise RuntimeError(
        "News text does not fit slide. "
        "Refusing to create clipped post."
    )


# ==========================================
# READ LATEST NEWS
# ==========================================

def load_news():

    if not NEWS_FILE.exists():

        raise RuntimeError(
            "latest_news.json missing. "
            "Run news_bot.py first."
        )

    news = json.loads(
        NEWS_FILE.read_text(
            encoding="utf-8"
        )
    )

    required = [
        "id",
        "title",
        "source",
        "url",
        "category",
        "published_utc",
    ]

    for field in required:

        if not clean_text(
            news.get(field)
        ):

            raise RuntimeError(
                f"Missing news field: {field}"
            )

    published = datetime.fromisoformat(
        news["published_utc"]
    )

    if published.tzinfo is None:

        published = published.replace(
            tzinfo=timezone.utc
        )

    age_hours = (
        datetime.now(timezone.utc)
        - published.astimezone(timezone.utc)
    ).total_seconds() / 3600

    if (
        age_hours < -0.1
        or age_hours > 24
    ):

        raise RuntimeError(
            "News is outside the "
            "last 24 hours."
        )

    return news


# ==========================================
# GEMINI NEWS CONTENT
# ==========================================

def generate_news_copy(
    client,
    news,
):

    prompt = f"""
You are the Hindi/Hinglish editor
for an Instagram news page called FACTZAI.

IMPORTANT:
You have ONLY an RSS headline and metadata.
You do NOT have the full original article.

Do not invent:
- numbers
- quotations
- causes
- explanations
- locations
- people
- events
- consequences

Use only what the supplied headline supports.

News headline:
{news["title"]}

News source:
{news["source"]}

News category:
{news["category"]}

Published UTC:
{news["published_utc"]}

Write natural Hindi in Devanagari
mixed with common English words.

Make the writing interesting but neutral.

If the headline describes an allegation,
claim, prediction, or uncertainty,
keep that uncertainty clear.

Return ONLY a JSON object with
exactly these four string keys:

headline
point1
point2
caption

CHARACTER LIMITS:

headline:
35 to 100 characters

point1:
35 to 100 characters

point2:
35 to 100 characters

caption:
55 to 180 characters

point1:
Summarize the main reported development.

point2:
Tell readers to check the original
report for full context.
Do not fabricate extra facts.

No URLs inside JSON.
No hashtags inside JSON.
No Markdown.
No explicit sexual descriptions.
"""

    last_error = None

    for attempt in range(3):

        try:

            result = client.models.generate_content(
                model=TEXT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type=(
                        "application/json"
                    ),
                    temperature=0.2,
                ),
            )

            data = json.loads(
                result.text or "{}"
            )

            limits = {
                "headline": (25, 115),
                "point1": (25, 115),
                "point2": (25, 115),
                "caption": (40, 220),
            }

            output = {}

            for key, (low, high) in limits.items():

                value = clean_text(
                    data.get(key)
                )

                if not (
                    low <= len(value) <= high
                ):

                    raise ValueError(
                        f"{key} length invalid"
                    )

                output[key] = value

            if not has_hindi(
                output["headline"]
            ):

                raise ValueError(
                    "Headline must use Hindi"
                )

            if not has_hindi(
                output["point1"]
            ):

                raise ValueError(
                    "Point 1 must use Hindi"
                )

            return output

        except Exception as error:

            last_error = error

            print(
                "Text generation attempt failed:",
                type(error).__name__,
            )

            prompt += """
Previous response failed validation.
Return shorter, complete sentences
within all character limits.
"""

            if attempt < 2:
                time.sleep(2)

    raise RuntimeError(
        "Could not generate valid "
        "Hindi news content: "
        + type(last_error).__name__
    )


# ==========================================
# AI IMAGE GENERATION
# ==========================================

def generate_ai_image(
    client,
    news,
):

    if not ENABLE_AI_IMAGE:

        print(
            "AI image generation disabled."
        )

        return None

    category = clean_text(
        news["category"]
    )

    title = clean_text(
        news["title"]
    )

    prompt = f"""
Create one premium editorial
illustration for an Indian news
Instagram carousel.

News category:
{category}

News headline:
{title}

STYLE:
- Cinematic editorial illustration
- Modern professional news design
- Dark navy and golden yellow palette
- High contrast
- Beautiful composition
- Detailed lighting
- Landscape 16:9 composition
- No text
- No letters
- No logos
- No watermark

IMPORTANT SAFETY:
This is an AI-generated illustration,
NOT documentary evidence.

Do not fabricate a photograph
of the reported event.

Do not depict unverified events
as if they really happened.

Prefer symbolic or conceptual
visuals connected to the headline.

If the news involves real people,
avoid photorealistic fake depictions
of their actions.

No nudity or explicit sexual imagery.
"""

    try:

        result = client.models.generate_content(
            model=IMAGE_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=[
                    "IMAGE",
                    "TEXT",
                ],
            ),
        )

        if not result.candidates:

            raise RuntimeError(
                "Image model returned "
                "no candidates."
            )

        for candidate in result.candidates:

            content = getattr(
                candidate,
                "content",
                None,
            )

            if not content:
                continue

            for part in (
                content.parts or []
            ):

                inline = getattr(
                    part,
                    "inline_data",
                    None,
                )

                if not inline:
                    continue

                image_bytes = getattr(
                    inline,
                    "data",
                    None,
                )

                if not image_bytes:
                    continue

                with Image.open(
                    io.BytesIO(image_bytes)
                ) as image:

                    image.load()

                    print(
                        "AI illustration generated."
                    )

                    return image.convert(
                        "RGB"
                    )

        raise RuntimeError(
            "No image returned "
            "by Gemini."
        )

    except Exception as error:

        print(
            "AI image unavailable:",
            type(error).__name__,
            str(error)[:160],
        )

        return None


# ==========================================
# GRAPHIC FALLBACK
# ==========================================

def make_fallback_image(
    category,
):

    image = Image.new(
        "RGB",
        (1200, 650),
        DARK,
    )

    draw = ImageDraw.Draw(
        image
    )

    # Decorative circles

    for radius in range(
        400,
        60,
        -45,
    ):

        draw.ellipse(
            (
                600 - radius,
                320 - radius,
                600 + radius,
                320 + radius,
            ),
            outline=(
                80,
                70,
                35,
            ),
            width=3,
        )

    draw.rounded_rectangle(
        (
            105,
            165,
            1095,
            480,
        ),
        radius=35,
        fill=NAVY,
        outline=YELLOW,
        width=5,
    )

    draw.text(
        (150, 205),
        "FACTZAI",
        font=get_font(
            85,
            True,
        ),
        fill=YELLOW,
    )

    draw_fitted_text(
        draw,
        category.upper(),
        155,
        345,
        850,
        95,
        max_size=45,
        min_size=27,
        color=WHITE,
    )

    return image


# ==========================================
# SLIDE BASE DESIGN
# ==========================================

def make_base(
    number,
    category,
    date_text,
):

    image = Image.new(
        "RGB",
        (SIZE, SIZE),
        NAVY,
    )

    draw = ImageDraw.Draw(
        image
    )

    draw.rectangle(
        (0, 0, SIZE, 18),
        fill=YELLOW,
    )

    draw.text(
        (65, 43),
        BRAND,
        font=get_font(
            70,
            True,
        ),
        fill=YELLOW,
    )

    draw.text(
        (68, 145),
        f"LATEST NEWS  /  {number:02d}",
        font=get_font(
            28,
            True,
        ),
        fill=WHITE,
    )

    draw.rounded_rectangle(
        (
            65,
            207,
            1015,
            275,
        ),
        radius=15,
        fill=DARK,
    )

    draw_fitted_text(
        draw,
        category.upper(),
        88,
        219,
        900,
        50,
        max_size=30,
        min_size=25,
        color=YELLOW,
    )

    draw.line(
        (
            65,
            977,
            1015,
            977,
        ),
        fill=YELLOW,
        width=3,
    )

    draw.text(
        (65, 997),
        date_text,
        font=get_font(24),
        fill=MUTED,
    )

    draw.text(
        (845, 997),
        INSTAGRAM,
        font=get_font(
            25,
            True,
        ),
        fill=YELLOW,
    )

    return image, draw


# ==========================================
# SLIDE 1
# ==========================================

def make_slide_one(
    news,
    copy,
    picture,
    ai_generated,
    date_text,
):

    image, draw = make_base(
        1,
        news["category"],
        date_text,
    )

    # News image

    photo = ImageOps.fit(
        picture,
        (950, 415),
        method=Image.Resampling.LANCZOS,
    )

    image.paste(
        photo,
        (65, 300),
    )

    draw.rectangle(
        (
            65,
            300,
            1015,
            715,
        ),
        outline=YELLOW,
        width=3,
    )

    label = (
        "AI-GENERATED ILLUSTRATION"
        if ai_generated
        else "FACTZAI NEWS GRAPHIC"
    )

    draw.rounded_rectangle(
        (
            82,
            654,
            680,
            705,
        ),
        radius=10,
        fill=NAVY,
    )

    draw.text(
        (99, 665),
        label,
        font=get_font(
            24,
            True,
        ),
        fill=YELLOW,
    )

    # News headline

    draw_fitted_text(
        draw,
        copy["headline"],
        65,
        745,
        950,
        160,
        max_size=47,
        min_size=27,
        color=WHITE,
    )

    draw.text(
        (65, 927),
        "SWIPE  →  MORE DETAILS",
        font=get_font(
            25,
            True,
        ),
        fill=YELLOW,
    )

    return image


# ==========================================
# SLIDE 2
# ==========================================

def make_slide_two(
    news,
    copy,
    date_text,
):

    image, draw = make_base(
        2,
        news["category"],
        date_text,
    )

    draw.text(
        (65, 315),
        "पूरी खबर",
        font=get_font(
            48,
            True,
        ),
        fill=YELLOW,
    )

    draw.rounded_rectangle(
        (
            65,
            410,
            1015,
            595,
        ),
        radius=22,
        fill=DARK,
    )

    draw_fitted_text(
        draw,
        "01  " + copy["point1"],
        93,
        440,
        890,
        125,
        max_size=39,
        min_size=25,
        color=WHITE,
    )

    draw.rounded_rectangle(
        (
            65,
            620,
            1015,
            805,
        ),
        radius=22,
        fill=DARK,
    )

    draw_fitted_text(
        draw,
        "02  " + copy["point2"],
        93,
        650,
        890,
        125,
        max_size=39,
        min_size=25,
        color=WHITE,
    )

    draw_fitted_text(
        draw,
        "SOURCE: "
        + clean_text(
            news["source"]
        ),
        65,
        850,
        950,
        55,
        max_size=30,
        min_size=25,
        color=YELLOW,
    )

    draw.text(
        (65, 930),
        "Read original report via caption",
        font=get_font(25),
        fill=MUTED,
    )

    return image


# ==========================================
# SAVE OUTPUTS
# ==========================================

def save_outputs(
    news,
    copy,
    slide1,
    slide2,
    date_text,
    ai_generated,
):

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    slide1.save(
        OUTPUT / "slide_1.jpg",
        "JPEG",
        quality=93,
        subsampling=0,
    )

    slide2.save(
        OUTPUT / "slide_2.jpg",
        "JPEG",
        quality=93,
        subsampling=0,
    )

    caption = (
        copy["caption"]
        + "\n\n"
        + "📰 Source: "
        + news["source"]
        + "\n"
        + "📅 Published: "
        + date_text
        + "\n"
        + "🔗 "
        + news["url"]
        + "\n\n"
        + (
            "🎨 Visual: AI-generated illustration"
            if ai_generated
            else "🎨 Visual: FACTZAI graphic"
        )
        + "\n"
        + "AI-assisted summary based on "
        + "news headline metadata. "
        + "Read the original report "
        + "for full context."
        + "\n\n"
        + "#FACTZAI #LatestNews "
        + "#HindiNews #NewsUpdate"
    )

    (
        OUTPUT / "caption.txt"
    ).write_text(
        caption,
        encoding="utf-8",
    )

    (
        OUTPUT / "news_id.txt"
    ).write_text(
        news["id"],
        encoding="utf-8",
    )

    print(
        "FACTZAI slides created."
    )

    print(
        "Slide 1:",
        OUTPUT / "slide_1.jpg",
    )

    print(
        "Slide 2:",
        OUTPUT / "slide_2.jpg",
    )

    print(
        "AI image used:",
        ai_generated,
    )


# ==========================================
# MAIN
# ==========================================

def main():

    print(
        "Starting FACTZAI News Bot..."
    )

    news = load_news()

    print(
        "Selected news:",
        news["title"],
    )

    api_key = os.getenv(
        "GEMINI_API_KEY",
        "",
    ).strip()

    if not api_key:

        raise RuntimeError(
            "GEMINI_API_KEY missing"
        )

    client = genai.Client(
        api_key=api_key
    )

    # Generate news copy

    copy = generate_news_copy(
        client,
        news,
    )

    # Generate topic-related AI image

    picture = generate_ai_image(
        client,
        news,
    )

    ai_generated = (
        picture is not None
    )

    # Safe fallback if image API fails

    if picture is None:

        picture = make_fallback_image(
            news["category"]
        )

    date_text = datetime.fromisoformat(
        news["published_utc"]
    ).strftime(
        "%d %b %Y"
    )

    slide1 = make_slide_one(
        news,
        copy,
        picture,
        ai_generated,
        date_text,
    )

    slide2 = make_slide_two(
        news,
        copy,
        date_text,
    )

    save_outputs(
        news,
        copy,
        slide1,
        slide2,
        date_text,
        ai_generated,
    )

    print(
        "FACTZAI NEWS GENERATION COMPLETE"
    )


if __name__ == "__main__":
    main()
