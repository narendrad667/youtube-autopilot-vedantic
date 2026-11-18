"""One-video orchestrator for the Vedantic Psychology autopilot.

Usage: python run_one.py <job_index 0..N-1> [work_dir]
  - Book: deterministic rotation from books.json (date-based slot, so
    every day's videos cover different books; after the 50-book pool
    cycles, it starts again from the top).
  - Gemini writes a Hindi book-summary script (super hook + 6 chapters,
    1500+ words, ~10-12 min).
  - Gemini native TTS voice "Charon" (user-approved 2026-11-18; clear,
    calm, steady style on every request), fallback Edge
    hi-IN-MadhurNeural, then gTTS hi — narrates chapter by chapter.
  - Exactly 2 AI images per video (Pollinations, Openverse fallback):
    one book visual for the whole video, one thumbnail visual.
  - FFmpeg assembles the 10+ min video: static book visual + chapter
    title overlay + burned-in Hindi captions + music bed + SFX.
  - Pillow builds the BookPeak-style thumbnail.
  - YouTube Data API uploads it (private + staggered publishAt) with a
    full SEO description (takeaways + chapters with timestamps +
    hashtags, always #VedanticPsychology).

Env required: GEMINI_API_KEY, YT2_CLIENT_ID, YT2_CLIENT_SECRET,
YT2_REFRESH_TOKEN. Optional: GEMINI_TTS_VOICE (default Charon),
GEMINI_TTS_MODEL, GEMINI_TTS_STYLE, TTS_VOICE (Edge fallback voice),
DRY_RUN=1 (build the video but skip the upload), VIDEOS_PER_DAY
(default 3), TTS_ENGINE (force one TTS path: "gemini" for the approved
Charon voice, "edge", or "gtts"), TEST_CHAPTERS=N (short-test mode:
build only the first N chapters, so a quick test video can be rendered
without a full 10-minute build).
"""
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from assemble import assemble
from captions import write_srt
from images import fetch_video_images
from script_gen import generate_script
from thumbnail import make_thumbnail
from tts import narrate_chapters
from upload import upload_full, build_description

BOOKS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "books.json")
# Book rotation starts on this date (same convention as the live pool).
START_ORDINAL = datetime.date(2026, 11, 18)


def videos_per_day():
    try:
        return max(1, int(os.environ.get("VIDEOS_PER_DAY", "3")))
    except ValueError:
        return 3


def pick_book(index, per_day=None):
    """Deterministic book rotation: slot = days since START x per_day +
    index; cycles through books.json. Returns (book, cycle)."""
    if per_day is None:
        per_day = videos_per_day()
    with open(BOOKS_FILE, encoding="utf-8") as f:
        books = json.load(f)
    days = (datetime.date.today() - START_ORDINAL).days
    slot = days * per_day + index
    return books[slot % len(books)], slot // len(books)


def publish_at_for(index, per_day=None):
    """Stagger releases through the day, evenly spaced 07:00-22:00 IST.
    3 videos/day -> 07:00, 14:30, 22:00 IST. Returns an RFC3339 UTC
    timestamp, or a +5min time if the slot already passed (publish
    immediately)."""
    if per_day is None:
        per_day = videos_per_day()
    if per_day <= 1:
        hours = [7.0]
    else:
        step = 15.0 / (per_day - 1)  # 07:00 -> 22:00 IST
        hours = [7.0 + step * i for i in range(per_day)]
    slot_hour = hours[min(index, len(hours) - 1)]
    h, m = int(slot_hour), int(round((slot_hour - int(slot_hour)) * 60))
    # 07:00 IST = 01:30 UTC.
    base = datetime.datetime.now(datetime.timezone.utc).replace(
        hour=1, minute=30, second=0, microsecond=0)
    target = base + datetime.timedelta(hours=(h - 7), minutes=m)
    if target <= datetime.datetime.now(datetime.timezone.utc):
        target = (datetime.datetime.now(datetime.timezone.utc)
                  + datetime.timedelta(minutes=5))
    return target.strftime("%Y-%m-%dT%H:%M:%SZ")


def chapter_starts(timings, chapters):
    """[(title, start_seconds)] from per-chapter durations."""
    starts, acc = [], 0.0
    for t, ch in zip(timings, chapters):
        starts.append((ch.get("title", ""), acc))
        acc += t["duration"]
    return starts


def main():
    index = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    work_dir = sys.argv[2] if len(sys.argv) > 2 else "work_%d" % index
    os.makedirs(work_dir, exist_ok=True)

    gemini_key = os.environ["GEMINI_API_KEY"]
    per_day = videos_per_day()
    book, cycle = pick_book(index, per_day)
    print("Job %d — book: %s by %s (cycle %d)"
          % (index, book["title_en"], book["author"], cycle))

    script = generate_script(gemini_key, book)
    if not script:
        sys.exit("Script generation failed.")
    # Short-test mode: keep only the first N chapters (e.g. TEST_CHAPTERS=1
    # builds a ~2 min test video for judging the voice).
    test_chapters = os.environ.get("TEST_CHAPTERS", "").strip()
    if test_chapters:
        try:
            n = max(1, int(test_chapters))
        except ValueError:
            n = 1
        if n < len(script["chapters"]):
            script["chapters"] = script["chapters"][:n]
            script["total_words"] = sum(
                len(c.get("narration", "").split())
                for c in script["chapters"])
            print("TEST MODE: using first %d chapter(s) only (%d words)"
                  % (n, script["total_words"]))
    with open(os.path.join(work_dir, "script.json"), "w",
              encoding="utf-8") as f:
        json.dump(script, f, indent=2, ensure_ascii=False)

    chapters = script["chapters"]
    audio_dir = os.path.join(work_dir, "audio")
    timings = narrate_chapters(chapters, audio_dir)

    # Burned-in captions from the script itself (exact words, no API quota).
    srt_path = os.path.join(work_dir, "captions.srt")
    write_srt(chapters, timings, srt_path)

    media_dir = os.path.join(work_dir, "media")
    images = fetch_video_images(script, media_dir)

    starts = chapter_starts(timings, chapters)
    video_path = os.path.join(work_dir, "video.mp4")
    assemble(images["book"], timings, chapters, work_dir, video_path,
             srt_path=srt_path, chapter_starts=starts)

    thumb_path = os.path.join(work_dir, "thumbnail.jpg")
    make_thumbnail(images["thumbnail"], script["thumbnail_text"], thumb_path)

    description = build_description(script, book, starts)
    result = {
        "book": book["title_en"], "title": script["title"],
        "words": script["total_words"],
        "duration_s": sum(t["duration"] for t in timings),
        "chapters": len(chapters),
        "images": {"book": images["book"], "thumbnail": images["thumbnail"]},
        "video": video_path, "thumbnail": thumb_path,
        "captions": srt_path,
    }
    if os.environ.get("DRY_RUN") == "1":
        print("DRY RUN — skipping upload.")
    else:
        video_id, url = upload_full(
            video_path, thumb_path, script["title"], description,
            script["tags"], publish_at=publish_at_for(index, per_day))
        result["video_id"] = video_id
        result["url"] = url
    with open(os.path.join(work_dir, "result.json"), "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
