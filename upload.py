"""YouTube upload for the Vedantic Psychology autopilot — YouTube Data
API v3, free quota.

Quota: videos.insert = 1600 units, thumbnails.set = 50 units.
With VIDEOS_PER_DAY=3: 3 x 1600 + 3 x 50 = 4950/10000 on this channel's
own project — but NOTE: the quota is per Google Cloud project, NOT per
channel. If this channel shares the live pipeline's project, the two
channels together may only upload 6 videos/day total (9900/10000).
6+6/day needs a second Google Cloud project with its own OAuth client.
Auth: OAuth2 refresh token from env (YT2_CLIENT_ID, YT2_CLIENT_SECRET,
YT2_REFRESH_TOKEN) — separate secrets from the live pipeline (YT_*).
The OAuth app MUST be in Production in Google Cloud — in Testing mode
the refresh token expires after 7 days.
Scope used: https://www.googleapis.com/auth/youtube.upload (covers upload
and thumbnails.set).

Publish timing: videos are uploaded as private with a publishAt time
(staggered through the day). If the channel cannot schedule (unverified
account), the API rejects publishAt and we fall back to public immediately.

Description: full SEO in Hindi — hook + what the video covers + key
takeaways, a CHAPTERS section with timestamps, hashtags (always
including #VedanticPsychology), and a short English line for search.
"""
import os
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
CATEGORY_EDUCATION = "27"  # book summaries / explainers fit Education best
CHANNEL_HASHTAG = "VedanticPsychology"


def get_service():
    creds = Credentials(
        token=None,
        refresh_token=os.environ["YT2_REFRESH_TOKEN"],
        client_id=os.environ["YT2_CLIENT_ID"],
        client_secret=os.environ["YT2_CLIENT_SECRET"],
        token_uri=TOKEN_URI,
        scopes=SCOPES)
    creds.refresh(Request())
    return build("youtube", "v3", credentials=creds)


def _fmt_chapter_time(seconds):
    """Seconds -> MM:SS (or H:MM:SS past one hour) for the description."""
    s = int(seconds)
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    if h:
        return "%d:%02d:%02d" % (h, m, s)
    return "%02d:%02d" % (m, s)


def _clean_hashtag(tag):
    """Make a tag safe as a YouTube hashtag: strip spaces and punctuation
    except Devanagari/letters/digits. Returns None if nothing is left."""
    tag = re.sub(r"[\s#]+", "", tag or "")
    tag = re.sub(r"[^\w\u0900-\u097F]", "", tag, flags=re.UNICODE)
    return tag or None


def build_description(script, book, chapter_starts):
    """Build the full SEO description.

    script: the script dict (description, tags, chapters with takeaways).
    book: the books.json entry (title_en, author, title_hi).
    chapter_starts: [(title, start_seconds)] for the CHAPTERS section.
    Layout: Hindi hook + what you learn + takeaways + chapters with
    timestamps + hashtags + one English line for search."""
    lines = []
    lines.append(script.get("description", "").strip())
    lines.append("")
    lines.append("इस वीडियो में आप सीखेंगे:")
    for ch in script.get("chapters", []):
        takeaway = (ch.get("takeaway") or "").strip()
        if takeaway:
            lines.append("• " + takeaway)
    lines.append("")
    lines.append("अध्याय (Chapters):")
    for title, start in chapter_starts:
        lines.append("%s - %s" % (_fmt_chapter_time(start), title))
    lines.append("")
    tags = []
    for t in script.get("tags", []):
        clean = _clean_hashtag(t)
        if clean and clean not in tags:
            tags.append(clean)
    if CHANNEL_HASHTAG not in tags:
        tags.insert(0, CHANNEL_HASHTAG)
    lines.append(" ".join("#" + t for t in tags[:12]))
    lines.append("")
    lines.append("Book summary in Hindi | %s by %s | Vedantic Psychology"
                 % (book["title_en"], book["author"]))
    lines.append("यह वीडियो \"%s\" किताब का मूल सारांश है — किताब के "
                 "विचारों को अपने शब्दों में सरल हिंदी में समझाया गया है।"
                 % book["title_en"])
    return "\n".join(lines)


def upload_video(service, video_path, title, description, tags,
                 publish_at=None, category_id=CATEGORY_EDUCATION):
    """Upload one video. Returns the YouTube video id."""
    body = {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags[:30],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": "private" if publish_at else "public",
            "selfDeclaredMadeForKids": False,
        },
    }
    if publish_at:
        body["status"]["publishAt"] = publish_at
    media = MediaFileUpload(video_path, mimetype="video/mp4",
                            chunksize=8 * 1024 * 1024, resumable=True)
    try:
        req = service.videos().insert(part="snippet,status", body=body,
                                      media_body=media)
        resp = None
        while resp is None:
            _, resp = req.next_chunk()
        video_id = resp["id"]
        print("Uploaded: %s -> https://youtu.be/%s" % (title, video_id))
        return video_id
    except HttpError as e:
        # Scheduling needs a verified channel; fall back to public now.
        if publish_at and e.resp.status in (400, 403):
            print("publishAt rejected (%s) — retrying as public now."
                  % e.resp.status)
            body["status"].pop("publishAt", None)
            body["status"]["privacyStatus"] = "public"
            media = MediaFileUpload(video_path, mimetype="video/mp4",
                                    chunksize=8 * 1024 * 1024, resumable=True)
            req = service.videos().insert(part="snippet,status", body=body,
                                          media_body=media)
            resp = None
            while resp is None:
                _, resp = req.next_chunk()
            video_id = resp["id"]
            print("Uploaded (public): %s -> https://youtu.be/%s"
                  % (title, video_id))
            return video_id
        raise


def set_thumbnail(service, video_id, thumb_path):
    """Upload the thumbnail (50 quota units). Non-fatal if it fails."""
    try:
        media = MediaFileUpload(thumb_path, mimetype="image/jpeg",
                                resumable=False)
        service.thumbnails().set(videoId=video_id,
                                 media_body=media).execute()
        print("Thumbnail set for %s" % video_id)
        return True
    except HttpError as e:
        print("Thumbnail failed (non-fatal): %s" % e)
        return False


def upload_full(video_path, thumb_path, title, description, tags,
                publish_at=None):
    """Upload + thumbnail in one call. Returns (video_id, url)."""
    service = get_service()
    video_id = upload_video(service, video_path, title, description, tags,
                            publish_at=publish_at)
    if thumb_path and os.path.exists(thumb_path):
        set_thumbnail(service, video_id, thumb_path)
    return video_id, "https://youtu.be/" + video_id


if __name__ == "__main__":
    import sys
    vid, url = upload_full(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None,
                           sys.argv[3] if len(sys.argv) > 3 else "Test upload",
                           "Test description", ["test"])
    print(url)
