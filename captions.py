"""Burned-in captions for the Vedantic Psychology autopilot.

The captions come from the script itself (the exact words that are
narrated), so the text is 100% accurate — unlike YouTube auto-captions.
Timing is ESTIMATED from word counts within each chapter (steady TTS
pace), not word-level forced alignment, so a cue can be a fraction of a
second early or late. The .srt is also saved alongside the video so it
can be uploaded to YouTube Studio separately if ever needed.

CRITICAL — Hindi shaping: FFmpeg's subtitles/drawtext filters do NOT
shape Devanagari correctly (conjuncts break: "लेकिन" renders as
"लेकनि", "सच्चाई" as "सचूाई"). Verified on this VM 2026-11-18. So the
captions are NOT burned in with the subtitles filter. Instead each cue
is rendered to a transparent PNG with Pillow + libraqm (which shapes
Devanagari correctly — verified: "लेकिन सच्चाई किताब शक्ति" renders
perfectly), the PNGs are joined into a transparent caption-track video,
and that track is overlaid once in the assemble step. The .srt is still
written for the artifact.
Style: white Noto Sans Devanagari with a black outline, bottom-centre.
"""
import os
import re
import subprocess

MAX_CHARS_PER_LINE = 42
MAX_LINES_PER_CUE = 2
MIN_CUE_S = 1.2
MAX_CUE_S = 5.0

W, H = 1280, 720
DEVA_REGULAR = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Regular.ttf"
CAPTION_FONT_SIZE = 40
CAPTION_MARGIN_V = 36


def _fmt(t):
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return "%02d:%02d:%02d,%03d" % (h, m, s, ms)


def _split_sentences(text):
    """Split on sentence ends — Hindi danda (।) counts as a sentence end
    alongside Latin . ! ?"""
    parts = re.split(r"(?<=[.!?।])\s+", text.strip())
    return [p.strip() for p in parts if p.strip()]


def _wrap_words(words, max_chars):
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if len(trial) <= max_chars:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _cues_for_chapter(narration, start, duration):
    """Split one chapter's narration into (start, end, text) cues."""
    words = narration.split()
    if not words or duration <= 0:
        return []
    wps = len(words) / duration  # words per second (steady TTS pace)
    chunks = []
    for sent in _split_sentences(narration):
        lines = _wrap_words(sent.split(), MAX_CHARS_PER_LINE)
        for i in range(0, len(lines), MAX_LINES_PER_CUE):
            chunks.append(lines[i:i + MAX_LINES_PER_CUE])
    timed, t = [], start
    for chunk in chunks:
        text = "\n".join(chunk)
        n = len(text.split())
        dur = max(MIN_CUE_S, min(MAX_CUE_S, n / wps)) if wps > 0 else 2.0
        end = min(t + dur, start + duration)
        if end - t < 0.5:
            end = min(t + 0.5, start + duration)
        timed.append((t, end, text))
        t = end
    if timed and timed[-1][1] < start + duration - 0.2:
        s, _, tx = timed[-1]
        timed[-1] = (s, start + duration, tx)
    return timed


def all_cues(chapters, timings):
    """All (start, end, text) cues for the whole video."""
    cues, t = [], 0.0
    for chapter, timing in zip(chapters, timings):
        cues += _cues_for_chapter(chapter["narration"], t, timing["duration"])
        t += timing["duration"]
    return cues


def write_srt(chapters, timings, out_path):
    """Write an .srt from chapters + per-chapter durations. Chapters are
    dicts with a "narration" key; timings are [{duration}]. Returns path."""
    cues = all_cues(chapters, timings)
    with open(out_path, "w", encoding="utf-8") as f:
        for i, (s, e, text) in enumerate(cues, 1):
            f.write("%d\n%s --> %s\n%s\n\n" % (i, _fmt(s), _fmt(e), text))
    print("Wrote %s (%d cues)" % (out_path, len(cues)))
    return out_path


def _render_cue_png(text, out_path):
    """Render one caption cue as a transparent 1280x720 PNG with Pillow
    + libraqm (correct Devanagari shaping). White text, black outline,
    bottom-centre."""
    from PIL import Image, ImageDraw, ImageFont
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(DEVA_REGULAR, CAPTION_FONT_SIZE)
    except OSError:
        font = ImageFont.load_default()
    lines = text.split("\n")
    heights = [draw.textbbox((0, 0), l, font=font)[3] for l in lines]
    total_h = sum(heights) + 10 * (len(lines) - 1)
    y = H - CAPTION_MARGIN_V - total_h
    for line, lh in zip(lines, heights):
        w = draw.textlength(line, font=font)
        x = (W - w) / 2
        draw.text((x, y), line, font=font, fill=(255, 255, 255, 255),
                  stroke_width=2, stroke_fill=(0, 0, 0, 255))
        y += lh + 10
    img.save(out_path, "PNG")


def render_caption_track(chapters, timings, work_dir, total, fps=10):
    """Build a transparent caption-track video (qtrle .mov with alpha)
    from the script's cues. Returns the track path, or None if it could
    not be built (caller falls back to the subtitles filter).
    Each cue becomes one PNG held for its duration; gaps get a blank PNG.
    The track runs at `fps` (10 is plenty — captions switch within 100ms).
    """
    cues = all_cues(chapters, timings)
    if not cues:
        return None
    track_dir = os.path.join(work_dir, "capframes")
    os.makedirs(track_dir, exist_ok=True)
    blank = os.path.join(track_dir, "blank.png")
    try:
        from PIL import Image
        Image.new("RGBA", (W, H), (0, 0, 0, 0)).save(blank, "PNG")
    except Exception as e:
        print("Caption track failed (blank PNG): %s" % e)
        return None
    entries = []  # (path, duration)
    t = 0.0
    for i, (s, e, text) in enumerate(cues):
        if s > t + 0.05:
            entries.append((blank, s - t))
        path = os.path.join(track_dir, "cue_%03d.png" % i)
        try:
            _render_cue_png(text, path)
        except Exception as ex:
            print("Caption cue render failed (%s)" % ex)
            return None
        entries.append((path, max(0.1, e - s)))
        t = e
    if t < total - 0.05:
        entries.append((blank, total - t))
    list_path = os.path.join(track_dir, "concat.txt")
    with open(list_path, "w") as f:
        for path, dur in entries:
            f.write("file '%s'\nduration %.3f\n" % (path, dur))
        # Concat quirk: the last file must be repeated (its duration is
        # otherwise ignored).
        f.write("file '%s'\n" % entries[-1][0])
    out = os.path.join(work_dir, "caption_track.mov")
    # NOTE (2026-11-18): on the GitHub runner BOTH codecs failed with
    # `-vf format=yuva420p` while the same command works on this VM
    # (FFmpeg 8.1.2) — the runner's older FFmpeg (Ubuntu apt) apparently
    # rejects yuva420p for these encoders. So try with the filter first,
    # then WITHOUT it (encoder negotiates its own pix_fmt), and always
    # print ffmpeg's stderr so the real error shows in the log.
    attempts = [
        ("qtrle", ["-vf", "format=yuva420p"]),
        ("png", ["-vf", "format=yuva420p"]),
        ("qtrle", []),
        ("png", []),
    ]
    for codec, vf in attempts:
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
               "-i", list_path] + vf + ["-r", str(fps), "-c:v", codec, out]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0 and os.path.exists(out) \
                and os.path.getsize(out) > 1000:
            print("Caption track: %s (%d cues, %s)"
                  % (out, len(cues), codec))
            return out
        print("Caption track %s%s failed: %s"
              % (codec, " (no pix_fmt filter)" if not vf else "",
                 (r.stderr or "").strip()[:500]))
    return None


if __name__ == "__main__":
    import json
    import sys
    script = json.load(open(sys.argv[1]))
    timings = json.load(open(sys.argv[2]))
    write_srt(script["chapters"], timings, sys.argv[3])
