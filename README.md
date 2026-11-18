# Vedantic Psychology — YouTube Autopilot (Hindi Book Summaries)

Automated Hindi book-summary videos for the **Vedantic Psychology**
YouTube channel, in the style of @BookPeak: faceless Hindi voiceover,
one book visual on screen for the whole video, 10+ minutes long.
Fully free, zero Muse tokens after setup — same architecture as the live
What If autopilot (`~/workspace/youtube-autopilot/`), adapted for Hindi.

## How it differs from the live pipeline

| | Live (What If / The Reality Shift) | This pipeline (Vedantic Psychology) |
|---|---|---|
| Language | English | Hindi (Devanagari script) |
| Content | What If questions, 13 scenes | Book summaries, 6 chapters |
| Length | 4–5 min | 10+ min (1800 words) |
| Images | ~52 photos/video (Openverse) | **2 AI images/video** (Pollinations): book visual + thumbnail visual |
| Motion | Ken Burns + clips | Static book visual + chapter-title overlay |
| Voice | Kokoro am_adam (English) | **Gemini TTS "Charon" (approved)** — see below |
| Topics | trends + 102-topic pool | 50-book rotation from `books.json` |
| Description | Short + tags | Full SEO + takeaways + chapters with timestamps + hashtags |
| Secrets | `YT_*` | `YT2_*` (separate channel) |
| Videos/day | 6 | `VIDEOS_PER_DAY` env (default 3) |

## Voice — FINAL (2026-11-18)

**APPROVED: Gemini native TTS, voice "Charon".** The user listened to
three Gemini voices (Kore, Charon, Aoede) and picked Charon: "ye thik
ha". It is the primary voice in `tts.py`, with a style instruction on
every request — clear, calm, steady narration — so the voice sounds
the same in every video ("har bar style me"). Configurable via
`GEMINI_TTS_VOICE` (default Charon) and `GEMINI_TTS_MODEL` (default
`gemini-3.8-flash-tts`, free of charge on the Gemini API free tier with
the same `GEMINI_API_KEY` the script generator uses). Fallback chain:
Gemini TTS → Edge `hi-IN-MadhurNeural` → gTTS `hi`.

**REJECTED (never as primary):** ALL Kokoro Hindi voices (`hm_omega`,
`hm_psi`, `hf_alpha`) and Edge `hi-IN-MadhurNeural` — the user said
all of them sound robotic. Kokoro has been REMOVED from this pipeline
(no torch, no espeak-ng, no `kokoro`/`soundfile` in requirements).

**Measured paces:** Gemini Charon ~171 wpm (30 words in 10.5s);
Edge Hindi ~145 wpm (378 words in 156.4s). The script target is 1800
words (6 chapters × 280–320), so a full video is ~10.5 min at Gemini
pace. The first Edge test video (Atomic Habits ch. 1, 378 words,
156.4s) is the evidence for the Edge pace.

## Files

- `books.json` — 50 books (English title, author, Hindi title, Hindi hook).
- `script_gen.py` — Gemini `gemini-3.5-flash-lite` writes a Hindi script:
  super hook + 6 chapters (280–320 words each), takeaway per chapter,
  title, SEO description draft, tags, thumbnail text, 2 AI image
  prompts. Word gate: ≥1500 to pass, keeps the longest ≥1200 after
  4 attempts. Target 1800 words ≈ 10.5 min at Gemini Charon pace.
- `tts.py` — Gemini TTS "Charon" primary (clear/calm/steady style on
  every request), Edge Hindi fallback, gTTS `hi` last resort. One mp3
  per chapter + `timings.json`.
- `images.py` — 2 images/video via Pollinations (FLUX, free, no key;
  bottom-7% watermark crop), Openverse fallback, never-fail reuse.
- `captions.py` — burned-in Hindi captions from the script (.srt, word-
  count timing; splits sentences on the Hindi danda `।` too).
- `assemble.py` — static book visual, chapter-title overlay (Noto Sans
  Devanagari), burned-in captions, music bed + SFX, FFmpeg chapter
  metadata (best effort).
- `thumbnail.py` — BookPeak style: book visual left, big bold Hindi
  headline right, "ऑडियोबुक" ribbon. Pillow, 1280×720.
- `upload.py` — YouTube Data API v3 resumable upload (category 27,
  private + staggered publishAt) + `build_description()` (SEO + chapters
  with timestamps + hashtags, always `#VedanticPsychology`).
- `run_one.py` — orchestrator: pick book → script → TTS → 2 images →
  assemble → thumbnail → upload (or `DRY_RUN=1` to skip upload).
- `.github/workflows/daily.yml` — daily schedule (cron placeholder
  01:00 UTC = 06:30 IST, to be confirmed), matrix gated by
  `VIDEOS_PER_DAY`.

## Secrets needed (GitHub repo secrets)

- `GEMINI_API_KEY` — same free Gemini key as the live pipeline.
  Also powers the Gemini TTS voice (no separate key needed).
- `YT2_CLIENT_ID`, `YT2_CLIENT_SECRET`, `YT2_REFRESH_TOKEN` — OAuth for
  the **Vedantic Psychology** channel (separate token: Playground auth
  selecting the Vedantic Psychology brand account; verify with a
  Playground "Refresh access token" 200 before storing, like the live
  pipeline). OAuth app must be in Production.
- `GEMINI_TTS_VOICE` (optional) — the user's picked Gemini voice
  (default Charon, approved 2026-11-18).

## Quota warning

YouTube Data API quota is **per Google Cloud project, not per channel**.
If this channel shares the live pipeline's project, both channels
together may only upload **6 videos/day total** (9900/10000 units).
6+6/day needs a second Google Cloud project with its own OAuth client.

## Local dry-run test

```bash
cd ~/workspace/youtube-autopilot-vedantic
~/workspace/youtube-autopilot/.venv/bin/python -m py_compile *.py
# TTS smoke test needs GEMINI_API_KEY (Gemini TTS runs on the API):
GEMINI_API_KEY=... ~/workspace/youtube-autopilot/.venv/bin/python tts.py "सोचो और अमीर बनो।"
# Full dry run with a fixture script (no Gemini key needed):
#   test_work/test_dryrun.py — builds a short video end to end with
#   DRY_RUN=1 and TEST_CHAPTERS=1.
# Real run (needs GEMINI_API_KEY + YT2_*):
GEMINI_API_KEY=... DRY_RUN=1 ~/workspace/youtube-autopilot/.venv/bin/python run_one.py 0
# Full test video with the approved Charon voice (GitHub Actions):
#   workflow_dispatch with tts_engine=gemini (or empty for the default
#   chain), test_chapters empty (full 6-chapter video), dry_run true.
```

Note: the full pipeline needs `ffmpeg` and the `fonts-noto-core`
package (Devanagari font for captions/thumbnails); both are installed
on this VM and in the workflow. No torch, no espeak-ng any more —
Kokoro was removed when the user rejected all its Hindi voices.
