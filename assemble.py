"""Video assembly for the Vedantic Psychology autopilot — FFmpeg only.

Video: ONE static book visual stays on screen for the whole video
(BookPeak style — no Ken Burns, no photo changes). The current chapter
title is overlaid in big Hindi text and the narration captions are
burned in at the bottom.
Audio: chapter narration (concatenated) + a synthesised ambient music
bed (sine pads + brown noise — original, never a paid library track)
+ a short synthesised SFX at each chapter start, matched to the
chapter's SFX cue.
Chapters: written into the mp4 as FFmpeg chapter metadata when possible
(so YouTube shows chapter markers); the description carries the chapter
list regardless.
Output: 1280x720, 30fps, H.264 + AAC, faststart for YouTube.

CRITICAL — Hindi shaping: FFmpeg's drawtext/subtitles filters do NOT
shape Devanagari correctly (conjuncts break: "लेकिन" renders as
"लेकनि"). Verified on this VM 2026-11-18. So ALL on-screen Hindi text
is pre-rendered to transparent PNGs with Pillow + libraqm (verified
correct shaping) and overlaid with the overlay filter: one PNG per
chapter title, and a transparent caption-track video (see captions.py)
for the burned-in captions. If the caption track cannot be built, the
subtitles filter is used as a degraded fallback (shaping may be wrong).
"""
import json
import os
import subprocess

W, H = 1280, 720
FPS = 30

# Devanagari font for the chapter-title PNGs (Pillow + libraqm shapes
# correctly). Noto Sans Devanagari ships with fonts-noto-core on Ubuntu
# runners (the workflow installs it) and is present on this VM.
DEVA_BOLD = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"

# SFX cue keyword -> synth recipe (same recipes as the live pipeline).
SFX_MAP = [
    ("bell", "bell"), ("chime", "bell"), ("temple", "bell"),
    ("rumble", "rumble"), ("earthquake", "rumble"),
    ("rain", "rain"), ("storm", "rain"), ("pour", "rain"),
    ("wind", "wind"), ("gust", "wind"), ("blizzard", "wind"),
    ("heartbeat", "heartbeat"), ("heart", "heartbeat"),
    ("impact", "impact"), ("explosion", "impact"), ("crash", "impact"),
    ("boom", "impact"),
    ("wave", "whoosh"), ("whoosh", "whoosh"), ("rush", "whoosh"),
    ("silence", "silence"), ("quiet", "silence"), ("calm", "silence"),
]


def sfx_kind(cue):
    cue = (cue or "").lower()
    for keyword, kind in SFX_MAP:
        if keyword in cue:
            return kind
    return "bell"


def run(cmd, what):
    print(" ".join(cmd[:6]), "...", what)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise RuntimeError("FFmpeg failed: %s" % what)
    return r


def synth_sfx(kind, out_path):
    """Synthesise one short SFX wav with lavfi. Silence -> tiny quiet file."""
    if kind == "silence":
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
               "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.5", out_path]
        run(cmd, "silence sfx")
        return
    if kind == "bell":
        src = None
        filt = ("[0:a]volume=0.4[b1];[1:a]volume=0.25[b2];"
                "[b1][b2]amix=inputs=2:normalize=0,"
                "afade=t=in:st=0:d=0.1,afade=t=out:st=1.8:d=0.7")
        inputs = ["-f", "lavfi", "-i", "sine=frequency=880:duration=2.5",
                  "-f", "lavfi", "-i", "sine=frequency=1320:duration=2.5"]
    elif kind == "rumble":
        src = None
        filt = "[0:a]volume=0.5[r];[1:a]lowpass=f=120,volume=0.4[n];[r][n]amix=inputs=2:normalize=0,afade=t=in:st=0:d=0.3,afade=t=out:st=1.5:d=0.5"
        inputs = ["-f", "lavfi", "-i", "sine=frequency=55:duration=2.0",
                  "-f", "lavfi", "-i", "anoisesrc=duration=2.0:color=brown"]
    elif kind == "rain":
        src = None
        filt = "[0:a]lowpass=f=1500,volume=0.30,afade=t=in:st=0:d=0.4,afade=t=out:st=2.0:d=0.5"
        inputs = ["-f", "lavfi", "-i", "anoisesrc=duration=2.5:color=white"]
    elif kind == "wind":
        src = None
        filt = "[0:a]bandpass=f=400:width_type=q:width=0.6,volume=0.35,afade=t=in:st=0:d=0.5,afade=t=out:st=1.8:d=0.7"
        inputs = ["-f", "lavfi", "-i", "anoisesrc=duration=2.5:color=brown"]
    elif kind == "heartbeat":
        src = None
        filt = ("[0:a]volume=0.9,atrim=0:0.14,adelay=0|0[h1];"
                "[0:a]volume=0.7,atrim=0:0.12,adelay=300|300[h2];"
                "[h1][h2]amix=inputs=2:normalize=0")
        inputs = ["-f", "lavfi", "-i", "sine=frequency=60:duration=0.6"]
    elif kind == "impact":
        src = None
        filt = "[0:a]volume=0.9,afade=t=out:st=0.4:d=0.3"
        inputs = ["-f", "lavfi", "-i",
                  "aevalsrc=0.9*sin(2*PI*(140-70*t)*t):duration=0.7"]
    else:  # whoosh
        src = None
        filt = "[0:a]bandpass=f=900:width_type=q:width=0.8,volume=0.30,afade=t=in:st=0:d=0.15,afade=t=out:st=0.7:d=0.5"
        inputs = ["-f", "lavfi", "-i", "anoisesrc=duration=1.2:color=white"]
    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + [
        "-filter_complex", filt, "-t", "3", out_path]
    run(cmd, "sfx %s" % kind)


def synth_bed(duration, out_path):
    """Synthesise a quiet ambient music bed (sine pads + brown noise)."""
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i", "sine=frequency=110:duration=%f" % duration,
           "-f", "lavfi", "-i", "sine=frequency=164.81:duration=%f" % duration,
           "-f", "lavfi", "-i", "sine=frequency=220:duration=%f" % duration,
           "-f", "lavfi", "-i", "anoisesrc=duration=%f:color=brown" % duration,
           "-filter_complex",
           "[0:a]volume=0.20[p1];[1:a]volume=0.14[p2];[2:a]volume=0.10[p3];"
           "[3:a]lowpass=f=200,volume=0.05[n];"
           "[p1][p2][p3][n]amix=inputs=4:normalize=0,"
           "tremolo=f=0.1:d=0.4,afade=t=in:st=0:d=2,afade=t=out:st=%f:d=3" % (duration - 3),
           "-t", str(duration), out_path]
    run(cmd, "music bed")


def _wrap_title(title, max_chars=28):
    """Wrap a Hindi chapter title into at most 2 lines for the overlay."""
    words = title.split()
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
    return lines[:2]


def _render_title_png(title, out_path, font_size=58):
    """Render a chapter title as a transparent 1280x720 PNG with Pillow
    + libraqm (correct Devanagari shaping). Yellow bold text with a black
    outline on a semi-transparent dark box, box bottom at 60% height
    (above the captions). Returns True on success."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        try:
            font = ImageFont.truetype(DEVA_BOLD, font_size)
        except OSError:
            font = ImageFont.load_default()
        lines = _wrap_title(title)
        heights = [draw.textbbox((0, 0), l, font=font)[3] for l in lines]
        widths = [draw.textlength(l, font=font) for l in lines]
        total_h = sum(heights) + 12 * (len(lines) - 1)
        # Box BOTTOM fixed at 60% height (was: box top at 60%). A 2-line
        # title used to push its 2nd line down into the caption zone
        # (captions sit at the bottom, MarginV 36) — e.g. "असर"/"बदला"/
        # "जादू" overlapping the white caption text in run #3. Bottom
        # anchoring keeps every line above the captions.
        box_pad = 18
        box_w = int(max(widths)) + 2 * box_pad
        box_h = total_h + 2 * box_pad
        box_bottom = int(H * 0.60)
        top = box_bottom - box_h
        box_x = (W - box_w) // 2
        draw.rectangle([box_x, top, box_x + box_w, top + box_h],
                       fill=(0, 0, 0, 140))
        y = top + box_pad
        for line, lh in zip(lines, heights):
            w = draw.textlength(line, font=font)
            x = (W - w) / 2
            draw.text((x, y), line, font=font, fill=(255, 210, 0, 255),
                      stroke_width=3, stroke_fill=(0, 0, 0, 255))
            y += lh + 12
        img.save(out_path, "PNG")
        return True
    except Exception as e:
        print("Title PNG render failed (%s)" % e)
        return False


def _write_chapter_metadata(chapter_starts, total, out_path):
    """Write an ffmetadata file with one [CHAPTER] per chapter.
    chapter_starts: [(title, start_seconds)]. Returns True on success."""
    try:
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(";FFMETADATA1\n")
            for i, (title, start) in enumerate(chapter_starts):
                end = (chapter_starts[i + 1][1] if i + 1 < len(chapter_starts)
                       else total)
                f.write("[CHAPTER]\nTIMEBASE=1/1000\n"
                        "START=%d\nEND=%d\ntitle=%s\n"
                        % (int(start * 1000), int(end * 1000),
                           title.replace("\n", " ")))
        return True
    except Exception as e:
        print("Chapter metadata write failed (%s)" % e)
        return False


def _attach_chapters(video_path, meta_path, work_dir):
    """Attach ffmetadata chapters to the finished mp4 (stream copy).
    Returns True on success; on failure the video stays chapter-less."""
    tmp = os.path.join(work_dir, "video_chapters.mp4")
    r = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", video_path, "-i", meta_path,
         "-map", "0", "-map_metadata", "1", "-map_chapters", "1",
         "-c", "copy", tmp],
        capture_output=True, text=True)
    if r.returncode != 0:
        print("Chapter attach failed (video kept without chapters): %s"
              % r.stderr[-500:])
        return False
    os.replace(tmp, video_path)
    return True


def assemble(book_visual, timings, chapters, work_dir, out_path,
             srt_path=None, chapter_starts=None):
    """book_visual: the single static image for the whole video.
    timings: [{audio, duration}] per chapter. chapters: script chapters
    (for SFX cues and titles). srt_path: optional .srt — used ONLY if the
    Pillow caption track cannot be built (degraded fallback; shaping may
    be wrong — see module docstring). chapter_starts: [(title,
    start_seconds)] for the title overlay and the mp4 chapter metadata.
    Builds out_path mp4."""
    from captions import render_caption_track

    n_chapters = len(timings)
    total = sum(t["duration"] for t in timings)
    print("Assembling %.1fs video from static book visual, %d chapters"
          % (total, n_chapters))

    # Chapter start times (cumulative narration durations).
    if chapter_starts is None:
        chapter_starts = []
        acc = 0.0
        for i, t in enumerate(timings):
            chapter_starts.append((chapters[i].get("title", ""), acc))
            acc += t["duration"]

    # --- synthesise bed + SFX files ---
    bed = os.path.join(work_dir, "bed.wav")
    synth_bed(total + 1, bed)
    sfx_files = []
    for i, chapter in enumerate(chapters):
        kind = sfx_kind(chapter.get("sfx", ""))
        if kind == "silence":
            continue
        path = os.path.join(work_dir, "sfx_%02d.wav" % i)
        synth_sfx(kind, path)
        sfx_files.append((path, chapter_starts[i][1]))

    # --- chapter-title PNGs (Pillow + libraqm, correct shaping) ---
    title_pngs = []  # (path, start, end)
    for i, (title, start) in enumerate(chapter_starts):
        path = os.path.join(work_dir, "chtitle_%02d.png" % i)
        if not _render_title_png(title, path):
            continue
        end = (chapter_starts[i + 1][1] if i + 1 < len(chapter_starts)
               else total)
        title_pngs.append((path, start, end))

    # --- caption track (Pillow PNGs -> transparent video) ---
    caption_track = render_caption_track(chapters, timings, work_dir, total)

    # --- build ffmpeg command ---
    # Input 0: the book visual, looped for the whole video length.
    # Inputs 1..k: chapter-title PNGs. Next: caption track (if built).
    # Then: chapter narration mp3s, the bed, the SFX files.
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-loop", "1", "-t", "%.3f" % total, "-i", book_visual]
    for path, _, _ in title_pngs:
        cmd += ["-i", path]
    cap_idx = None
    if caption_track:
        cap_idx = 1 + len(title_pngs)
        cmd += ["-i", caption_track]
    audio_base = 1 + len(title_pngs) + (1 if caption_track else 0)
    audio_inputs = [t["audio"] for t in timings]
    n_audio = len(audio_inputs)
    for a in audio_inputs:
        cmd += ["-i", a]
    cmd += ["-i", bed]
    sfx_start_idx = audio_base + n_audio + 1
    for path, _ in sfx_files:
        cmd += ["-i", path]

    filters = []
    # video: scale/crop the book visual to 1280x720.
    filters.append(
        "[0:v]scale=%d:%d:force_original_aspect_ratio=increase,"
        "crop=%d:%d,format=yuv420p,settb=AVTB[vbase]" % (W, H, W, H))
    # chapter-title overlays (one PNG per chapter, shown only in its span).
    cur = "vbase"
    for i, (_, start, end) in enumerate(title_pngs):
        out_lbl = "vtitle%d" % i
        filters.append(
            "[%s][%d:v]overlay=0:0:enable='between(t,%.3f,%.3f)'[%s]"
            % (cur, 1 + i, start, end, out_lbl))
        cur = out_lbl
    # captions: overlay the transparent caption track once; fall back to
    # the subtitles filter only if the track could not be built.
    vlabel = cur
    if caption_track:
        filters.append(
            "[%s][%d:v]overlay=0:0,format=yuv420p[vsub]"
            % (cur, cap_idx))
        vlabel = "vsub"
    elif srt_path and os.path.exists(srt_path):
        print("WARNING: caption track missing — using subtitles filter "
              "(Hindi shaping may be wrong)")
        esc = (os.path.abspath(srt_path).replace("\\", "\\\\")
               .replace(":", "\\:").replace("'", "\\'"))
        filters.append(
            "[%s]subtitles='%s':force_style='FontName=Noto Sans Devanagari,"
            "FontSize=22,PrimaryColour=&HFFFFFF,OutlineColour=&H80000000,"
            "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=36'[vsub]"
            % (cur, esc))
        vlabel = "vsub"
    # audio: resample + concat narration (no apad: apad would pad forever
    # and stall the concat filter).
    for i in range(n_audio):
        filters.append("[%d:a]aresample=44100,aformat=channel_layouts=stereo[a%d]"
                       % (audio_base + i, i))
    concat_inputs = "".join("[a%d]" % i for i in range(n_audio))
    filters.append("%sconcat=n=%d:v=0:a=1[narr]" % (concat_inputs, n_audio))
    # mix: narration + bed (quiet) + delayed SFX.
    filters.append("[%d:a]volume=0.08,aformat=channel_layouts=stereo[bed]"
                   % (audio_base + n_audio))
    for s_i, (path, start) in enumerate(sfx_files):
        idx = sfx_start_idx + s_i
        delay_ms = int(start * 1000)
        filters.append("[%d:a]volume=0.30,adelay=%d|%d,"
                       "aformat=channel_layouts=stereo[sfx%d]"
                       % (idx, delay_ms, delay_ms, s_i))
    labels = ["narr", "bed"] + ["sfx%d" % i for i in range(len(sfx_files))]
    filters.append("%samix=inputs=%d:normalize=0,alimiter=limit=0.95,"
                   "afade=t=out:st=%.1f:d=2[aout]"
                   % ("".join("[%s]" % l for l in labels), len(labels),
                      max(total - 2, 0)))
    cmd += ["-filter_complex", ";".join(filters),
            "-map", "[%s]" % vlabel, "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", "-t", "%.3f" % total, out_path]
    run(cmd, "assemble video")
    size = os.path.getsize(out_path)
    print("Wrote %s (%.1f MB)" % (out_path, size / 1e6))

    # Attach FFmpeg chapter metadata (best effort — video is fine without).
    meta_path = os.path.join(work_dir, "chapters.txt")
    if _write_chapter_metadata(chapter_starts, total, meta_path):
        if _attach_chapters(out_path, meta_path, work_dir):
            print("Attached %d chapters to the video" % len(chapter_starts))
    return out_path


if __name__ == "__main__":
    print("Import OK. Use run_one.py to build a video.")
