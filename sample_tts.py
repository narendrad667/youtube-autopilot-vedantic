"""One-off voice sampler for the Vedantic Psychology pipeline.

Calls the Gemini API's native text-to-speech (Flash TTS models, free of
charge on the free tier with the same GEMINI_API_KEY the pipeline
already uses) and saves one mp3 per voice, so the user can judge which
Hindi voice sounds natural instead of robotic.

Usage (GitHub Actions workflow_dispatch, or locally with a key):
  python sample_tts.py [--model gemini-3.8-flash-tts]
                       [--voices Kore,Charon,Aoede]
                       [--out out_tts]

Env: GEMINI_API_KEY (required).

Notes:
- Model fallback: if the requested model 404s (retired), the script
  tries gemini-3.1-flash-tts-preview, then gemini-2.5-flash-preview-tts.
- The API returns raw 16-bit PCM at 24 kHz (base64). This script writes
  a proper .wav with the stdlib `wave` module, then converts to mp3
  with ffmpeg (installed on the runner by the workflow).
- Same sample text as the earlier Kokoro/Edge samples, so voices can be
  compared fairly.
"""
import base64
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
import wave

SAMPLE_TEXT = (
    "नमस्कार दोस्तों। आज हम बात करेंगे ध्यान के बारे में। "
    "जब मन शांत होता है, तो जिंदगी बदल जाती है। "
    "एक छोटी सी आदत भी बड़ा बदलाव ला सकती है।"
)

MODEL_FALLBACKS = [
    "gemini-3.8-flash-tts",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-preview-tts",
]


def synth(api_key, model, voice, text):
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/%s"
        ":generateContent?key=%s" % (model, api_key)
    )
    body = json.dumps({
        "contents": [{"parts": [{"text": text}]}],
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


def pcm_to_mp3(pcm_bytes, mp3_path):
    wav_path = mp3_path + ".wav"
    with wave.open(wav_path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24000)
        w.writeframes(pcm_bytes)
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", wav_path, mp3_path],
        check=True)
    os.remove(wav_path)
    return os.path.getsize(mp3_path)


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default="gemini-3.8-flash-tts")
    ap.add_argument("--voices", default="Kore,Charon,Aoede")
    ap.add_argument("--out", default="out_tts")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        sys.exit("GEMINI_API_KEY is not set.")
    os.makedirs(args.out, exist_ok=True)

    models = [args.model] + [m for m in MODEL_FALLBACKS if m != args.model]
    for voice in [v.strip() for v in args.voices.split(",") if v.strip()]:
        pcm = None
        used_model = None
        last_err = ""
        for model in models:
            try:
                pcm = synth(api_key, model, voice, SAMPLE_TEXT)
                used_model = model
                break
            except Exception as e:
                last_err = str(e)
                print("  %s with %s failed: %s" % (voice, model, last_err))
        if pcm is None:
            print("FAILED voice %s: %s" % (voice, last_err))
            continue
        mp3_path = os.path.join(args.out, "gemini_tts_%s.mp3" % voice.lower())
        size = pcm_to_mp3(pcm, mp3_path)
        print("OK voice=%s model=%s file=%s bytes=%d duration~%.1fs"
              % (voice, used_model, mp3_path, size, len(pcm) / 2 / 24000))


if __name__ == "__main__":
    main()
