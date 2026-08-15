"""Classify stored livecam URLs. Photo CDNs are previews, not CCTV."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

PHOTO_HINTS = (
    "picsum.photos",
    "unsplash.com",
    "images.unsplash",
    "tong.visitkorea.or.kr",
)
LIVE_HINTS = (".m3u8", ".mp4", "youtube.com", "youtu.be", "vimeo.com")


def _youtube_id(url: str) -> str:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host in {"youtu.be", "www.youtu.be"}:
        return parsed.path.strip("/")
    if "youtube.com" in host:
        if parsed.path.startswith("/embed/"):
            return parsed.path.split("/embed/", 1)[-1].split("/", 1)[0]
        if parsed.path.startswith("/live/"):
            return parsed.path.split("/live/", 1)[-1].split("/", 1)[0]
        return (parse_qs(parsed.query).get("v") or [""])[0]
    return ""


def is_live_stream(url: str) -> bool:
    text = (url or "").strip().lower()
    if not text:
        return False
    if any(hint in text for hint in PHOTO_HINTS):
        return False
    return any(hint in text for hint in LIVE_HINTS)


def embed_url(url: str) -> str:
    raw = (url or "").strip()
    if not raw:
        return ""
    video_id = _youtube_id(raw)
    if video_id:
        return f"https://www.youtube.com/embed/{video_id}?autoplay=1&mute=1"
    if is_live_stream(raw):
        return raw
    return ""


def livecam_payload(url: str) -> dict:
    raw = (url or "").strip()
    live = is_live_stream(raw)
    return {
        "url": raw,
        "is_live": live,
        "embed_url": embed_url(raw) if live else "",
    }
