"""Render a numbered promotional image using the uploaded original poster.

Required input: assets/youtube_automation_promo.png
Output: output/promo_post.jpg and output/caption.txt
"""
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ASSET = ROOT / "assets" / "youtube_automation_promo.png"
OUTPUT = ROOT / "output"
COUNTER = ROOT / "post_counter.txt"

CAPTION = """🚀 YOUTUBE AUTOMATION — ₹100 / MONTH!

Ek baar apna niche aur posting time set karo. Hamara automation workflow:
✅ Niche-wise script banane ka system
✅ Automatic voice generation
✅ Animated YouTube Shorts creation
✅ YouTube par upload aur scheduled publishing
✅ Mobile-friendly setup

🎯 Setup instructions, real demo aur availability updates ke liye WhatsApp Channel JOIN KARO!
📲 WhatsApp Channel link: BIO MEIN

⚠️ Project development / testing mein hai. Final features aur service launch demo ke baad confirm honge.

#YouTubeAutomation #YouTubeShorts #AIShorts #YouTubeTools #ContentAutomation
"""

def get_font(size):
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
    ]
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()

def main():
    if not ASSET.exists():
        raise RuntimeError(
            "Missing promotional image. Upload the provided YouTube Automation image "
            "as assets/youtube_automation_promo.png in GitHub."
        )
    previous = 0
    if COUNTER.exists():
        previous = int(COUNTER.read_text(encoding="utf-8").strip())
    number = previous + 1

    canvas = Image.open(ASSET).convert("RGB")
    w, h = canvas.size
    draw = ImageDraw.Draw(canvas)
    label = f"POST {number}"
    size = max(30, w // 19)
    font = get_font(size)
    bounds = draw.textbbox((0, 0), label, font=font)
    tw, th = bounds[2] - bounds[0], bounds[3] - bounds[1]
    pad = max(16, w // 56)
    x, y = w - tw - pad * 3, pad
    draw.rounded_rectangle(
        (x - pad, y - pad // 2, x + tw + pad, y + th + pad),
        radius=max(8, pad // 2),
        fill=(7, 10, 22),
        outline=(255, 210, 35),
        width=max(3, w // 300),
    )
    draw.text((x, y), label, font=font, fill=(255, 226, 51))

    OUTPUT.mkdir(exist_ok=True)
    canvas.save(OUTPUT / "promo_post.jpg", "JPEG", quality=91, optimize=True)
    (OUTPUT / "caption.txt").write_text(CAPTION, encoding="utf-8")
    (OUTPUT / "post_number.txt").write_text(str(number), encoding="utf-8")
    print(f"Created promo POST {number}")

if __name__ == "__main__":
    main()
