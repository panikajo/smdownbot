"""Automatic Instagram cookie refresh via Playwright."""
import asyncio
import logging
import os
from config import config

logger = logging.getLogger("smdownbot.cookies")

_refresh_lock = asyncio.Lock()
_last_refresh = 0
COOLDOWN = 300  # 5 min cooldown between refresh attempts


async def are_cookies_valid() -> bool:
    """Quick check if Instagram cookies are still valid."""
    cookie_file = os.path.join(config.COOKIES_DIR, "instagram.txt")
    if not os.path.exists(cookie_file):
        return False

    import yt_dlp
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "cookies": cookie_file,
            "extract_flat": True,
            "no_download": True,
        }
        # Try fetching a known public account's stories
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info("https://www.instagram.com/stories/instagram/", download=False)
            if info and info.get("entries"):
                return True
    except Exception:
        pass
    return False


async def refresh_cookies() -> bool:
    """Re-login to Instagram with Playwright. Returns True if successful."""
    global _last_refresh
    import time

    # Cooldown check
    if time.time() - _last_refresh < COOLDOWN:
        logger.info("Cookie refresh on cooldown, skipping")
        return False

    async with _refresh_lock:
        # Double-check cooldown inside lock
        if time.time() - _last_refresh < COOLDOWN:
            return False

        logger.info("Refreshing Instagram cookies via Playwright...")
        _last_refresh = time.time()

        try:
            result = await asyncio.get_event_loop().run_in_executor(
                None, _login_sync
            )
            if result:
                logger.info("Instagram cookies refreshed successfully!")
                return True
            else:
                logger.error("Instagram cookie refresh failed")
                return False
        except Exception as e:
            logger.error(f"Cookie refresh error: {e}")
            return False


def _login_sync() -> bool:
    """Synchronous Playwright login. Runs in thread executor."""
    from playwright.sync_api import sync_playwright

    cookie_file = os.path.join(config.COOKIES_DIR, "instagram.txt")
    email = os.getenv("IG_EMAIL", "dhiklydotcom@gmail.com")
    password = os.getenv("IG_PASSWORD", "indonesiaku123")

    try:
        with sync_playwright() as p:
            browser = p.firefox.launch(headless=True)
            page = browser.new_page()

            page.goto("https://www.instagram.com/accounts/login/", timeout=30000)
            page.wait_for_selector('input[name="email"]', timeout=10000)

            page.fill('input[name="email"]', email)
            page.fill('input[name="pass"]', password)

            import time
            time.sleep(1)

            # Click the Log in div button
            login_btn = page.locator('div[role="button"]:has-text("Log in")').first
            login_btn.click()

            # Wait for navigation (onetap or home page)
            time.sleep(8)

            # Save cookies
            cookies = page.context.cookies()
            has_session = any(c["name"] == "sessionid" for c in cookies)
            has_user = any(c["name"] == "ds_user_id" for c in cookies)

            if has_session and has_user:
                with open(cookie_file, "w") as f:
                    f.write("# Netscape HTTP Cookie File\n# Auto-refreshed by smdownbot\n\n")
                    for c in cookies:
                        domain = c.get("domain", "")
                        if not domain.startswith("."):
                            domain = "." + domain
                        f.write(
                            f"{domain}\tTRUE\t{c.get('path', '/')}\t"
                            f"{'TRUE' if c.get('secure') else 'FALSE'}\t"
                            f"{int(c.get('expires', 0))}\t"
                            f"{c['name']}\t{c['value']}\n"
                        )
                browser.close()
                return True

            browser.close()
            return False

    except Exception as e:
        logger.error(f"Playwright login failed: {e}")
        return False


async def ensure_cookies() -> bool:
    """Ensure cookies are valid. Refresh if needed. Returns True if cookies are good."""
    cookie_file = os.path.join(config.COOKIES_DIR, "instagram.txt")

    # If no cookies at all, refresh immediately
    if not os.path.exists(cookie_file):
        return await refresh_cookies()

    return True  # Cookies exist, assume valid (will be caught on download failure)


async def handle_auth_failure() -> bool:
    """Called when a download fails with auth error. Auto-refreshes cookies."""
    logger.info("Auth failure detected, auto-refreshing cookies...")
    return await refresh_cookies()
