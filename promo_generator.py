"""Render a numbered promotional image using the uploaded original poster.

Required input: assets/youtube_automation_promo.png
Output: output/promo_post.jpg and output/caption.txt
"""
from pathlib import Path
import os
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent
ASSETS = [ROOT / "assets" / "youtube_automation_promo.png", ROOT / "assets" / "youtube_automation_promo.jpg", ROOT / "assets" / "youtube_automation_promo.jpeg"]
OUTPUT = ROOT / "output"
COUNTER = ROOT / "post_counter.txt"

CAPTION = """🚀 COMPUTER COURSES – 100% FREE! 🎓

🔥 अब सीखना हुआ और भी आसान!

क्या आप Computer Skills सीखना चाहते हैं, लेकिन महंगे Courses खरीदने के पैसे नहीं हैं? 😍

तो आपके लिए खुशखबरी है! ❤️

💻 अब पाएं Computer के ढेरों Courses बिल्कुल FREE में!

📚 यहाँ आपको मिलेंगे:

✅ Basic Computer Course
✅ Advanced Computer Course
✅ MS Word, Excel & PowerPoint
✅ Graphic Designing
✅ Web Development
✅ Programming & Coding
✅ Tally & Accounting
✅ Digital Marketing
✅ Video Editing
✅ Cyber Security
✅ और भी बहुत कुछ! 🔥

🎯 हमारा मकसद: हर किसी तक Quality Education पहुँचाना, वो भी बिल्कुल FREE में!

💯 No Course Fees
📚 Learn New Skills
🚀 Improve Your Knowledge
🎓 Build Your Future

👇 JOIN OUR TELEGRAM CHANNEL NOW!

🔗 Telegram: [अपना Telegram Link यहाँ डालें]

❤️ सीखना शुरू करो, आगे बढ़ना शुरू करो!

📢 इस पोस्ट को अपने दोस्तों के साथ भी SHARE करें!

#FreeCourses #ComputerCourses #FreeEducation #LearnSkills #OnlineLearning #ComputerEducation
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
    asset = next((path for path in ASSETS if path.is_file()), None)
    if asset is None:
        raise RuntimeError(
            "Missing promotional image. Upload the provided YouTube Automation image "
            "as assets/youtube_automation_promo.png in GitHub."
        )
    previous = 0
    if COUNTER.exists():
        previous = int(COUNTER.read_text(encoding="utf-8").strip())
    number = previous + 1

    canvas = Image.open(asset).convert("RGB")
    if min(canvas.size) < 320:
        raise RuntimeError("Promotional image is too small (minimum 320px on each side).")
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
