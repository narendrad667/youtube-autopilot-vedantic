"""Narration for the Vedantic Psychology autopilot — Hindi book summaries.

Primary: Kokoro TTS (free open-source neural voice, hexgrad/Kokoro-82M),
Hindi pipeline (lang_code='h'). Runs locally on CPU, no key. Needs
espeak-ng installed and the ~310 MB model downloaded on first use.
The voice is fully configurable via the KOKORO_HINDI_VOICE env var.
NOTE 2026-11-18: the user REJECTED ALL Kokoro Hindi voices — hm_omega,
hm_psi and hf_alpha all sound robotic to him (hm_omega also had wrong
pronunciation). Kokoro Hindi stays in the chain only as a fallback
until/unless he approves one; do NOT present any Kokoro Hindi voice as
the approved primary. He now wants ONE test video with Edge TTS Hindi
(hi-IN-MadhurNeural) to judge it. Edge TTS cannot run from this VM
(proxy blocks speech.platform.bing.com) but works on GitHub Actions —
the test video is built via a GitHub Actions dry run with
TTS_ENGINE=edge (see run_one.py TEST_CHAPTERS + daily.yml inputs).
Fallback 1: Microsoft Edge TTS (natural neural voices, free, no API key),
Hindi male voice hi-IN-MadhurNeural. Works on GitHub Actions runners.
Fallback 2: gTTS (Google Translate TTS, free, no key, plain HTTPS),
lang='hi'. Robotic, last resort only.

One mp3 per chapter, plus a timings JSON with each chapter's duration
(measured with ffprobe) so the assembler and the chapter timestamps in
the description can be computed from real audio lengths.
"""
import asyncio
import json
import os
import re
import subprocess

# Configurable voice — swap with env if the user rejects the default.
DEFAULT_VOICE = os.environ.get("TTS_VOICE", "hi-IN-MadhurNeural")
# KOKORO_HINDI_VOICE picks the Kokoro Hindi voice. Default hm_psi is a
# PLACEHOLDER — ALL Kokoro Hindi voices (hm_omega, hm_psi, hf_alpha)
# were rejected by the user 2026-11-18 (sound robotic). Kokoro Hindi
# stays only as a fallback; the primary under test is Edge Hindi
# (TTS_ENGINE=edge). Never present a Kokoro Hindi voice as approved.
KOKORO_VOICE = (os.environ.get("KOKORO_HINDI_VOICE")
                or os.environ.get("KOKORO_VOICE", "hm_psi"))
KOKORO_LANG = os.environ.get("KOKORO_LANG", "h")
GTTS_LANG = os.environ.get("TTS_LANG", "hi")
# TTS_ENGINE=kokoro forces the Kokoro path (used for local testing).
FORCE_ENGINE = os.environ.get("TTS_ENGINE", "")

_KOKORO_PIPE = None
_KOKORO_FAILED = False
# Kokoro handles short text best; long chapters are split on sentence
# boundaries into chunks of at most this many characters.
KOKORO_CHUNK_CHARS = 600


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


async def _edge_tts_one(text, voice, out_path):
    import edge_tts
    comm = edge_tts.Communicate(text, voice)
    await comm.save(out_path)


def edge_tts_scene(text, voice, out_path):
    asyncio.run(_edge_tts_one(text, voice, out_path))
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000


def gtts_scene(text, lang, out_path):
    from gtts import gTTS
    gTTS(text=text, lang=lang, slow=False).save(out_path)
    return os.path.exists(out_path) and os.path.getsize(out_path) > 1000


def _split_text(text, max_chars=KOKORO_CHUNK_CHARS):
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


def kokoro_scene(text, voice, out_path):
    """Narrate with Kokoro Hindi (lang_code='h'). The pipeline object is
    loaded once and reused for all chapters. Long text is split into
    sentence chunks and the audio concatenated. Returns True on success."""
    global _KOKORO_PIPE, _KOKORO_FAILED
    if _KOKORO_FAILED:
        return False
    try:
        if _KOKORO_PIPE is None:
            from kokoro import KPipeline
            _KOKORO_PIPE = KPipeline(lang_code=KOKORO_LANG)
        import numpy as np
        import soundfile as sf
        all_audio = []
        for chunk in _split_text(text):
            pieces = []
            for _, _, audio in _KOKORO_PIPE(chunk, voice=voice):
                pieces.append(audio)
            if pieces:
                all_audio.append(np.concatenate(pieces))
        if not all_audio:
            return False
        tmp_wav = out_path + ".kokoro.wav"
        sf.write(tmp_wav, np.concatenate(all_audio), 24000)
        r = subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", tmp_wav,
             "-codec:a", "libmp3lame", "-q:a", "3", out_path],
            capture_output=True, text=True)
        os.remove(tmp_wav)
        return r.returncode == 0 and os.path.exists(out_path) \
            and os.path.getsize(out_path) > 1000
    except Exception as e:
        print("Kokoro failed (%s)" % e)
        _KOKORO_FAILED = True
        return False


def synth_chapter(text, voice, out_path, index):
    """Narrate one chapter. Order: Kokoro Hindi first, Edge TTS
    fallback, gTTS last resort. TTS_ENGINE forces one path:
    "kokoro" -> [kokoro, gtts], "edge"/"edge-tts" -> [edge-tts, gtts]
    (the Edge test video uses TTS_ENGINE=edge), "gtts" -> [gtts].
    Returns (ok, engine)."""
    order = ["kokoro", "edge-tts", "gtts"]
    if FORCE_ENGINE == "kokoro":
        order = ["kokoro", "gtts"]
    elif FORCE_ENGINE in ("edge", "edge-tts"):
        order = ["edge-tts", "gtts"]
    elif FORCE_ENGINE == "gtts":
        order = ["gtts"]
    for engine in order:
        try:
            if engine == "edge-tts":
                ok = edge_tts_scene(text, voice, out_path)
            elif engine == "kokoro":
                ok = kokoro_scene(text, KOKORO_VOICE, out_path)
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


def narrate_chapters(chapters, out_dir, voice=DEFAULT_VOICE):
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
def narrate_scenes(scenes, out_dir, voice=DEFAULT_VOICE):
    return narrate_chapters(scenes, out_dir, voice)


if __name__ == "__main__":
    import sys
    text = sys.argv[1] if len(sys.argv) > 1 else (
        "सोचो और अमीर बनो। यह किताब बताती है कि सफलता किस्मत से नहीं, "
        "सोच से बनती है। छोटी-छोटी आदतें रोज़ दोहराने से बड़ा बदलाव आता है।")
    ok, engine = synth_chapter(text, DEFAULT_VOICE, "/tmp/tts_smoke_hi.mp3", 0)
    print("ok=%s engine=%s duration=%.1fs"
          % (ok, engine, probe_duration("/tmp/tts_smoke_hi.mp3")))
