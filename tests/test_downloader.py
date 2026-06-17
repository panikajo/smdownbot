import pytest
from services.platform import detect_platform, get_platform_info


class TestPlatformDetection:
    def test_youtube_watch(self):
        result = detect_platform("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
        assert result is not None
        assert result[0] == "youtube"
        assert result[1] == "dQw4w9WgXcQ"

    def test_youtube_short(self):
        result = detect_platform("https://youtu.be/dQw4w9WgXcQ")
        assert result is not None
        assert result[0] == "youtube"

    def test_youtube_shorts(self):
        result = detect_platform("https://www.youtube.com/shorts/abc123")
        assert result is not None
        assert result[0] == "youtube"

    def test_instagram_reel(self):
        result = detect_platform("https://www.instagram.com/reel/Cx1234abcd/")
        assert result is not None
        assert result[0] == "instagram"

    def test_instagram_post(self):
        result = detect_platform("https://www.instagram.com/p/Cx1234abcd/")
        assert result is not None
        assert result[0] == "instagram"

    def test_instagram_story(self):
        result = detect_platform("https://www.instagram.com/stories/dr_tompi/3913401630049724573?utm_source=ig_story_item_share&igsh=enVkcmdqenVuenpl")
        assert result is not None
        assert result[0] == "instagram"
        assert result[1] == "3913401630049724573"

    def test_tiktok_video(self):
        result = detect_platform("https://www.tiktok.com/@user/video/7123456789")
        assert result is not None
        assert result[0] == "tiktok"

    def test_tiktok_short(self):
        result = detect_platform("https://vm.tiktok.com/ZMabcdef/")
        assert result is not None
        assert result[0] == "tiktok"

    def test_unknown_url(self):
        result = detect_platform("https://example.com/video/123")
        assert result is not None
        assert result[0] == "unknown"

    def test_not_url(self):
        result = detect_platform("hello world no link here")
        assert result is None

    def test_platform_info(self):
        info = get_platform_info("youtube")
        assert info.name == "YouTube"
        assert info.supports_audio is True

    def test_unknown_platform_info(self):
        info = get_platform_info("foobar")
        assert info.name == "Unknown"
