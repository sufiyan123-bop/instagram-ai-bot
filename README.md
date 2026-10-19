# YouTube Automation Promo → Instagram

This repository's active publishing workflow is **YouTube Automation Promo Instagram Publisher** (`.github/workflows/post_test.yml`). The old FACTZAI news scripts and workflows have been removed. Only the promo publishing workflow is active.

## One-time setup (required before first run)

1. Save the promotional image received in ChatGPT as a PNG or JPG.
2. On GitHub, open this repository and upload that *exact image* at `assets/youtube_automation_promo.png` (or `.jpg` / `.jpeg`) (create `assets/` when prompted). Commit the file on `main`.
3. In GitHub repository **Settings → Secrets and variables → Actions**, make sure `IG_ACCESS_TOKEN` is present and is a valid Instagram Professional account publishing token. **Never put it in source code.**
4. Go to **Actions → YouTube Automation Promo Instagram Publisher → Run workflow**. Choose **no** to only generate preview (download artifact `youtube-promo-preview`).
5. Check the image/caption. To make **one real post**, run workflow again and choose **yes**.
6. The schedule is **07:00, 10:00, 13:00, 16:00, 19:00 and 22:00 IST** (6 posts/day). GitHub Actions cron is best-effort, not exact. To stop, disable the workflow in the GitHub Actions UI.

## What it does

- Reads the one original uploaded image every time.
- Draws a prominent `POST 1`, `POST 2`, `POST 3`, ... number at upper-right.
- Uses a reusable caption advertising the **₹100/month YouTube automation project** and directing visitors to **WhatsApp Channel link in bio**.
- Produces a public JPEG in `posts/promo-<run-id>-<attempt>/promo_post.jpg` (required by Meta to fetch photo).
- Publishes one standard Instagram image post using the official Instagram Login API.
- Only after publish returns success, saves the next counter in `post_counter.txt`.
- Uses the existing quota guard and serializes runs to avoid parallel publishing.

## Notes / limitations

- This intentionally does **not** automatically repost the same ad every 18 minutes. Repeated near-identical posts can trigger spam restrictions and hurt account health. Use the daily schedule, and vary creatives based on results.
- Requires a public GitHub repository so Instagram can fetch the hosted photo; there is no secret token in the public image.
- Requires Instagram Professional account, valid permissions and Meta API access.
- The workflow will **fail safely** if `assets/youtube_automation_promo.png` is missing; it will not silently publish a different image.
- Numbering is per *confirmed API publish call*, but if GitHub loses connectivity immediately after publishing and before recording the counter, the counter may not advance. Check Instagram after any failed run before manually retrying.
- The promotion should not imply the YouTube automation product is already fully released if it is still in development.
