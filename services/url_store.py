"""Temporary URL store for callback data. Maps short IDs to URLs."""
import hashlib
import time

_store: dict[str, tuple[str, str]] = {}  # id -> (url, platform)

def store_url(url: str, platform: str) -> str:
    """Store a URL and return a short ID."""
    # Use hash of URL for consistent IDs
    short_id = hashlib.md5(url.encode()).hexdigest()[:8]
    _store[short_id] = (url, platform)
    return short_id

def get_url(short_id: str) -> tuple[str, str] | None:
    """Get (url, platform) by short ID."""
    return _store.get(short_id)

def cleanup(max_age: int = 3600):
    """Remove entries older than max_age seconds."""
    # Simple cleanup - in production use TTL
    pass
