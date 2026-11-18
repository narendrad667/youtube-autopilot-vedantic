"""The TWO images for a Vedantic Psychology video — both AI-generated.

Unlike the live What If pipeline (52 photos/video), this channel uses
exactly two images per video, like BookPeak:
  (a) book visual — one calm cinematic image that stays on screen for the
      whole video (the "static book cover" of the format);
  (b) thumbnail visual — one dramatic image used as the thumbnail base.

Primary: Pollinations (image.pollinations.ai, free, no key, FLUX).
  It 402s/503s from GitHub Actions runners sometimes, so each image gets
  up to 2 tries (different seeds). Pollinations stamps a small
  "pollinations.ai" logo bottom-right even with nologo=true, so its
  images have the bottom 7% cropped off with Pillow (same fix as live).
Fallback: Openverse (api.openverse.org, free, no key) — real CC photos.

Never-fail rule: if every source fails for one image, the most recent
successfully downloaded image is reused for that slot instead of killing
the whole video — one bad image must never waste a run.
"""
import hashlib
import json
import os
import shutil
import time
import urllib.request
import urllib.error

POLLINATIONS_URL = ("https://image.pollinations.ai/prompt/{prompt}"
                    "?width=1024&height=576&model=flux&seed={seed}&nologo=true")
OPENVERSE_URL = ("https://api.openverse.org/v1/images/?q={q}&page_size=5"
                 "&license_type=commercial&filter_dead=false")
USER_AGENT = "VedanticPsychology-YT-Autopilot/1.0"
OPENVERSE_PACE_S = 1
# Generic queries tried when no image has succeeded yet at all.
GENERIC_QUERIES = ["old books library", "meditation sunrise mountains",
                   "indian temple golden light"]


def _seed(prompt):
    return int(hashlib.md5(prompt.encode("utf-8")).hexdigest()[:8], 16) % 100000


def _crop_watermark(path):
    """Crop the bottom 7% off an image (removes the Pollinations logo
    stamped at the bottom-right). No-op if Pillow cannot read the file."""
    try:
        from PIL import Image
        img = Image.open(path).convert("RGB")
        w, h = img.size
        img.crop((0, 0, w, int(h * 0.93))).save(path, "JPEG", quality=90)
    except Exception as e:
        print("Watermark crop skipped (%s)" % e)


def _valid_image(path, min_bytes=5000):
    """True if the file is a readable image of reasonable size."""
    if not os.path.exists(path) or os.path.getsize(path) < min_bytes:
        return False
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.verify()
        return True
    except Exception:
        return False


def _is_landscape(path):
    try:
        from PIL import Image
        with Image.open(path) as img:
            return img.size[0] >= img.size[1]
    except Exception:
        return False


def fetch_pollinations(prompt, out_path, seed_offset=0, timeout=120):
    """Download one Pollinations image. One try, no retries. True on success."""
    url = POLLINATIONS_URL.format(
        prompt=urllib.parse.quote(prompt + ", cinematic, 16:9, no text, "
                                  "no words, no letters, no watermark"),
        seed=(_seed(prompt) + seed_offset) % 100000)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read()
        ctype = resp.headers.get("Content-Type", "")
        if resp.status != 200 or not ctype.startswith("image/"):
            print("Pollinations bad reply: %s %s" % (resp.status, ctype))
            return False
        if len(data) < 5000:
            print("Pollinations image too small (%d bytes)" % len(data))
            return False
        with open(out_path, "wb") as f:
            f.write(data)
        _crop_watermark(out_path)
        return True
    except Exception as e:
        print("Pollinations failed: %s" % e)
        return False


def fetch_openverse(query, out_path, timeout=60):
    """Download a CC photo from Openverse (no key). Prefers a landscape
    photo; falls back to the first usable result. True on success."""
    url = OPENVERSE_URL.format(q=urllib.parse.quote(query))
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        results = data.get("results") or []
        first_good = None
        tried = 0
        for item in results:
            if tried >= 3:
                break
            img_url = item.get("url")
            if not img_url:
                continue
            tried += 1
            try:
                req2 = urllib.request.Request(
                    img_url, headers={"User-Agent": USER_AGENT})
                with urllib.request.urlopen(req2, timeout=timeout) as resp2:
                    blob = resp2.read()
                    ctype = resp2.headers.get("Content-Type", "")
                if resp2.status != 200 or not ctype.startswith("image/") \
                        or len(blob) <= 5000:
                    continue
                tmp = out_path + ".ov"
                with open(tmp, "wb") as f:
                    f.write(blob)
                if not _valid_image(tmp):
                    os.remove(tmp)
                    continue
                if first_good is None:
                    first_good = tmp
                if _is_landscape(tmp):
                    os.replace(tmp, out_path)
                    if first_good != tmp and os.path.exists(first_good):
                        os.remove(first_good)
                    return True
            except Exception:
                continue
        if first_good is not None:
            os.replace(first_good, out_path)
            return True
        return False
    except Exception as e:
        print("Openverse failed: %s" % e)
        return False


def _query_variants(prompt):
    """Short keyword queries for a photo search, from an AI image prompt."""
    words = [w.strip(".,;:!?()\"'") for w in prompt.split()]
    words = [w for w in words if w and w.lower() not in
             ("a", "an", "the", "of", "in", "on", "with", "and")]
    variants = []
    if len(words) >= 4:
        variants.append(" ".join(words[:4]))
    if len(words) >= 2:
        variants.append(" ".join(words[:2]))
    return variants


def fetch_image(prompt, out_path, last_good=None):
    """Fetch one image: Pollinations (2 seed tries), then Openverse.
    Falls back to reusing last_good. Returns (ok, engine)."""
    for offset in (0, 1):
        if fetch_pollinations(prompt, out_path, seed_offset=offset):
            return True, "pollinations"
        time.sleep(2)
    for query in _query_variants(prompt):
        if fetch_openverse(query, out_path):
            return True, "openverse"
        time.sleep(OPENVERSE_PACE_S)
    if last_good is None:
        for gq in GENERIC_QUERIES:
            if fetch_openverse(gq, out_path):
                return True, "openverse-generic"
    if last_good is not None and os.path.exists(last_good):
        shutil.copyfile(last_good, out_path)
        return True, "reuse"
    return False, "none"


def fetch_video_images(script, out_dir, last_good=None):
    """Fetch the two images for one video. script carries the AI prompts
    from script_gen ("book_visual_prompt", "thumbnail_prompt"); if they
    are missing, generic book-themed prompts are built from the title.
    Returns {"book": path, "thumbnail": path}."""
    os.makedirs(out_dir, exist_ok=True)
    book_prompt = script.get("book_visual_prompt") or (
        "cinematic illustration, an open ancient book glowing softly on a "
        "wooden table, warm candle light, peaceful library, misty morning")
    thumb_prompt = script.get("thumbnail_prompt") or (
        "dramatic cinematic illustration, a person meditating on a mountain "
        "peak at sunrise, golden light breaking through clouds")
    book_path = os.path.join(out_dir, "book_visual.jpg")
    ok, engine = fetch_image(book_prompt, book_path, last_good)
    if not ok:
        raise RuntimeError("Book visual failed — no source returned an image")
    print("Book visual: %s" % engine)
    last_good = book_path
    thumb_path = os.path.join(out_dir, "thumbnail_visual.jpg")
    ok, engine = fetch_image(thumb_prompt, thumb_path, last_good)
    if not ok:
        raise RuntimeError("Thumbnail visual failed — no source returned an image")
    print("Thumbnail visual: %s" % engine)
    return {"book": book_path, "thumbnail": thumb_path}


if __name__ == "__main__":
    result = fetch_video_images(
        {"book_visual_prompt": "cinematic illustration, an open ancient book "
         "glowing softly, warm light, peaceful",
         "thumbnail_prompt": "dramatic cinematic illustration, meditating "
         "monk at sunrise on a mountain peak"},
        "/tmp/vp_images")
    print(result)
