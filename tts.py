"""Narration for the Vedantic Psychology autopilot — Hindi book summaries.

Primary (USER-APPROVED 2026-11-18): Gemini native text-to-speech
(gemini-3.8-flash-tts, free of charge on the Gemini API free tier with
the same GEMINI_API_KEY the script generator already uses), voice
"Charon". The user listened to three Gemini voices (Kore, Charon,
Aoede) and picked Charon: "ye thik ha". Style: clear, calm, steady
narration — the style instruction is part of every TTS request so the
voice sounds the same in every video ("har bar style me").
Configurable via GEMINI_TTS_VOICE (default Charon) and
GEMINI_TTS_MODEL (default gemini-3.8-flash-tts; falls back to
gemini-3.1-flash-tts-preview, then gemini-2.5-flash-preview-tts if the
model is retired).

REJECTED voices (do NOT use as primary): ALL Kokoro Hindi voices
(hm_omega, hm_psi, hf_alpha) and Edge hi-IN-MadhurNeural — the user
said all of them sound robotic. Kokoro has been REMOVED from this
pipeline entirely (no torch, no espeak-ng needed any more).
Fallback 1: Microsoft Edge TTS, hi-IN-MadhurNeural (free, no key).
Fallback 2: gTTS, lang='hi' (robotic, last resort only).

Measured paces (2026-11-18): Gemini Charon ~171 wpm (30 words in
10.5s); Edge Hindi ~145 wpm (378 words in 156.4s). The script target
is 1800 words so a full video is 10+ minutes at Gemini pace.

One mp3 per chapter, plus a timings JSON with each chapter's duration
(measured with ffprobe) so the assembler and the chapter timestamps in
the description can be computed from real audio lengths.
"""
import base64
import json
import os
import re
import subprocess
import time
import urllib.error
import urllib.request
import wave

# Configurable voice — the user approved Charon on 2026-11-18.
# NOTE: use `or` (not .get's default) because GitHub passes an UNSET
# secret as an EMPTY STRING env var — .get("X", "Charon") returns ""
# when X is set-but-empty, and "" is not a valid voice name. (That bug
# made run #2 fall back to Edge: "Received empty voice name".)
GEMINI_VOICE = os.environ.get("GEMINI_TTS_VOICE") or "Charon"
GEMINI_MODEL = os.environ.get("GEMINI_TTS_MODEL") or "gemini-3.8-flash-tts"
GEMINI_MODEL_FALLBACKS = [
    "gemini-3.8-flash-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
]
# Style instruction, sent with every request so the voice is clear and
# sounds the same in every video. Gemini TTS treats a leading style
# direction as instruction, not as text to read aloud.
GEMINI_STYLE = os.environ.get("GEMINI_TTS_STYLE") or (
    "Say clearly, calmly and steadily, like a professional narrator:")
# Edge fallback voice (also rejected as robotic by the user — fallback
# only, never primary).
EDGE_VOICE = os.environ.get("TTS_VOICE") or "hi-IN-MadhurNeural"
GTTS_LANG = os.environ.get("TTS_LANG") or "hi"
# TTS_ENGINE forces one path: "gemini"/"gemini-tts" -> [gemini, edge,
# gtts], "edge"/"edge-tts" -> [edge-tts, gtts], "gtts" -> [gtts].
FORCE_ENGINE = os.environ.get("TTS_ENGINE", "")
# Long chapters are split on sentence boundaries into chunks of at most
# this many characters (one Gemini API call per chunk).
TTS_CHUNK_CHARS = 900


def probe_duration(path):
    """Audio duration in seconds via ffprobe."""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", path],
        capture_output=True, text=True)
    try:
        return float(out.stdout.strip())
    except ValueError:
        return 0.0


def _split_text(text, max_chars=TTS_CHUNK_CHARS):
    """Split long text into sentence-boundary chunks (Hindi danda and
    Latin punctuation both count as sentence ends)."""
    sents = [s.strip() for s in
             re.split(r"(?<=[.!?।])\s+", text.strip()) if s.strip()]
    chunks, cur = [], ""
    for s in sents:
        trial = (cur + " " + s).strip()
        if len(trial) <= max_chars:
            cur = trial
        else:
            if cur:
                chunks.append(cur)
            cur = s
    if cur:
        chunks.append(cur)
    return chunks or [text]


def _gemini_tts_call(api_key, model, voice, text):
    """One Gemini TTS request. Returns raw 16-bit PCM bytes at 24 kHz."""
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/%s"
        ":generateContent?key=%s" % (model, api_key)
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": GEMINI_STYLE + "\n\n" + text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {"voiceName": voice}
                }
            },
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8", "replace")[:300]
        raise RuntimeError("HTTP %d from %s: %s" % (e.code, model, err))
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
    for part in parts:
        inline = part.get("inlineData", {})
        if inline.get("mimeType", "").startswith("audio/"):
            return base64.b64decode(inline["data"])
    raise RuntimeError("No audio in response from %s" % model)


def _gemini_tts_call_with_retry(api_key, model, voice, text):
    """One chunk via one model, with backoff on 429. The free tier
    rate-limits per minute (run #4 hit 429 after 2 chapters because
    chunks fired back-to-back and the single 15s retry was not enough).
    Retries the SAME model up to 3 more times (15s, 60s, 120s) before
    giving up on it. Returns PCM bytes, or raises the last error."""
    waits = (15, 60, 120)
    last_err = None
    for attempt in range(len(waits) + 1):
        try:
            return _gemini_tts_call(api_key, model, voice, text)
        except Exception as e:
            last_err = e
            if "429" not in str(e) or attempt == len(waits):
                raise
            wait = waits[attempt]
            print("Gemini TTS rate-limited (%s), waiting %ds "
                  "(attempt %d/%d)..." % (model, wait, attempt + 1,
                                           len(waits)))
            time.sleep(wait)
    raise last_err


def gemini_tts_scene(text, voice, out_path):
    """Narrate with Gemini TTS (Charon). Long text is split into
    sentence chunks; the PCM is concatenated and converted to mp3 with
    ffmpeg. Returns True on success."""
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("Gemini TTS: no GEMINI_API_KEY set.")
        return False
    models = [GEMINI_MODEL] + [m for m in GEMINI_MODEL_FALLBACKS
                               if m != GEMINI_MODEL]
    pcm_all = b""
    chunks = _split_text(text)
    for ci, chunk in enumerate(chunks):
        if ci > 0:
            # Pace requests: firing chunks back-to-back trips the
            # free-tier per-minute limit (run #4).
            time.sleep(3)
        pcm = None
        last_err = ""
        for mi, model in enumerate(models):
            try:
                pcm = _gemini_tts_call_with_retry(api_key, model, voice,
                                                  chunk)
                break
            except Exception as e:
                last_err = str(e)
                if "429" in last_err and mi < len(models) - 1:
                    # The quota is per project, so the next model is
                    # limited too — wait a minute before trying it.
                    print("Gemini TTS still rate-limited, waiting 60s "
                          "before the next model...")
                    time.sleep(60)
        if pcm is None:
            print("Gemini TTS failed for a chunk: %s" % last_err)
            return False
        pcm_all += pcm
    if not pcm_all:
        return False
    tmp_wav = out_path + ".gemini.wav"
    with wave.open(tmp_wav, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm_all)
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", tmp_wav,
         "-codec:a", "libmp3lame", "-q:a", "3", out_path],
        capture_output=True, text=True)
    os.remove(tmp_wav)
    return r.returncode == 0 and os.path.exists(out_path) \
        and os.path.getsize(out_path) > 1000


async def _edge_tts_one(text, voice, out_path):
    import edge_tts
    comm = edge_tts.Communicate(text, voice)
    await comm.save(out_path)


def edge_tts_scene(text, voice, out_path):
    import asyncio
    asyncio.run(_edge_tts_one(text, voice, out_path))
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000


def gtts_scene(text, lang, out_path):
    from gtts import gTTS
    gTTS(text=text, lang=lang, slow=False).save(out_path)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000


def synth_chapter(text, voice, out_path, index):
    """Narrate one chapter. Order: Gemini TTS (Charon) first, Edge TTS
    fallback, gTTS last resort. TTS_ENGINE forces one path (see above).
    Returns (ok, engine)."""
    order = ["gemini-tts", "edge-tts", "gtts"]
    if FORCE_ENGINE in ("gemini", "gemini-tts"):
        order = ["gemini-tts", "edge-tts", "gtts"]
    elif FORCE_ENGINE in ("edge", "edge-tts"):
        order = ["edge-tts", "gtts"]
    elif FORCE_ENGINE == "gtts":
        order = ["gtts"]
    for engine in order:
        try:
            if engine == "gemini-tts":
                ok = gemini_tts_scene(text, GEMINI_VOICE, out_path)
            elif engine == "edge-tts":
                ok = edge_tts_scene(text, voice, out_path)
            else:
                ok = gtts_scene(text, GTTS_LANG, out_path)
            if ok:
                return True, engine
            print("Chapter %d: %s produced nothing, trying next..."
                  % (index, engine))
        except Exception as e:
            print("Chapter %d: %s failed (%s), trying next..."
                  % (index, engine, e))
    return False, "none"


def narrate_chapters(chapters, out_dir, voice=EDGE_VOICE):
    """Narrate every chapter. Returns list of {audio, duration, engine,
    title} and writes timings.json in out_dir."""
    os.makedirs(out_dir, exist_ok=True)
    results = []
    for i, chapter in enumerate(chapters):
        path = os.path.join(out_dir, "chapter_%02d.mp3" % i)
        ok, engine = synth_chapter(chapter["narration"], voice, path, i)
        if not ok:
            raise RuntimeError("TTS failed for chapter %d" % i)
        dur = probe_duration(path)
        if dur <= 0:
            raise RuntimeError("Zero-length audio for chapter %d" % i)
        print("Chapter %02d: %.1fs (%s) — %s"
              % (i, dur, engine, chapter.get("title", "")[:40]))
        results.append({"audio": path, "duration": dur, "engine": engine,
                        "title": chapter.get("title", "")})
    timings_path = os.path.join(out_dir, "timings.json")
    with open(timings_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    total = sum(r["duration"] for r in results)
    print("Total narration: %.1fs (%.1f min)" % (total, total / 60.0))
    return results


# Backwards-compatible alias (same shape as the live pipeline's scenes).
def narrate_scenes(scenes, out_dir, voice=EDGE_VOICE):
    return narrate_chapters(scenes, out_dir, voice)


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else (
        "सोचो और अमीर बनो। यह किताब बताती है कि सफलता किस्मत से नहीं, "
        "सोच से बनती है। छोटी-छोटी आदतें रोज़ दोहराने से बड़ा बदलाव आता है।")
    ok, engine = synth_chapter(text, EDGE_VOICE, "/tmp/tts_smoke_hi.mp3", 0)
    print("ok=%s engine=%s duration=%.1fs"
          % (ok, engine, probe_duration("/tmp/tts_smoke_hi.mp3")))
