"""Instagram facts: generate a 2-image SIMPLE ENGLISH carousel preview.

Step 4 is PREVIEW ONLY: this script does not post to Instagram.
Works on GitHub Actions with GEMINI_API_KEY stored in repository Actions secrets.
"""
from __future__ import annotations

import json
import os
import random
from pathlib import Path
from urllib.parse import quote

import requests
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types

ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "output"
MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")
BRAND = os.getenv("BRAND_NAME", "FACT DAILY")[:20].upper()

# Simple, evergreen science/nature/space subjects. Topic selection is random.
TOPICS = [
    "Octopus", "Honey bee", "Venus", "Jupiter", "Saturn", "Mars",
    "Great Barrier Reef", "Antarctica", "Hummingbird", "Koala",
    "Blue whale", "Giant panda", "Lightning", "Solar eclipse",
    "Aurora", "Volcano", "Giraffe", "Dolphin", "Penguin",
    "Red panda", "Elephant", "Chameleon", "Axolotl", "Coral reef",
    "Baobab", "Mount Everest", "Moon", "Neptune", "Red fox", "Owl",
]

HTTP = requests.Session()
HTTP.headers.update({"User-Agent": "KnowledgeFactsPreview/1.0 (learning-project; GitHub Actions)"})


def get_verified_source():
    """Choose a topic with a real Wikipedia text excerpt and link."""
    candidates = random.sample(TOPICS, len(TOPICS))
    for name in candidates[:12]:
        url = "https://en.wikipedia.org/api/rest_v1/page/summary/" + quote(name.replace(" ", "_"))
        try:
            res = HTTP.get(url, timeout=22, headers={"Accept": "application/json"})
            res.raise_for_status()
            data = res.json()
            extract = (data.get("extract") or "").strip()
            if len(extract) < 180 or data.get("type") == "disambiguation":
                continue
            source = data.get("content_urls", {}).get("desktop", {}).get("page", url)
            return data.get("title", name), extract[:2500], source
        except (requests.RequestException, ValueError):
            continue
    raise RuntimeError("Could not load a Wikipedia source. Retry the workflow later.")


def generate_english_copy(title, extract, source):
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not key:
        raise RuntimeError("GEMINI_API_KEY secret missing. Check Step 3.")

    prompt = f"""
Write ONE premium educational Instagram carousel in VERY SIMPLE ENGLISH.
Only use facts clearly supported by the quoted Wikipedia excerpt below.
NEVER invent numbers, dates, dramatic claims, or extra facts.
Use words easy for a 10-year-old to understand; explain unusual words.
Make it genuinely useful and interesting. Short sentences and no filler.
JSON ONLY. Four string keys:
- hook: a short curious title, 10 to 48 characters, easy words
- fact: one correct and surprising fact, 25 to 145 characters
- explanation: 2-3 simple sentences explaining it, 70 to 260 characters
- caption: a short friendly 1-2 sentence caption, 25 to 220 characters
Do not add hashtags or URLs to any JSON fields.
Topic: {title}
Source URL: {source}
Source excerpt: {extract}
"""
    ai = genai.Client(api_key=key)
    response = ai.models.generate_content(
        model=MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            temperature=0.2,
            response_mime_type="application/json",
        ),
    )
    if not response.text:
        raise RuntimeError("AI returned no text. Check model or free-tier quota.")
    try:
        info = json.loads(response.text)
    except ValueError as exc:
        raise RuntimeError("AI text is not valid JSON. Please retry.") from exc
    constraints = {"hook": (10, 48), "fact": (25, 145),
                   "explanation": (70, 260), "caption": (25, 220)}
    for field, (low, high) in constraints.items():
        value = str(info.get(field, "")).strip()
        if not (low <= len(value) <= high):
            raise RuntimeError(f"AI returned an invalid {field} length. Please retry.")
        info[field] = value
    return info


def font(size, bold=False):
    font_path = ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
                 else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    return ImageFont.truetype(font_path, size)


def break_lines(draw, content, use_font, max_width):
    chunks, line = [], ""
    for word in content.split():
        candidate = (line + " " + word).strip()
        bbox = draw.textbbox((0, 0), candidate, font=use_font)
        if bbox[2] <= max_width:
            line = candidate
        else:
            if line:
                chunks.append(line)
            line = word
    if line:
        chunks.append(line)
    return chunks


def write_block(draw, content, area, start_size, color, bold=False, max_lines=9):
    left, top, right, bottom = area
    for size in range(start_size, 27, -2):
        face = font(size, bold)
        lines = break_lines(draw, content, face, right - left)
        space = int(size * 1.35)
        if len(lines) <= max_lines and top + len(lines) * space <= bottom:
            for index, text in enumerate(lines):
                draw.text((left, top + index * space), text, font=face, fill=color)
            return
    raise ValueError("Fact text does not fit the slide. Re-run for a fresh fact.")


def draw_slide(position, topic, text):
    """Make readable 1080x1350 original JPG designs without paid image AI."""
    dark = (11, 21, 39) if position == 1 else (19, 29, 51)
    accent = (104, 245, 208) if position == 1 else (255, 202, 112)
    cream = (244, 249, 255)
    canvas = Image.new("RGB", (1080, 1350), dark)
    d = ImageDraw.Draw(canvas)
    for radius in (255, 332, 418):
        cx, cy = 940, 160 if position == 1 else 270
        d.ellipse((cx-radius, cy-radius, cx+radius, cy+radius),
                  outline=tuple(int(x * 0.35) for x in accent), width=3)
    d.rounded_rectangle((54, 58, 1026, 1295), radius=34, outline=(91, 107, 129), width=3)
    d.rounded_rectangle((90, 95, 385, 161), radius=16, fill=accent)
    d.text((112, 113), "KNOWLEDGE / DAILY", font=font(24, True), fill=dark)
    d.text((90, 223), "DID YOU KNOW?" if position == 1 else "LEARN MORE",
           font=font(36, True), fill=accent)

    if position == 1:
        write_block(d, text["hook"], (90, 335, 980, 545), 72, cream, True, 3)
        d.rounded_rectangle((90, 603, 983, 616), radius=6, fill=accent)
        write_block(d, text["fact"], (90, 710, 985, 1095), 66, cream, False, 7)
        d.text((90, 1163), "SWIPE  >>>", font=font(37, True), fill=accent)
    else:
        write_block(d, topic.upper(), (90, 330, 985, 490), 54, cream, True, 3)
        d.rounded_rectangle((90, 521, 983, 534), radius=6, fill=accent)
        write_block(d, text["explanation"], (90, 615, 985, 1060), 58, cream, False, 8)
        d.text((90, 1141), "SOURCE LINK IN CAPTION", font=font(26, True), fill=accent)

    d.text((90, 1244), f"{BRAND}    |    {position} / 2", font=font(26, True),
           fill=(175, 193, 217))
    OUTPUT.mkdir(parents=True, exist_ok=True)
    destination = OUTPUT / f"slide_{position}.jpg"
    canvas.save(destination, format="JPEG", quality=90, optimize=True)
    return destination


def main():
    print("Creating a preview only. Nothing will be posted to Instagram.")
    topic, excerpt, url = get_verified_source()
    copy = generate_english_copy(topic, excerpt, url)
    first = draw_slide(1, topic, copy)
    second = draw_slide(2, topic, copy)
    caption = f"{copy['caption']}\n\nSource: {url}\n\n#AmazingFacts #LearnSomethingNew #Knowledge"
    (OUTPUT / "caption.txt").write_text(caption, encoding="utf-8")
    (OUTPUT / "source_excerpt.txt").write_text(
        f"TOPIC: {topic}\nSOURCE: {url}\n\nWIKIPEDIA EXCERPT:\n{excerpt}\n",
        encoding="utf-8",
    )
    print("SUCCESS: Created", first.name, "and", second.name)
    print("Check the preview and source before posting. AI can make mistakes.")


if __name__ == "__main__":
    main()
