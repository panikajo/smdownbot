import asyncio
import os
import json
import re
import glob
import logging
from dataclasses import dataclass
from typing import Optional
from config import config
import shutil
import sys

logger = logging.getLogger("smdownbot.downloader")

# Find yt-dlp: prefer venv copy, fallback to system
YTDLP = os.path.join(os.path.dirname(sys.executable), "yt-dlp")
if not os.path.exists(YTDLP):
    YTDLP = shutil.which("yt-dlp") or "yt-dlp"


def _clean_source_url(u) -> str:
    """Strip tracking params and fragments from a media URL, keeping the
    canonical link.

    Instagram / TikTok carry the media id in the PATH, so the whole query
    string is junk and can be dropped:
        https://www.instagram.com/reel/DZaGtH9HY0S/?utm_source=ig_web_copy_link&igsh=...
            -> https://www.instagram.com/reel/DZaGtH9HY0S/
        https://www.tiktok.com/@user/video/12345?is_from_webapp=1
            -> https://www.tiktok.com/@user/video/12345

    YouTube /watch carries the id in the query (?v=...), so we keep only the
    'v' param and drop the rest (si, feature, list, t, etc.):
        https://www.youtube.com/watch?v=dQw4w9WgXcQ&feature=share -> ...?v=dQw4w9WgXcQ
        https://youtu.be/dQw4w9WgXcQ?si=abcd -> https://youtu.be/dQw4w9WgXcQ
    """
    if not u:
        return u
    if not isinstance(u, str):
        u = str(u)
    u = u.strip()

    try:
        from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
        parts = urlsplit(u)
        host = (parts.netloc or "").lower()
        # YouTube /watch keeps its id in ?v=
        if "youtube.com" in host and parts.path.rstrip("/") .endswith("/watch"):
            q = [(k, v) for k, v in parse_qsl(parts.query) if k == "v"]
            return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q), ""))
        # Everything else: id is in the path — drop query + fragment entirely.
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", ""))
    except Exception:
        # Fallback: naive trim at '?' / '#'
        for sep in ("?", "#"):
            idx = u.find(sep)
            if idx != -1:
                u = u[:idx]
        return u


def _sanitize_title(title) -> str:
    """Make a yt-dlp title safe for a Telegram HTML caption.
    Removes broken/surrogate code points that render as � and strips
    control chars. HTML-escaping is done at send time in the handler."""
    if not title:
        return "Download"
    if not isinstance(title, str):
        title = str(title)
    # Drop lone surrogates and re-decode to clean UTF-8
    title = title.encode("utf-8", "ignore").decode("utf-8", "ignore")
    # Remove control characters (except normal whitespace)
    title = "".join(ch for ch in title if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    title = title.strip()
    return title or "Download"


@dataclass
class DownloadResult:
    success: bool
    file_path: Optional[str] = None
    title: Optional[str] = None
    duration: Optional[int] = None
    file_size: Optional[int] = None
    thumbnail: Optional[str] = None
    platform: Optional[str] = None
    error: Optional[str] = None
    formats: Optional[list] = None
    source_url: Optional[str] = None
    uploader_id: Optional[str] = None
    tags: Optional[list] = None

def _base_opts(platform: str = None) -> dict:
    opts = {
        "quiet": True,
        "no-warnings": True,
        "no-playlist": True,
        "output": os.path.join(config.DOWNLOAD_DIR, "%(id)s.%(ext)s"),
        "socket-timeout": 30,
        "retries": 3,
    }
    # TikTok: do NOT attach cookies — yt-dlp's challenge solver sets its own
    # short-lived cookies, and user cookies break them (causes
    # "Unable to extract universal data for rehydration").
    cookie_file = os.path.join(config.COOKIES_DIR, f"{platform}.txt")
    if platform != "tiktok" and os.path.exists(cookie_file):
        opts["cookies"] = cookie_file
    return opts

def _is_auth_error(stderr: str) -> bool:
    """Check if error indicates expired/invalid cookies."""
    auth_patterns = [
        "You need to log in",
        "login required",
        "authentication",
        "HTTP Error 401",
        "HTTP Error 403",
        "Private content",
    ]
    lower = stderr.lower()
    return any(p.lower() in lower for p in auth_patterns)


async def get_info(url: str, platform: str = None, _retry: bool = True) -> Optional[dict]:
    """Get video info without downloading."""
    cmd = [YTDLP, "--dump-json", "--no-download", "--no-playlist"]

    # Only pass CLI-compatible options.
    # Skip cookies for TikTok — they break yt-dlp's challenge solver.
    cookie_file = os.path.join(config.COOKIES_DIR, f"{platform}.txt")
    if platform != "tiktok" and os.path.exists(cookie_file):
        cmd.extend(["--cookies", cookie_file])

    cmd.append(url)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)
    if proc.returncode != 0:
        err = stderr.decode("utf-8", "replace")
        if _retry and platform == "instagram" and _is_auth_error(err):
            logger.info("Auth error in get_info, auto-refreshing cookies...")
            from services.cookies import handle_auth_failure
            if await handle_auth_failure():
                return await get_info(url, platform, _retry=False)
        return None
    try:
        return json.loads(stdout.decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return None

async def download(url: str, platform: str = None, audio_only: bool = False, quality: str = "best") -> DownloadResult:
    """Download video/audio via yt-dlp."""
    os.makedirs(config.DOWNLOAD_DIR, exist_ok=True)
    opts = _base_opts(platform)

    if audio_only:
        opts.update({
            "format": "bestaudio/best",
            "extract-audio": True,
            "audio-format": "mp3",
            "audio-quality": "192",
        })
    else:
        if quality == "720":
            opts["format"] = "bestvideo[height<=720]+bestaudio/best[height<=720]/best"
        elif quality == "480":
            opts["format"] = "bestvideo[height<=480]+bestaudio/best[height<=480]/best"
        else:
            opts["format"] = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best"

    # TikTok: prefer no-watermark
    if platform == "tiktok":
        opts["format"] = "best"

    # Build command
    cmd = [YTDLP]
    for k, v in opts.items():
        flag = f"--{k.replace('_', '-')}"
        if isinstance(v, bool):
            if v:
                cmd.append(flag)
        elif isinstance(v, (str, int, float)):
            cmd.extend([flag, str(v)])
        elif isinstance(v, list):
            for item in v:
                cmd.extend([flag, json.dumps(item) if isinstance(item, dict) else str(item)])
        elif isinstance(v, dict):
            for dk, dv in v.items():
                cmd.extend([f"--{dk}", str(dv)])

    # Use a unique output template based on the video id so we can reliably
    # locate the file afterwards even when yt-dlp's after_move print is empty
    # (happens for single-file TikTok downloads that skip the merge/move step).
    cmd.extend([
        "--print", "after_move:filepath",
        "--print", "after_move:%(title)s",
        "--print", "after_move:%(duration)s",
        "--print", "after_move:%(thumbnail)s",
        "--print", "after_move:%(webpage_url)s",
        "--print", "after_move:%(uploader_id)s",
        "--print", "after_move:%(uploader)s",
        "--print", "after_move:%(tags)j",
        "--no-simulate",
    ])
    cmd.append(url)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=config.YT_DLP_TIMEOUT
    )

    if proc.returncode != 0:
        err = stderr.decode("utf-8", "replace").strip().split("\n")[-1]
        # Auto-refresh cookies on auth failure
        if platform == "instagram" and _is_auth_error(err):
            logger.info("Auth error in download, auto-refreshing cookies...")
            from services.cookies import handle_auth_failure
            if await handle_auth_failure():
                # Retry download with fresh cookies
                cookie_file = os.path.join(config.COOKIES_DIR, f"{platform}.txt")
                if os.path.exists(cookie_file):
                    opts["cookies"] = cookie_file
                    cmd = [YTDLP]
                    for k, v in opts.items():
                        flag = f"--{k.replace('_', '-')}"
                        if isinstance(v, bool):
                            if v:
                                cmd.append(flag)
                        elif isinstance(v, (str, int, float)):
                            cmd.extend([flag, str(v)])
                        elif isinstance(v, list):
                            for item in v:
                                cmd.extend([flag, json.dumps(item) if isinstance(item, dict) else str(item)])
                        elif isinstance(v, dict):
                            for dk, dv in v.items():
                                cmd.extend([f"--{dk}", str(dv)])
                    cmd.extend(["--print", "after_move:filepath"])
                    cmd.append(url)

                    proc = await asyncio.create_subprocess_exec(
                        *cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    stdout, stderr = await asyncio.wait_for(
                        proc.communicate(), timeout=config.YT_DLP_TIMEOUT
                    )
                    if proc.returncode == 0:
                        filepath = stdout.decode("utf-8", "replace").strip().split("\n")[-1]
                        if os.path.exists(filepath):
                            file_size = os.path.getsize(filepath)
                            info = await get_info(url, platform, _retry=False)
                            return DownloadResult(
                                success=True,
                                file_path=filepath,
                                title=_sanitize_title(info.get("title", "Download") if info else "Download")[:100],
                                duration=info.get("duration") if info else None,
                                file_size=file_size,
                                thumbnail=info.get("thumbnail") if info else None,
                                platform=platform,
                            )
                    err = stderr.decode("utf-8", "replace").strip().split("\n")[-1]
        return DownloadResult(success=False, error=err[:200])

    # Capture full stderr so failures show the real yt-dlp reason instead of
    # a generic "File not found".
    full_stderr = stderr.decode("utf-8", "replace").strip()
    out_lines = [ln for ln in stdout.decode("utf-8", "replace").strip().split("\n") if ln.strip()]

    # Resolve the downloaded file. The first non-empty stdout line should be the
    # filepath from --print after_move:filepath, but for some extractors (TikTok
    # single-file, no post-processing) after_move can print an empty/old path.
    # Fall back to globbing the download dir for the video id from the URL.
    def _resolve_filepath():
        if out_lines and os.path.exists(out_lines[0]):
            return out_lines[0]
        # Fallback: find by video id in the output dir
        m = re.search(r"/video/(\d+)|/(\d{8,})", url) or re.search(r"(\d{8,})", url)
        vid = next((g for g in (m.groups() if m else []) if g), None)
        if vid:
            matches = glob.glob(os.path.join(config.DOWNLOAD_DIR, f"{vid}.*"))
            if matches:
                return max(matches, key=os.path.getmtime)
        # Last resort: newest file in the download dir created just now
        all_files = glob.glob(os.path.join(config.DOWNLOAD_DIR, "*"))
        if all_files:
            newest = max(all_files, key=os.path.getmtime)
            import time as _t
            if _t.time() - os.path.getmtime(newest) < config.YT_DLP_TIMEOUT:
                return newest
        return None

    filepath = _resolve_filepath()
    if not filepath or not os.path.exists(filepath):
        # yt-dlp may have exited 0 but produced no file (e.g. extractor warning).
        reason = full_stderr.split("\n")[-1] if full_stderr else "File not found after download"
        return DownloadResult(success=False, error=reason[:200])

    file_size = os.path.getsize(filepath)

    # Parse metadata printed in the SAME yt-dlp pass.
    # out_lines layout (in --print order):
    #   [filepath, title, duration, thumbnail, webpage_url, uploader_id, uploader, tags_json]
    title = "Download"
    duration = None
    thumbnail = None
    source_url = None
    uploader_id = None
    tags = None

    def _na(v):
        v = (v or "").strip()
        return None if v in ("", "NA", "None") else v

    if len(out_lines) >= 8:
        title = _sanitize_title(out_lines[1] or "Download")
        dur_raw = (out_lines[2] or "").strip()
        try:
            duration = int(float(dur_raw)) if dur_raw and dur_raw != "NA" else None
        except ValueError:
            duration = None
        thumbnail = _na(out_lines[3])
        source_url = _clean_source_url(_na(out_lines[4]))
        uploader_id = _na(out_lines[5])
        # tags printed as a JSON array via %(tags)j
        try:
            parsed = json.loads(out_lines[7]) if out_lines[7] else None
            if isinstance(parsed, list):
                tags = [str(t) for t in parsed if t]
        except (json.JSONDecodeError, IndexError):
            tags = None
    elif len(out_lines) >= 4:
        # Older/partial print (fallback): [filepath, title, duration, thumbnail]
        title = _sanitize_title(out_lines[-3] or "Download")
        dur_raw = out_lines[-2].strip()
        try:
            duration = int(float(dur_raw)) if dur_raw and dur_raw != "NA" else None
        except ValueError:
            duration = None
        thumbnail = _na(out_lines[-1])

    # Fallback: derive source_url / uploader_id from the original URL for TikTok/IG
    if not source_url:
        source_url = url
    source_url = _clean_source_url(source_url)
    if not uploader_id:
        m = re.search(r"(?:tiktok\.com|instagram\.com)/@?([\w.]+)", url)
        if m:
            uploader_id = m.group(1)

    return DownloadResult(
        success=True,
        file_path=filepath,
        title=_sanitize_title(title)[:100],
        duration=duration,
        file_size=file_size,
        thumbnail=thumbnail,
        platform=platform,
        source_url=source_url,
        uploader_id=uploader_id,
        tags=tags,
    )

def cleanup_file(path: str):
    """Delete downloaded file."""
    try:
        if path and os.path.exists(path):
            os.remove(path)
    except OSError:
        pass

def cleanup_old_files(max_age_hours: int = 1):
    """Clean files older than max_age_hours."""
    import time
    now = time.time()
    cutoff = now - (max_age_hours * 3600)
    for f in glob.glob(os.path.join(config.DOWNLOAD_DIR, "*")):
        if os.path.getmtime(f) < cutoff:
            try:
                os.remove(f)
            except OSError:
                pass


def split_video(file_path: str, max_size_mb: int = 48) -> list[str]:
    """Split a video into parts that fit under max_size_mb.
    Returns list of part file paths."""
    import subprocess
    
    file_size = os.path.getsize(file_path)
    max_bytes = max_size_mb * 1024 * 1024
    
    if file_size <= max_bytes:
        return [file_path]
    
    # Get video duration
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", file_path],
        capture_output=True, text=True
    )
    duration = float(result.stdout.strip())
    
    # Calculate number of parts needed
    num_parts = int(file_size / max_bytes) + 1
    segment_duration = duration / num_parts
    
    # Split using ffmpeg
    base, ext = os.path.splitext(file_path)
    pattern = f"{base}_part%d{ext}"
    
    subprocess.run([
        "ffmpeg", "-i", file_path,
        "-c", "copy",
        "-f", "segment",
        "-segment_time", str(segment_duration),
        "-reset_timestamps", "1",
        pattern
    ], capture_output=True, check=True)
    
    # Collect part files
    parts = sorted(glob.glob(f"{base}_part*{ext}"))
    return parts if parts else [file_path]
