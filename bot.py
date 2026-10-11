
"""Generate two Hindi-English Instagram carousel slides.

Outputs:
    output/slide_1.jpg
    output/slide_2.jpg
    output/caption.txt

Photos come from Wikipedia/Wikimedia, not image-generation AI.
Check photo licenses and factual accuracy before automated publication.
"""

from __future__ import annotations

import io
import json
import os
import random
import re
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import (
    Image,
    ImageDraw,
    ImageEnhance,
    ImageFont,
    ImageOps,
    features,
)
from google import genai
from google.genai import types


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"

MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
BRAND = os.getenv("BRAND_NAME", "FACT DAILY")[:20].upper()

SIDE = 1080
Y_PANEL = 565

MAX_CONTENT_ATTEMPTS = 5
MAX_SOURCE_ATTEMPTS = 3

TOPICS = [
    "Octopus",
    "Honey bee",
    "Venus",
    "Jupiter",
    "Saturn",
    "Mars",
    "Great Barrier Reef",
    "Antarctica",
    "Hummingbird",
    "Koala",
    "Blue whale",
    "Giant panda",
    "Lightning",
    "Solar eclipse",
    "Aurora",
    "Volcano",
    "Giraffe",
    "Dolphin",
    "Penguin",
    "Red panda",
    "Elephant",
    "Chameleon",
    "Axolotl",
    "Coral reef",
    "Baobab",
    "Mount Everest",
    "Moon",
    "Neptune",
    "Red fox",
    "Owl",
]

HTTP = requests.Session()
HTTP.headers.update({
    "User-Agent": (
        "FactDailyInstagramBot/3.0 "
        "(educational project; "
        "https://github.com/sufiyan123-bop/instagram-ai-bot)"
    )
})


def get_verified_source(excluded=None):
    """Find a Wikipedia article with text and a usable photo."""

    excluded = excluded or set()
    topics = [t for t in TOPICS if t not in excluded]
    random.shuffle(topics)

    for name in topics:
        endpoint = (
            "https://en.wikipedia.org/api/rest_v1/page/summary/"
            + quote(name.replace(" ", "_"))
        )

        try:
            response = HTTP.get(
                endpoint,
                timeout=20,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()
            data = response.json()

            extract = (data.get("extract") or "").strip()

            photos = []
            for kind in ("originalimage", "thumbnail"):
                url = (data.get(kind) or {}).get("source", "")

                if url.lower().split("?")[0].endswith(
                    (".jpg", ".jpeg", ".png", ".webp")
                ):
                    if url not in photos:
                        photos.append(url)

            if (
                len(extract) < 180
                or data.get("type") == "disambiguation"
                or not photos
            ):
                continue

            source = (
                data.get("content_urls", {})
                .get("desktop", {})
                .get("page", endpoint)
            )

            return (
                data.get("title", name),
                extract[:2600],
                source,
                photos,
                name,
            )

        except (requests.RequestException, ValueError, KeyError):
            continue

    raise RuntimeError("No suitable Wikipedia article found.")


def has_hindi_and_english(text):
    return (
        bool(re.search(r"[\u0900-\u097f]", text))
        and bool(re.search(r"[A-Za-z]", text))
    )


def normalize_text(value):
    """Remove formatting that should not appear on slides."""

    if not isinstance(value, str):
        return ""

    value = re.sub(r"\s+", " ", value).strip()
    value = value.strip("`\"' ")

    return value


def validate_copy(data):
    """Validate AI copy without cutting sentences mid-word."""

    if not isinstance(data, dict):
        raise ValueError("Gemini response is not a JSON object.")

    limits = {
        "hook": (10, 48),
        "fact": (15, 85),
        "explanation": (30, 130),
        "caption": (20, 200),
    }

    clean = {}

    for field, (minimum, maximum) in limits.items():
        value = normalize_text(data.get(field))

        if len(value) < minimum:
            raise ValueError(
                f"{field} too short: {len(value)} characters"
            )

        if len(value) > maximum:
            raise ValueError(
                f"{field} too long: {len(value)} characters"
            )

        clean[field] = value

    for field in ("fact", "explanation"):
        if not has_hindi_and_english(clean[field]):
            raise ValueError(
                f"{field} must contain Hindi and English"
            )

    return clean


def generate_mixed_copy(title, extract, source, client):
    """Retry Gemini when it ignores character limits."""

    prompt = f"""
Create accurate educational Instagram carousel copy.

Use ONLY facts supported by the Wikipedia excerpt below.
Do not invent facts, numbers, or scientific claims.

Language:
- Natural Hindi in Devanagari mixed with English words.
- Both fact and explanation MUST contain Hindi and English.
- Do not use only Roman Hinglish.
- No emojis, hashtags, URLs, or markdown inside JSON values.

Return ONLY a JSON object containing exactly:
hook, fact, explanation, caption

STRICT CHARACTER LIMITS INCLUDING SPACES:
hook: 12 to 36 characters
fact: 20 to 75 characters
explanation: 45 to 105 characters
caption: 25 to 150 characters

Make sentences complete and concise.
Keep the explanation especially short.
Do not repeat the fact in the explanation.

Topic: {title}
Wikipedia source: {source}
Wikipedia excerpt: {extract}
"""

    last_error = None

    for attempt in range(1, MAX_CONTENT_ATTEMPTS + 1):
        print(
            f"Gemini generation attempt "
            f"{attempt}/{MAX_CONTENT_ATTEMPTS}"
        )

        try:
            result = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                ),
            )

            if not result.text:
                raise ValueError("Gemini returned empty content.")

            data = json.loads(result.text)
            clean = validate_copy(data)

            print("Gemini content validated successfully.")
            return clean

        except (
            ValueError,
            TypeError,
            KeyError,
        ) as exc:
            last_error = exc
            print(
                "Content validation failed:",
                str(exc)[:180],
            )

            # Tell Gemini exactly why the previous output failed.
            prompt += (
                "\nIMPORTANT CORRECTION: Your previous output "
                f"was rejected because: {str(exc)[:150]}. "
                "Return NEW, SHORTER, COMPLETE sentences "
                "within ALL character limits.\n"
            )

        except Exception as exc:
            last_error = exc
            print(
                "Gemini request failed:",
                type(exc).__name__,
            )

        if attempt < MAX_CONTENT_ATTEMPTS:
            time.sleep(min(2 * attempt, 8))

    raise RuntimeError(
        "Gemini could not generate valid content "
        f"after {MAX_CONTENT_ATTEMPTS} attempts. "
        f"Last error: {type(last_error).__name__}"
    )


def download_photo(urls):
    """Download a real photo, trying alternate sizes."""

    for url in urls:
        try:
            with HTTP.get(
                url,
                timeout=45,
                stream=True,
            ) as response:

                response.raise_for_status()

                raw = bytearray()

                for chunk in response.iter_content(65536):
                    raw.extend(chunk)

                    if len(raw) > 22 * 1024 * 1024:
                        raise ValueError("Image too large.")

            with Image.open(io.BytesIO(raw)) as image:
                image.load()

                if image.width < 300 or image.height < 260:
                    raise ValueError("Image too small.")

                photo = ImageOps.exif_transpose(image)
                return photo.convert("RGB"), url

        except (
            requests.RequestException,
            ValueError,
            OSError,
        ) as exc:
            print(
                "Skipping photo:",
                type(exc).__name__,
            )

    raise RuntimeError("No usable Wikipedia photo found.")


def load_font(size, bold=False, script="hi"):
    """Load fonts for Hindi and English."""

    if script == "en":
        path = (
            "/usr/share/fonts/truetype/dejavu/"
            + (
                "DejaVuSans-Bold.ttf"
                if bold
                else "DejaVuSans.ttf"
            )
        )
        return ImageFont.truetype(path, size)

    if not features.check("raqm"):
        raise RuntimeError(
            "Pillow libraqm required for Hindi text."
        )

    candidates = [
        (
            "/usr/share/fonts/truetype/noto/"
            + (
                "NotoSansDevanagari-Bold.ttf"
                if bold
                else "NotoSansDevanagari-Regular.ttf"
            )
        ),
        (
            "/usr/share/fonts/truetype/noto/"
            + (
                "NotoSansDevanagariUI-Bold.ttf"
                if bold
                else "NotoSansDevanagariUI-Regular.ttf"
            )
        ),
    ]

    path = next(
        (Path(p) for p in candidates if Path(p).is_file()),
        None,
    )

    if path is None:
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
                path = Path(matched)

        except (OSError, subprocess.SubprocessError):
            pass

    if path is None:
        path = (
            Path(tempfile.gettempdir())
            / "autopost_noto_devanagari.ttf"
        )

        if not path.is_file():
            font_url = (
                "https://raw.githubusercontent.com/"
                "google/fonts/main/ofl/"
                "notosansdevanagari/"
                "NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf"
            )

            response = HTTP.get(font_url, timeout=35)
            response.raise_for_status()
            path.write_bytes(response.content)

    font = ImageFont.truetype(
        str(path),
        size,
        layout_engine=ImageFont.Layout.RAQM,
    )

    try:
        axes = font.get_variation_axes()

        if axes:
            coordinates = []

            for axis in axes:
                axis_name = axis["name"]

                if isinstance(axis_name, bytes):
                    axis_name = axis_name.decode()

                if "Weight" in axis_name:
                    coordinates.append(
                        800 if bold else 500
                    )
                else:
                    coordinates.append(axis["default"])

            font.set_variation_by_axes(coordinates)

    except (OSError, AttributeError, ValueError):
        pass

    return font


def center_fit(
    draw,
    text,
    y1,
    y2,
    width,
    size_start,
    color,
    max_lines,
    bold=True,
    highlight=False,
):
    """Fit mixed Hindi-English text into a slide panel."""

    for size in range(size_start, 21, -2):
        hindi_font = load_font(
            size,
            bold,
            script="hi",
        )

        english_font = load_font(
            int(size * 0.88),
            bold,
            script="en",
        )

        space_width = draw.textlength(
            " ",
            font=english_font,
        )

        lines = []
        line = []
        used = 0.0
        overflow = False

        for word in text.split():
            is_hindi = bool(
                re.search(r"[\u0900-\u097f]", word)
            )

            font = (
                hindi_font
                if is_hindi
                else english_font
            )

            word_width = draw.textlength(
                word,
                font=font,
                language="hi" if is_hindi else "en",
            )

            if word_width > width:
                overflow = True
                break

            extra = (
                space_width
                if line
                else 0
            ) + word_width

            if line and used + extra > width:
                lines.append((line, used))
                line = []
                used = 0.0

            if line:
                used += space_width

            line.append(
                (
                    word,
                    font,
                    word_width,
                    is_hindi,
                )
            )
            used += word_width

        if overflow:
            continue

        if line:
            lines.append((line, used))

        line_height = int(size * 1.42)

        if (
            len(lines) > max_lines
            or len(lines) * line_height > y2 - y1
        ):
            continue

        baseline = (
            y1
            + (y2 - y1 - len(lines) * line_height) / 2
            + int(size * 1.05)
        )

        for words, line_width in lines:
            x = (SIDE - line_width) / 2

            for index, (
                word,
                font,
                word_width,
                is_hindi,
            ) in enumerate(words):

                if index:
                    x += space_width

                accent = (
                    bool(re.search(r"\d", word))
                    or word.strip("!?.।").upper()
                    in {"BLUE", "COPPER"}
                )

                ink = (
                    (255, 224, 35)
                    if highlight and accent
                    else color
                )

                draw.text(
                    (round(x), round(baseline)),
                    word,
                    font=font,
                    anchor="ls",
                    fill=ink,
                    language=(
                        "hi"
                        if is_hindi
                        else "en"
                    ),
                )

                x += word_width

            baseline += line_height

        return

    raise ValueError(
        "Text could not fit inside the slide."
    )


def design_slide(position, photo, copy):
    """Create a 1080x1080 carousel image."""

    crop = ImageOps.fit(
        photo,
        (SIDE, Y_PANEL + 78),
        method=Image.Resampling.LANCZOS,
        centering=(
            0.50 if position == 1 else 0.62,
            0.47,
        ),
    )

    crop = ImageEnhance.Contrast(crop).enhance(1.12)
    crop = ImageEnhance.Color(crop).enhance(1.18)

    slide = Image.new(
        "RGB",
        (SIDE, SIDE),
        (7, 7, 9),
    )
    slide.paste(crop, (0, 0))

    shade = Image.new(
        "RGBA",
        (SIDE, SIDE),
        (0, 0, 0, 0),
    )

    shader = ImageDraw.Draw(shade)

    for y in range(445, Y_PANEL + 100):
        alpha = int(
            255
            * min(
                1.0,
                max(
                    0,
                    (y - 445)
                    / (Y_PANEL + 75 - 445),
                ),
            )
        )

        shader.line(
            (0, y, SIDE, y),
            fill=(0, 0, 0, alpha),
            width=1,
        )

    slide = Image.alpha_composite(
        slide.convert("RGBA"),
        shade,
    ).convert("RGB")

    draw = ImageDraw.Draw(slide)

    yellow = (255, 224, 35)
    white = (252, 252, 250)
    cyan = (44, 209, 249)

    draw.rounded_rectangle(
        (905, 25, 1044, 92),
        radius=32,
        fill=(8, 10, 14),
    )

    draw.text(
        (974, 61),
        f"{position}/2",
        font=load_font(
            35,
            True,
            script="en",
        ),
        anchor="mm",
        fill=white,
    )

    if position == 1:
        center_fit(
            draw,
            copy["hook"],
            588,
            678,
            990,
            67,
            yellow,
            2,
        )

        center_fit(
            draw,
            copy["fact"],
            694,
            918,
            980,
            76,
            white,
            3,
            highlight=True,
        )

        bottom = "SWIPE  >>>"

    else:
        center_fit(
            draw,
            "और भी हैरानी की बात!",
            584,
            683,
            1000,
            57,
            yellow,
            2,
        )

        center_fit(
            draw,
            copy["explanation"],
            687,
            918,
            990,
            58,
            white,
            4,
            highlight=True,
        )

        bottom = "SOURCE IN CAPTION"

    draw.rounded_rectangle(
        (392, 934, 688, 942),
        radius=4,
        fill=yellow,
    )

    draw.text(
        (66, 1023),
        BRAND,
        font=load_font(
            24,
            True,
            script="en",
        ),
        anchor="lm",
        fill=(200, 200, 200),
    )

    draw.text(
        (1015, 1023),
        bottom,
        font=load_font(
            24,
            True,
            script="en",
        ),
        anchor="rm",
        fill=cyan,
    )

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    destination = OUTPUT / f"slide_{position}.jpg"

    slide.save(
        destination,
        format="JPEG",
        quality=93,
        optimize=True,
        subsampling=0,
    )

    return destination


def main():
    """Generate a complete carousel with automatic retries."""

    print("Starting Instagram carousel generation.")

    api_key = os.getenv(
        "GEMINI_API_KEY",
        "",
    ).strip()

    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY secret is missing."
        )

    client = genai.Client(api_key=api_key)

    OUTPUT.mkdir(
        parents=True,
        exist_ok=True,
    )

    excluded_topics = set()
    last_error = None

    for source_attempt in range(
        1,
        MAX_SOURCE_ATTEMPTS + 1,
    ):
        print(
            f"Source attempt "
            f"{source_attempt}/{MAX_SOURCE_ATTEMPTS}"
        )

        try:
            (
                topic,
                excerpt,
                source,
                image_urls,
                topic_key,
            ) = get_verified_source(
                excluded_topics
            )

            excluded_topics.add(topic_key)

            print("Selected topic:", topic)

            photo, image_url = download_photo(
                image_urls
            )

            copy = generate_mixed_copy(
                topic,
                excerpt,
                source,
                client,
            )

            first = design_slide(
                1,
                photo,
                copy,
            )

            second = design_slide(
                2,
                photo,
                copy,
            )

            caption = (
                f"{copy['caption']}\n\n"
                f"Source: {source}\n"
                "Image source (check license/attribution): "
                f"{image_url}\n\n"
                "#AmazingFacts #HindiFacts "
                "#Knowledge #Facts"
            )

            (OUTPUT / "caption.txt").write_text(
                caption,
                encoding="utf-8",
            )

            (
                OUTPUT / "source_excerpt.txt"
            ).write_text(
                f"TOPIC: {topic}\n"
                f"SOURCE: {source}\n"
                f"IMAGE: {image_url}\n\n"
                f"{excerpt}\n",
                encoding="utf-8",
            )

            print(
                "SUCCESS:",
                first.name,
                second.name,
                "1080x1080",
            )

            print(
                "Caption generated successfully."
            )

            return

        except Exception as exc:
            last_error = exc

            print(
                "Generation attempt failed:",
                type(exc).__name__,
                str(exc)[:250],
            )

            if source_attempt < MAX_SOURCE_ATTEMPTS:
                time.sleep(3)

    raise RuntimeError(
        "Carousel generation failed after retries. "
        f"Last error: {type(last_error).__name__}: "
        f"{str(last_error)[:200]}"
    )


if __name__ == "__main__":
    main()
