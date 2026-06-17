"""Bulk Instagram stories download."""
import asyncio
import json
import os
from dataclasses import dataclass
from config import config

YTDLP = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".venv", "bin", "yt-dlp")
if not os.path.exists(YTDLP):
    import shutil
    YTDLP = shutil.which("yt-dlp") or "yt-dlp"


@dataclass
class StoryItem:
    id: str
    title: str
    duration: float = 0
    index: int = 0  # 1-based playlist index


async def get_stories_list(username_url: str) -> list[StoryItem]:
    """Get list of available stories for a user using --flat-playlist."""
    cookie_file = os.path.join(config.COOKIES_DIR, "instagram.txt")
    cmd = [YTDLP, "--dump-json", "--flat-playlist", "--no-download"]
    if os.path.exists(cookie_file):
        cmd.extend(["--cookies", cookie_file])
    cmd.append(username_url)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=60)

    if proc.returncode != 0:
        return []

    stories = []
    for i, line in enumerate(stdout.decode("utf-8", "replace").strip().split("\n"), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            stories.append(StoryItem(
                id=data.get("id", ""),
                title=data.get("title", "Story"),
                duration=data.get("duration", 0),
                index=i,
            ))
        except json.JSONDecodeError:
            continue
    return stories


async def download_story_by_index(stories_url: str, index: int) -> dict:
    """Download a single story by its playlist index (1-based).
    
    Uses --playlist-items to pick the exact story from the playlist,
    which avoids the bug where media IDs don't resolve individually.
    Returns {success, file_path, title, file_size, duration, error}.
    """
    from services.downloader import DownloadResult

    cookie_file = os.path.join(config.COOKIES_DIR, "instagram.txt")
    out_dir = os.path.abspath(config.DOWNLOAD_DIR)
    os.makedirs(out_dir, exist_ok=True)
    out_tpl = os.path.join(out_dir, f"story_{index}_%(id)s.%(ext)s")

    cmd = [
        YTDLP,
        "--playlist-items", str(index),
        "-o", out_tpl,
        "--no-warnings",
        "--no-playlist",
    ]
    if os.path.exists(cookie_file):
        cmd.extend(["--cookies", cookie_file])
    cmd.append(stories_url)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(), timeout=config.YT_DLP_TIMEOUT
    )

    if proc.returncode != 0:
        err = stderr.decode("utf-8", "replace").strip().split("\n")[-1] if stderr else "Unknown error"
        return {
            "success": False, "file_path": None, "title": None,
            "file_size": 0, "duration": 0, "error": err,
        }

    # Find the downloaded file
    import glob
    pattern = os.path.join(out_dir, f"story_{index}_*")
    files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
    if not files:
        return {
            "success": False, "file_path": None, "title": None,
            "file_size": 0, "duration": 0, "error": "Downloaded file not found",
        }

    file_path = files[0]
    file_size = os.path.getsize(file_path)

    # Try to extract metadata from yt-dlp JSON output
    title = None
    duration = 0
    for line in stdout.decode("utf-8", "replace").strip().split("\n"):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
            title = title or data.get("title")
            duration = duration or data.get("duration", 0)
        except json.JSONDecodeError:
            continue

    return {
        "success": True,
        "file_path": file_path,
        "title": title or "Story",
        "file_size": file_size,
        "duration": duration,
        "error": None,
    }
