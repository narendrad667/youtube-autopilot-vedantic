"""Script generation for the Vedantic Psychology autopilot (Hindi book
summaries, BookPeak style).

Uses the Gemini free API (same free key family as the live What If
autopilot). No Muse tokens. Stdlib only — no extra pip packages needed.

Output contract (JSON):
{
  "book": "Atomic Habits",
  "title": "Hindi YouTube title, under 70 chars",
  "description": "2-3 sentences in Hindi + a question for comments",
  "tags": ["...", ... 8-12 tags, Hindi + English mix],
  "thumbnail_text": "short Hindi headline, 3-6 words",
  "total_words": 1800,
  "book_visual_prompt": "cinematic AI image prompt for the book visual",
  "thumbnail_prompt": "dramatic AI image prompt for the thumbnail base",
  "chapters": [
    {"title": "chapter title in Hindi",
     "narration": "...",            # 280-320 words, ~2 minutes spoken
     "takeaway": "one-line lesson in Hindi",
     "sfx": "soft bell"}            # short SFX cue for this chapter
  ]
}

Structure (BookPeak style):
- Chapter 1 = SUPER HOOK: a shocking question or a relatable life problem
  in the first 10 seconds that makes the viewer unable to click away.
- 6 chapters, each 280-320 words, each ending with one clear takeaway.
- Simple Hindi (Devanagari), real-life Indian examples, no difficult words.
- The script is an ORIGINAL summary in the narrator's own words — NEVER
  a verbatim reading of the book, never long quotes from it.
- Target 1800 Hindi words = 10+ minutes spoken (measured 2026-11-18:
  Gemini Charon ~171 wpm, so 1800 words ≈ 10.5 min; Edge ~145 wpm).
  Chapter 1 of the first test script actually came out at 378 words,
  so Gemini tends to overshoot the per-chapter ask — good for the
  10-minute minimum.
"""
import json
import time
import urllib.request
import urllib.error

DEFAULT_MODEL = "gemini-3.5-flash-lite"
GENERATE_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
                "{model}:generateContent?key={key}")

PROMPT_TEMPLATE = """Write a YouTube video script in simple Hindi (Devanagari script) for a book-summary video on the channel "Vedantic Psychology". The audience is Hindi-speaking India — students, job seekers, parents, anyone who wants to grow in life.

BOOK: {book_title} by {book_author} (Hindi title: {book_title_hi})
BOOK HOOK: {book_hook}

LENGTH: at least 1800 words of narration total (about 10-12 minutes spoken). Every chapter below must be 280-320 words — never write a shorter chapter, or the video will be too short.

IMPORTANT — ORIGINAL SUMMARY, NOT A READING: Write the summary in your own simple words, as if you are explaining the book to a friend. Do NOT copy sentences from the book, do NOT quote long passages, and do NOT invent fake quotes, fake studies or fake statistics. If you are unsure of a detail, say it approximately ("lagbhag", "aam taur par").

RETENTION STRUCTURE (mandatory):
- Chapter 1 is a SUPER HOOK: open with a shocking question or a relatable life problem in the first 10 seconds that makes the viewer unable to click away.
- Every chapter should open with something interesting — a question, a small story, or a surprising fact — so interest never drops.
- Do NOT write labels such as "HOOK:" in the script — write the hook lines themselves as normal sentences.
- Use simple everyday Hindi, real-life Indian examples (ghar, office, padhai, paisa, rishte), and end every chapter with one clear takeaway the viewer can use today.

CHAPTERS: exactly 6 chapters. For each chapter give:
- "title": a short Hindi chapter title.
- "narration": 280-320 words of spoken script in simple Hindi.
- "takeaway": one line in Hindi — the single lesson of this chapter.
- "sfx": one short sound-effect cue (e.g. "soft bell", "calm chime", "silence", "gentle wind").

ALSO GIVE:
- "title": a curiosity-driven Hindi YouTube title under 70 characters, starting with the life problem, not the book name.
- "description": 2-3 sentences in Hindi summarising what the viewer will learn, ending with a question inviting comments.
- "tags": 8-12 short search tags (mix of Hindi and English).
- "thumbnail_text": a short punchy Hindi headline, 3-6 words.
- "book_visual_prompt": one cinematic AI image prompt (in English) for a calm, beautiful book-themed visual that will stay on screen the whole video — peaceful, warm light, no text, no words, no letters in the image.
- "thumbnail_prompt": one dramatic AI image prompt (in English) for the thumbnail background — bold, high contrast, emotional, no text in the image.

Return ONLY a JSON object, no markdown fences, no extra text. Keys in this order:
{{"book": "...", "title": "...", "description": "...", "tags": [...], "thumbnail_text": "...", "total_words": 0, "book_visual_prompt": "...", "thumbnail_prompt": "...", "chapters": [{{"title": "...", "narration": "...", "takeaway": "...", "sfx": "..."}}]}}
"""

# Words: pass gate at >= 1500; keep the longest valid script if >= 1200.
MIN_WORDS = 1500
KEEP_WORDS = 1200


def _call_gemini(prompt, api_key, model):
    """One Gemini generateContent call. Returns raw text or None."""
    url = GENERATE_URL.format(model=model, key=api_key)
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 8000},
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload,
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        print("Gemini HTTP %s: %s" % (e.code, e.read().decode("utf-8")[:300]))
        return None
    except Exception as e:  # network errors etc.
        print("Gemini error: %s" % e)
        return None
    try:
        return "".join(p.get("text", "") for p in
                       data["candidates"][0]["content"]["parts"])
    except (KeyError, IndexError, TypeError):
        print("Gemini reply had no text: %s" % json.dumps(data)[:300])
        return None


def _parse_script(text):
    """Extract the JSON object from the model reply and validate it."""
    if not text:
        return None
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        print("No JSON object in Gemini reply: %s" % text[:300])
        return None
    try:
        script = json.loads(text[start:end + 1])
    except json.JSONDecodeError as e:
        print("JSON parse failed: %s | %s" % (e, text[:300]))
        return None
    chapters = script.get("chapters") or []
    if len(chapters) < 5 or not script.get("title"):
        print("Script failed validation: %d chapters" % len(chapters))
        return None
    words = sum(len((c.get("narration") or "").split()) for c in chapters)
    script["total_words"] = words
    return script


def generate_script(api_key, book, model=DEFAULT_MODEL):
    """Generate one full Hindi book-summary script. Retries up to 4 times
    if too short or invalid; keeps the longest valid script and returns
    it if it is at least 1200 words (a slightly shorter video beats no
    video). Returns the script dict or None."""
    prompt = PROMPT_TEMPLATE.format(
        book_title=book["title_en"], book_author=book["author"],
        book_title_hi=book["title_hi"], book_hook=book["hook_hi"])
    best = None
    for attempt in (1, 2, 3, 4):
        text = _call_gemini(prompt, api_key, model)
        script = _parse_script(text)
        if script is None:
            print("Attempt %d: invalid script, retrying..." % attempt)
            time.sleep(5)
            continue
        words = script["total_words"]
        print("Script: %s | %d words | %d chapters"
              % (script["title"], words, len(script["chapters"])))
        if best is None or words > best["total_words"]:
            best = script
        if words >= MIN_WORDS:
            return script
        print("Attempt %d: too short (%d words), retrying..." % (attempt, words))
        time.sleep(5)
    if best is not None and best["total_words"] >= KEEP_WORDS:
        print("Using longest script (%d words) after 4 attempts."
              % best["total_words"])
        return best
    return None


if __name__ == "__main__":
    import os
    import sys
    key = os.environ.get("GEMINI_API_KEY", "")
    if not key:
        sys.exit("Set GEMINI_API_KEY first.")
    books = json.load(open("books.json"))
    book = books[int(sys.argv[1])] if len(sys.argv) > 1 else books[0]
    script = generate_script(key, book)
    if script:
        print(json.dumps(script, indent=2, ensure_ascii=False)[:3000])
    else:
        sys.exit("Script generation failed.")
