import re
from dataclasses import dataclass
from typing import Optional

@dataclass
class PlatformInfo:
    name: str
    icon: str
    supports_audio: bool = True
    supports_quality: bool = True
    note: str = ""

PATTERNS = {
    "youtube": [
        r"(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/shorts/|youtube\.com/embed/)([\w-]+)",
    ],
    "instagram": [
        r"instagram\.com/(?:p|reel|reels)/([\w-]+)",
        r"instagram\.com/stories/[\w.]+/(\d+)",
        r"instagram\.com/stories/([\w.]+)/?$",
    ],
    "tiktok": [
        r"(?:tiktok\.com/@[\w.]+/video/|vm\.tiktok\.com/|vt\.tiktok\.com/)([\w-]+)",
    ],
}

PLATFORM_META = {
    "youtube": PlatformInfo("YouTube", "🔴", supports_audio=True, supports_quality=True),
    "instagram": PlatformInfo("Instagram", "📸", supports_audio=False, supports_quality=False),
    "tiktok": PlatformInfo("TikTok", "🎵", supports_audio=True, supports_quality=False, note="No-watermark available"),
}

def detect_platform(url: str) -> Optional[tuple[str, str]]:
    """Returns (platform_key, video_id) or None."""
    url = url.strip()
    for platform, patterns in PATTERNS.items():
        for pattern in patterns:
            m = re.search(pattern, url)
            if m:
                return platform, m.group(1)
    # Fallback: if it looks like a URL, let yt-dlp try it
    if re.match(r"https?://", url):
        return "unknown", ""
    return None

def get_platform_info(platform: str) -> PlatformInfo:
    return PLATFORM_META.get(platform, PlatformInfo("Unknown", "🌐", supports_audio=False, supports_quality=False))
