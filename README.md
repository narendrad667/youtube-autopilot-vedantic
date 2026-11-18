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
| Length | 4–5 min | 10+ min (1500–1800 words) |
| Images | ~52 photos/video (Openverse) | **2 AI images/video** (Pollinations): book visual + thumbnail visual |
| Motion | Ken Burns + clips | Static book visual + chapter-title overlay |
| Voice | Kokoro am_adam (English) | Kokoro Hindi (configurable, see below) |
| Topics | trends + 102-topic pool | 50-book rotation from `books.json` |
| Description | Short + tags | Full SEO + takeaways + chapters with timestamps + hashtags |
| Secrets | `YT_*` | `YT2_*` (separate channel) |
| Videos/day | 6 | `VIDEOS_PER_DAY` env (default 3) |

## Voice — IMPORTANT (2026-11-18)

The user **rejected ALL Kokoro Hindi voices** — `hm_omega`, `hm_psi`
and `hf_alpha` all sound robotic to him (`hm_omega` also had wrong
Hindi pronunciation). Kokoro Hindi stays in the chain only as a
fallback; never present any Kokoro Hindi voice as the approved primary.

**Current plan: ONE test video with Edge TTS Hindi
(`hi-IN-MadhurNeural`)** so he can judge it. Edge TTS cannot run from
this VM (proxy blocks `speech.platform.bing.com`) but works on GitHub
Actions runners. Build it with a manual workflow dispatch:

- `tts_engine` = `edge`
- `test_chapters` = `1` (builds only the first chapter, ~2 min — a
  quick voice test without a full 10-minute render)

or locally-equivalent env vars: `TTS_ENGINE=edge TEST_CHAPTERS=1`.

The Hindi voice is fully configurable via the `KOKORO_HINDI_VOICE`
env var / GitHub secret (default `hm_psi`, a placeholder). Fallback
chain: Kokoro Hindi → Edge `hi-IN-MadhurNeural` → gTTS `hi`.

**Measured pace (local test, Kokoro hm_psi): ~211 words/min** — 162
words took 46.1s. At that pace 1500 words ≈ 7 min, NOT 10 min. The
1500-word gate in `script_gen.py` is therefore likely too low; measure
the Edge pace from the test video and raise `MIN_WORDS` / the prompt
target (towards ~2100 words) if Edge is equally fast. The targets are
constants at the top of `script_gen.py` for exactly this adjustment.

## Files

- `books.json` — 50 books (English title, author, Hindi title, Hindi hook).
- `script_gen.py` — Gemini `gemini-3.5-flash-lite` writes a Hindi script:
  super hook + 6 chapters (200–300 words each), takeaway per chapter,
  title, SEO description draft, tags, thumbnail text, 2 AI image
  prompts. Word gate: ≥1500 to pass, keeps the longest ≥1200 after
  4 attempts.
- `tts.py` — Kokoro Hindi (`lang_code='h'`) primary, Edge Hindi fallback,
  gTTS `hi` last resort. One mp3 per chapter + `timings.json`.
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
- `YT2_CLIENT_ID`, `YT2_CLIENT_SECRET`, `YT2_REFRESH_TOKEN` — OAuth for
  the **Vedantic Psychology** channel (separate token: Playground auth
  selecting the Vedantic Psychology brand account; verify with a
  Playground "Refresh access token" 200 before storing, like the live
  pipeline). OAuth app must be in Production.
- `KOKORO_HINDI_VOICE` (optional) — the user's picked Kokoro Hindi voice.

## Quota warning

YouTube Data API quota is **per Google Cloud project, not per channel**.
If this channel shares the live pipeline's project, both channels
together may only upload **6 videos/day total** (9900/10000 units).
6+6/day needs a second Google Cloud project with its own OAuth client.

## Local dry-run test

```bash
cd ~/workspace/youtube-autopilot-vedantic
# venv with the project deps (the live pipeline's .venv has them):
~/workspace/youtube-autopilot/.venv/bin/python -m py_compile *.py
# TTS smoke test (Kokoro Hindi, uses .venv-kokoro):
~/workspace/youtube-autopilot/.venv-kokoro/bin/python tts.py "सोचो और अमीर बनो।"
# Full dry run with a fixture script (no Gemini key needed):
#   test_work/test_dryrun.py — builds a short video end to end with
#   DRY_RUN=1 and TEST_CHAPTERS=1 (the Edge voice-test mode).
# Real run (needs GEMINI_API_KEY + YT2_*):
GEMINI_API_KEY=... DRY_RUN=1 ~/workspace/youtube-autopilot/.venv-kokoro/bin/python run_one.py 0
# Edge Hindi voice test (GitHub Actions only — Edge is proxy-blocked here):
#   workflow_dispatch with tts_engine=edge, test_chapters=1.
# Locally, TTS_ENGINE=edge proves the forcing path (Edge fails on the
# proxy, gTTS catches it); on the runner Edge succeeds.
```

Note: the full pipeline needs `ffmpeg`, `espeak-ng` and the
`fonts-noto-core` package (Devanagari font for captions/thumbnails);
all three are installed on this VM and in the workflow.
