import asyncio
from typing import Optional

# Track active downloads per user to prevent spam
_active_downloads: dict[int, asyncio.Task] = {}

def set_active(user_id: int, task: asyncio.Task):
    _active_downloads[user_id] = task

def get_active(user_id: int) -> Optional[asyncio.Task]:
    return _active_downloads.get(user_id)

def clear_active(user_id: int):
    _active_downloads.pop(user_id, None)

def is_downloading(user_id: int) -> bool:
    task = _active_downloads.get(user_id)
    return task is not None and not task.done()

def cancel_download(user_id: int) -> bool:
    task = _active_downloads.get(user_id)
    if task and not task.done():
        task.cancel()
        clear_active(user_id)
        return True
    return False
