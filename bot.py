"""
FACTZAI - REALISTIC AI NEWS CAROUSEL

Creates:
 output/slide_1.jpg
 output/slide_2.jpg
 output/caption.txt
 output/news_id.txt

Both slides use realistic AI-generated visuals.
No generic-image fallback.
"""

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


ROOT = Path(__file__).resolve().parent
NEWS_FILE = ROOT / "latest_news.json"
OUT = ROOT / "output"

SIZE = 1080

NAVY = (7, 13, 27)
DARK = (14, 23, 41)
YELLOW = (255, 211, 45)
WHITE = (250, 251, 253)
GREY = (186, 194, 207)

TEXT_MODEL = os.getenv(
    "GEMINI_MODEL",
    "gemini-3.5-flash-lite"
)

IMAGE_MODEL = os.getenv(
    "GEMINI_IMAGE_MODEL",
    "gemini-2.5-flash-image"
)

API_KEY = os.getenv("GEMINI_API_KEY", "").strip()


# ---------------------------------
# FONTS
# ---------------------------------

def font(size, bold=False):
    candidates = [
        "/usr/share/fonts/truetype/noto/"
        "NotoSansDevanagari-Bold.ttf",
        "/usr/share/fonts/truetype/noto/"
        "NotoSansDevanagari-Regular.ttf",
    ]

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)

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
            return ImageFont.truetype(path, size)

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
        response = requests.get(url, timeout=45)
        response.raise_for_status()
        local.write_bytes(response.content)

    return ImageFont.truetype(str(local), size)


# ---------------------------------
# HELPERS
# ---------------------------------

def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def wrap(draw, text, chosen_font, max_width):
    lines = []
    current = ""

    for word in clean(text).split():
        candidate = (current + " " + word).strip()

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
    for size in range(max_font, min_font - 1, -2):
        chosen = font(size, True)
        lines = wrap(draw, text, chosen, max_width)
        line_height = int(size * 1.52)

        fits_width = all(
            draw.textbbox(
                (0, 0), line, font=chosen
            )[2] <= max_width
            for line in lines
        )

        if (
            fits_width
            and len(lines) * line_height <= max_height
        ):
            for line in lines:
                draw.text(
                    (x, y),
                    line,
                    font=chosen,
                    fill=fill,
                    stroke_width=0
                )
                y += line_height
            return

    raise RuntimeError(
        "Text too long for carousel layout"
    )


def load_news():
    if not NEWS_FILE.exists():
        raise RuntimeError("latest_news.json missing")

    news = json.loads(
        NEWS_FILE.read_text(encoding="utf-8")
    )

    for key in (
        "id", "title", "source",
        "url", "category", "published_utc"
    ):
        if not clean(news.get(key)):
            raise RuntimeError(
                f"Missing news field: {key}"
            )

    published = datetime.fromisoformat(
        news["published_utc"].replace("Z", "+00:00")
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

    return news


# ---------------------------------
# AI NEWS WRITING
# ---------------------------------

def create_copy(client, news):
    prompt = f"""
You are FACTZAI, a premium Indian Instagram
news editor.

Source headline:
{news["title"]}

Source:
{news["source"]}

Category:
{news["category"]}

You only know the RSS headline.
You have NOT read the full article.

Create short, accurate news copy.
Use modern Hinglish: a natural mixture of
Hindi Devanagari and English words.

IMPORTANT:
Do NOT write everything in pure Hindi.
Do NOT write everything in English.
Use both languages naturally.

Example of style:
"AI Technology में आया बड़ा Update"
"India में नई Policy पर चर्चा"
"Space Mission की नई खबर"

Do not invent facts, numbers, quotes,
details, outcomes, or implications.

Preserve uncertainty in allegations
and predictions.

Return JSON ONLY with these keys:

headline:
Short attention-grabbing factual
Hinglish headline, maximum 90 characters.

point1:
What the headline actually reports,
maximum 105 characters.

point2:
A careful contextual statement.
If details are missing, encourage readers
to consult the original report.
Maximum 105 characters.

caption:
A natural Hinglish Instagram news
caption, maximum 180 characters.

image_scene:
Describe a REALISTIC photographic
editorial visual related to the topic.
Maximum 350 characters.

IMPORTANT FOR image_scene:
It must NOT invent or reenact the
specific reported event.
Use a realistic conceptual photo scene:
technology -> servers or computers
space -> spacecraft or observatory
business -> trading floor or offices
sports -> generic stadium or equipment
politics -> generic government building
entertainment -> cinema or studio
health -> medical laboratory

Avoid identifiable real people and
fake documentary evidence.
No graphic or sexual content.
"""

    for attempt in range(3):
        try:
            result = client.models.generate_content(
                model=TEXT_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    temperature=0.35,
                ),
            )

            data = json.loads(result.text or "{}")

            limits = {
                "headline": 90,
                "point1": 105,
                "point2": 105,
                "caption": 180,
                "image_scene": 350,
            }

            for key, limit in limits.items():
                value = clean(data.get(key))

                if not value or len(value) > limit:
                    raise ValueError(
                        f"Invalid {key}"
                    )

                data[key] = value

            if not re.search(
                r"[\u0900-\u097f]",
                data["headline"]
            ):
                raise ValueError(
                    "Headline must contain Hindi"
                )

            if not re.search(
                r"[A-Za-z]",
                data["headline"]
            ):
                raise ValueError(
                    "Headline must contain English"
                )

            return data

        except Exception as error:
            print(
                "Copy attempt failed:",
                type(error).__name__
            )

            if attempt == 2:
                raise

            time.sleep(2)

    raise RuntimeError("News copy failed")


# ---------------------------------
# REALISTIC AI PHOTO GENERATION
# ---------------------------------

def generate_photo(client, scene, variation):
    prompt = f"""
Create an exceptionally high-quality,
REALISTIC editorial news photograph.

SCENE:
{scene}

VARIATION:
{variation}

Visual direction:
- Photorealistic, not cartoon
- Premium international news magazine
- Realistic physical materials
- Realistic camera perspective
- Professional cinematic lighting
- Rich dark navy and subtle gold accents
- High detail, crisp focus
- Natural colors
- Authentic documentary-style aesthetics
- Landscape composition, 16:9
- Strong focal subject
- Visually striking but believable

ABSOLUTELY NO:
- Text or typography
- Watermarks
- Logos
- Posters
- Infographic elements
- Fake breaking-news banners
- Identifiable real public figures
- Fabricated photographs of the
  specific reported news event
- Nudity or explicit sexual imagery

This is a CONCEPTUAL AI-generated
news visual, not evidence or an actual
photograph of the event.

Make the scene distinct from the other
slide while staying on the same topic.
"""

    last_error = None

    for attempt in range(2):
        try:
            response = client.models.generate_content(
                model=IMAGE_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_modalities=[
                        "IMAGE", "TEXT"
                    ]
                )
            )

            for candidate in response.candidates or []:
                content = getattr(
                    candidate, "content", None
                )

                if content is None:
                    continue

                for part in content.parts or []:
                    inline = getattr(
                        part, "inline_data", None
                    )

                    if inline is None:
                        continue

                    raw = getattr(
                        inline, "data", None
                    )

                    if not raw:
                        continue

                    with Image.open(
                        io.BytesIO(raw)
                    ) as photo:
                        photo.load()
                        return photo.convert("RGB")

            raise RuntimeError(
                "Gemini returned no image"
            )

        except Exception as error:
            last_error = error

            print(
                "Image attempt failed:",
                type(error).__name__,
                str(error)[:160]
            )

            if attempt == 0:
                time.sleep(3)

    raise RuntimeError(
        "Realistic AI photo unavailable. "
        "Post cancelled; no generic fallback. "
        + str(last_error)[:180]
    )


# ---------------------------------
# DESIGN
# ---------------------------------

def base_slide(photo, slide_number):
    canvas = Image.new(
        "RGB", (SIZE, SIZE), NAVY
    )

    draw = ImageDraw.Draw(canvas)

    # Big realistic image area
    image_area = ImageOps.fit(
        photo,
        (1080, 680),
        method=Image.Resampling.LANCZOS,
        centering=(0.5, 0.5)
    )

    canvas.paste(image_area, (0, 0))

    # Dark translucent bottom photo overlay
    overlay = Image.new(
        "RGBA", (1080, 680), (0, 0, 0, 0)
    )

    od = ImageDraw.Draw(overlay)

    for y in range(380, 680):
        alpha = int(
            210 * (y - 380) / 300
        )

        od.line(
            (0, y, 1080, y),
            fill=(5, 11, 24, alpha)
        )

    canvas.paste(
        Image.alpha_composite(
            image_area.convert("RGBA"),
            overlay
        ).convert("RGB"),
        (0, 0)
    )

    draw = ImageDraw.Draw(canvas)

    # Brand bar
    draw.rounded_rectangle(
        (40, 35, 470, 127),
        radius=17,
        fill=NAVY,
        outline=YELLOW,
        width=3
    )

    draw.text(
        (64, 45),
        "FACTZAI",
        font=font(56, True),
        fill=YELLOW
    )

    draw.rounded_rectangle(
        (685, 51, 1035, 108),
        radius=12,
        fill=NAVY
    )

    draw.text(
        (705, 61),
        f"NEWS  /  0{slide_number}",
        font=font(29, True),
        fill=WHITE
    )

    # Clear AI image label
    draw.rounded_rectangle(
        (40, 605, 515, 657),
        radius=10,
        fill=NAVY
    )

    draw.text(
        (57, 615),
        "AI-GENERATED VISUAL",
        font=font(26, True),
        fill=YELLOW
    )

    # Bottom news panel
    draw.rectangle(
        (0, 680, 1080, 1080),
        fill=NAVY
    )

    draw.rectangle(
        (0, 680, 1080, 690),
        fill=YELLOW
    )

    draw.line(
        (48, 1025, 1032, 1025),
        fill=YELLOW,
        width=2
    )

    draw.text(
        (48, 1035),
        "@fac.tzai",
        font=font(23, True),
        fill=YELLOW
    )

    draw.text(
        (825, 1035),
        "FACTZAI NEWS",
        font=font(23, True),
        fill=GREY
    )

    return canvas, draw


def slide_one(news, copy, photo):
    canvas, draw = base_slide(photo, 1)

    category = clean(
        news["category"]
    ).upper()

    fit_text(
        draw,
        category,
        48, 708,
        980, 45,
        max_font=29,
        min_font=22,
        fill=YELLOW
    )

    fit_text(
        draw,
        copy["headline"],
        48, 767,
        975, 205,
        max_font=57,
        min_font=29,
        fill=WHITE
    )

    return canvas


def slide_two(news, copy, photo):
    canvas, draw = base_slide(photo, 2)

    fit_text(
        draw,
        "NEWS EXPLAINED",
        48, 708,
        980, 45,
        max_font=30,
        min_font=23,
        fill=YELLOW
    )

    fit_text(
        draw,
        "01  " + copy["point1"],
        48, 770,
        975, 95,
        max_font=34,
        min_font=23,
        fill=WHITE
    )

    fit_text(
        draw,
        "02  " + copy["point2"],
        48, 883,
        975, 105,
        max_font=34,
        min_font=23,
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

    if os.getenv(
        "ENABLE_AI_IMAGE", "true"
    ).lower() != "true":
        raise RuntimeError(
            "AI images disabled. "
            "Post cancelled."
        )

    news = load_news()

    print(
        "FACTZAI news:",
        news["title"]
    )

    client = genai.Client(
        api_key=API_KEY
    )

    copy = create_copy(
        client, news
    )

    print(
        "Generating realistic AI photo 1..."
    )

    photo1 = generate_photo(
        client,
        copy["image_scene"],
        (
            "Wide establishing shot, "
            "dramatic composition, "
            "premium editorial cover."
        )
    )

    print(
        "Generating realistic AI photo 2..."
    )

    photo2 = generate_photo(
        client,
        copy["image_scene"],
        (
            "Closer alternate camera angle, "
            "different composition, "
            "professional editorial detail."
        )
    )

    first = slide_one(
        news, copy, photo1
    )

    second = slide_two(
        news, copy, photo2
    )

    OUT.mkdir(
        parents=True,
        exist_ok=True
    )

    first.save(
        OUT / "slide_1.jpg",
        "JPEG",
        quality=95,
        subsampling=0
    )

    second.save(
        OUT / "slide_2.jpg",
        "JPEG",
        quality=95,
        subsampling=0
    )

    published = datetime.fromisoformat(
        news["published_utc"].replace(
            "Z", "+00:00"
        )
    )

    date_text = published.strftime(
        "%d %b %Y"
    )

    caption = (
        copy["caption"]
        + "\n\n"
        + "📰 Source: "
        + clean(news["source"])
        + "\n"
        + "📅 "
        + date_text
        + "\n"
        + "🔗 "
        + clean(news["url"])
        + "\n\n"
        + "🎨 Images: AI-generated "
        + "conceptual visuals, not actual "
        + "photos of the news event."
        + "\n"
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
        news["id"],
        encoding="utf-8"
    )

    print(
        "SUCCESS: 2 realistic AI "
        "news carousel slides created"
    )


if __name__ == "__main__":
    main()
