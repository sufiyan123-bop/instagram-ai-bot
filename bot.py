
"""FACTZAI: free licensed real-photo Instagram carousel.
Outputs output/slide_1.jpg, slide_2.jpg, caption.txt, news_id.txt.
Real illustrative photos are not presented as documentation of a news event.
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
from PIL import Image, ImageDraw, ImageFont, ImageOps, features

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'output'
SIZE = 1080
NAVY = (8, 15, 31)
YELLOW = (255, 211, 45)
WHITE = (250, 251, 253)
GREY = (191, 200, 213)
API_KEY = os.getenv('GEMINI_API_KEY', '').strip()
TEXT_MODEL = os.getenv('GEMINI_MODEL', 'gemini-3.5-flash-lite')
COMMONS = 'https://commons.wikimedia.org/w/api.php'
HEADERS = {'User-Agent': 'FACTZAI-NewsCarousel/1.0 (contact: @fac.tzai on Instagram)'}

CATEGORY_SEARCH = {
    'india': 'India skyline city', 'world': 'world city skyline',
    'politics': 'parliament building', 'technology': 'data center servers',
    'science': 'research laboratory', 'space': 'space telescope observatory',
    'business': 'financial district skyscrapers', 'sports': 'sports stadium',
    'entertainment': 'cinema film camera', 'health': 'medical laboratory',
    'education': 'university library', 'cybersecurity': 'server racks',
    'environment': 'forest landscape', 'adult industry': 'film production studio',
}

def clean(value):
    return re.sub(r'\s+', ' ', str(value or '')).strip()

def meta(value):
    return clean(html.unescape(re.sub(r'<[^>]*>', ' ', str(value or ''))))

def get_font(size, bold=False):
    paths = [
        '/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf',
        '/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf',
    ]
    for path in paths:
        if Path(path).is_file():
            return ImageFont.truetype(path, size)
    try:
        path = subprocess.check_output(
            ['fc-match', '-f', '%{file}', 'Noto Sans Devanagari'],
            text=True, timeout=8).strip()
        if 'Devanagari' in path and Path(path).is_file():
            return ImageFont.truetype(path, size)
    except Exception:
        pass
    path = Path(tempfile.gettempdir()) / 'factzai_noto_devanagari.ttf'
    if not path.is_file():
        url = ('https://raw.githubusercontent.com/google/fonts/main/ofl/'
               'notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf')
        response = requests.get(url, timeout=40)
        response.raise_for_status()
        path.write_bytes(response.content)
    return ImageFont.truetype(str(path), size)

def wrap(draw, value, font, width):
    result, current = [], ''
    for word in clean(value).split():
        candidate = (current + ' ' + word).strip()
        if draw.textbbox((0, 0), candidate, font=font)[2] <= width:
            current = candidate
        else:
            if current:
                result.append(current)
            current = word
    if current:
        result.append(current)
    return result

def draw_fitted(draw, value, x, y, width, height, biggest=56, smallest=23, fill=WHITE):
    for size in range(biggest, smallest - 1, -2):
        f = get_font(size, True)
        lines = wrap(draw, value, f, width)
        step = int(size * 1.48)
        if lines and len(lines) * step <= height and all(
            draw.textbbox((0, 0), line, font=f)[2] <= width for line in lines
        ):
            for line in lines:
                draw.text((x, y), line, font=f, fill=fill)
                y += step
            return
    raise RuntimeError('Text does not fit: ' + clean(value)[:80])

def load_news():
    path = ROOT / 'latest_news.json'
    if not path.exists():
        raise RuntimeError('latest_news.json missing')
    news = json.loads(path.read_text(encoding='utf-8'))
    for key in ('id', 'title', 'source', 'url', 'category', 'published_utc'):
        if not clean(news.get(key)):
            raise RuntimeError('News missing: ' + key)
    published = datetime.fromisoformat(news['published_utc'].replace('Z', '+00:00'))
    if published.tzinfo is None:
        published = published.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - published.astimezone(timezone.utc)).total_seconds() / 3600
    if not -0.1 <= age <= 24:
        raise RuntimeError('News must be from the last 24 hours')
    return news, published

def create_copy(client, news):
    prompt = f'''You write FACTZAI Indian Instagram news copy. You know ONLY the RSS headline,
not the article body. Headline: {news['title']}
Source: {news['source']}; Category: {news['category']}.
Return only JSON with keys headline, point1, point2, caption.
headline <= 88 chars, point1 <= 100, point2 <= 100, caption <= 170.
Write natural Hinglish, mixing Hindi Devanagari and English in the headline.
Avoid all-Hindi and all-English headlines. Keep short and easy to read.
Do not invent numbers, facts, quotes or outcomes. If details are missing,
point2 should say to read the original report for more context.
No sensational or misleading claims. Preserve uncertainty.'''
    last = None
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model=TEXT_MODEL, contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type='application/json', temperature=0.3))
            data = json.loads(response.text or '{}')
            for key, limit in {'headline': 88, 'point1': 100,
                               'point2': 100, 'caption': 170}.items():
                data[key] = clean(data.get(key))
                if not data[key] or len(data[key]) > limit:
                    raise ValueError('Invalid news copy: ' + key)
            if not re.search('[\u0900-\u097f]', data['headline']) or not re.search('[A-Za-z]', data['headline']):
                raise ValueError('Headline must mix Hindi and English')
            return data
        except Exception as error:
            last = error
            print('Text generation attempt:', attempt + 1, type(error).__name__, str(error)[:120])
            if attempt < 2:
                time.sleep(3)
    raise RuntimeError('News text generation failed: ' + str(last)[:180])

def search_commons(query):
    params = {
        'action': 'query', 'format': 'json', 'generator': 'search',
        'gsrsearch': query + ' filetype:bitmap', 'gsrnamespace': 6,
        'gsrlimit': 35, 'prop': 'imageinfo',
        'iiprop': 'url|size|extmetadata', 'iiurlwidth': 1600,
    }
    response = requests.get(COMMONS, params=params, headers=HEADERS, timeout=35)
    response.raise_for_status()
    pages = response.json().get('query', {}).get('pages', {})
    for page in pages.values():
        title = page.get('title', '')
        if not title.lower().endswith(('.jpg', '.jpeg', '.png')):
            continue
        info = (page.get('imageinfo') or [{}])[0]
        if int(info.get('width') or 0) < 850 or int(info.get('height') or 0) < 550:
            continue
        fields = info.get('extmetadata') or {}
        license_name = meta((fields.get('LicenseShortName') or {}).get('value'))
        normalized = license_name.lower().replace(' ', '')
        allowed = (normalized.startswith('ccby-') or normalized.startswith('ccby-sa-')
                   or normalized in ('cc0', 'publicdomain', 'pd'))
        if not allowed:
            continue
        url = info.get('thumburl') or info.get('url')
        page_url = info.get('descriptionurl')
        if not url or not page_url:
            continue
        yield {
            'url': url, 'page': page_url, 'title': title,
            'license': license_name,
            'author': meta((fields.get('Artist') or {}).get('value'))[:180]
                      or 'Wikimedia Commons contributor',
        }

def get_photos(news):
    category = clean(news['category']).lower()
    term = CATEGORY_SEARCH.get(category, 'city skyline architecture')
    queries = [term, term.split()[0] + ' photography', 'modern city skyline']
    photos, seen = [], set()
    for query in queries:
        try:
            for item in search_commons(query):
                if item['page'] in seen:
                    continue
                try:
                    result = requests.get(item['url'], headers=HEADERS, timeout=40)
                    result.raise_for_status()
                    img = Image.open(io.BytesIO(result.content))
                    img.load()
                    if img.width < 800 or img.height < 500:
                        continue
                    photos.append((img.convert('RGB'), item))
                    seen.add(item['page'])
                    print('Photo selected:', item['title'], item['license'])
                    if len(photos) == 2:
                        return photos
                except Exception as error:
                    print('Skipping image:', type(error).__name__)
        except Exception as error:
            print('Wikimedia search problem:', type(error).__name__, str(error)[:120])
    raise RuntimeError('Two licensed photographs unavailable; skipping post safely')

def base_slide(photo, index):
    canvas = Image.new('RGB', (SIZE, SIZE), NAVY)
    photo = ImageOps.fit(photo, (1080, 680), method=Image.Resampling.LANCZOS)
    canvas.paste(photo, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((38, 36, 430, 123), radius=16, fill=NAVY,
                           outline=YELLOW, width=3)
    draw.text((63, 46), 'FACTZAI', font=get_font(55, True), fill=YELLOW)
    draw.rounded_rectangle((750, 48, 1034, 108), radius=12, fill=NAVY)
    draw.text((770, 60), f'NEWS / 0{index}', font=get_font(29, True), fill=WHITE)
    draw.rounded_rectangle((40, 609, 470, 660), radius=10, fill=NAVY)
    draw.text((57, 619), 'REAL PHOTO / COMMONS', font=get_font(24, True), fill=YELLOW)
    draw.rectangle((0, 680, 1080, 1080), fill=NAVY)
    draw.rectangle((0, 680, 1080, 689), fill=YELLOW)
    draw.line((48, 1025, 1032, 1025), fill=YELLOW, width=2)
    draw.text((48, 1036), '@fac.tzai', font=get_font(24, True), fill=YELLOW)
    draw.text((815, 1036), 'FACTZAI NEWS', font=get_font(23, True), fill=GREY)
    return canvas, draw

def make_slide_one(news, copy, photo):
    canvas, draw = base_slide(photo, 1)
    draw_fitted(draw, clean(news['category']).upper(), 48, 710, 980, 48,
                biggest=30, smallest=22, fill=YELLOW)
    draw_fitted(draw, copy['headline'], 48, 765, 980, 225,
                biggest=61, smallest=29)
    return canvas

def make_slide_two(copy, photo):
    canvas, draw = base_slide(photo, 2)
    draw_fitted(draw, 'NEWS EXPLAINED', 48, 710, 980, 45,
                biggest=30, smallest=23, fill=YELLOW)
    draw_fitted(draw, '01  ' + copy['point1'], 48, 770, 980, 100,
                biggest=36, smallest=22)
    draw_fitted(draw, '02  ' + copy['point2'], 48, 890, 980, 105,
                biggest=36, smallest=22)
    return canvas

def main():
    if not API_KEY:
        raise RuntimeError('GEMINI_API_KEY missing')
    if not features.check('raqm'):
        raise RuntimeError('Pillow libraqm is required for correct Hindi text rendering')
    news, published = load_news()
    print('FACTZAI headline:', news['title'])
    client = genai.Client(api_key=API_KEY)
    copy = create_copy(client, news)
    print('Finding openly licensed real photos (no Gemini image API)...')
    (photo1, credit1), (photo2, credit2) = get_photos(news)
    first = make_slide_one(news, copy, photo1)
    second = make_slide_two(copy, photo2)
    OUT.mkdir(parents=True, exist_ok=True)
    first.save(OUT / 'slide_1.jpg', 'JPEG', quality=94, subsampling=0)
    second.save(OUT / 'slide_2.jpg', 'JPEG', quality=94, subsampling=0)
    caption = (
        copy['caption'] + '\n\n'
        + '📰 Source: ' + clean(news['source']) + '\n'
        + '📅 ' + published.strftime('%d %b %Y') + '\n'
        + '🔗 ' + clean(news['url']) + '\n\n'
        + '📷 Illustrative real photos, not verified images of this event.\n'
        + 'Photo 1: ' + credit1['author'] + ' | ' + credit1['license'] + '\n'
        + credit1['page'] + '\n'
        + 'Photo 2: ' + credit2['author'] + ' | ' + credit2['license'] + '\n'
        + credit2['page'] + '\n'
        + 'AI-assisted summary based on RSS headline metadata. '
        + 'Read original reporting for complete context.\n\n'
        + '#FACTZAI #LatestNews #HinglishNews #NewsUpdate'
    )
    (OUT / 'caption.txt').write_text(caption, encoding='utf-8')
    (OUT / 'news_id.txt').write_text(clean(news['id']), encoding='utf-8')
    print('SUCCESS: two free licensed-photo FACTZAI slides created')

if __name__ == '__main__':
    main()
