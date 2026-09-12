import pytest
from app.services.youtube_intelligence import YouTubeIntelligence


def test_extract_video_id_standard():
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
    assert YouTubeIntelligence.extract_video_id(url) == "jNQXAC9IVRw"


def test_extract_video_id_short():
    url = "https://youtu.be/jNQXAC9IVRw"
    assert YouTubeIntelligence.extract_video_id(url) == "jNQXAC9IVRw"


def test_extract_video_id_shorts():
    url = "https://www.youtube.com/shorts/jNQXAC9IVRw"
    assert YouTubeIntelligence.extract_video_id(url) == "jNQXAC9IVRw"


def test_extract_video_id_embed():
    url = "https://www.youtube.com/embed/jNQXAC9IVRw"
    assert YouTubeIntelligence.extract_video_id(url) == "jNQXAC9IVRw"


def test_extract_video_id_with_timestamp_and_extra_params():
    url = "https://www.youtube.com/watch?v=jNQXAC9IVRw&feature=youtu.be&t=15s"
    assert YouTubeIntelligence.extract_video_id(url) == "jNQXAC9IVRw"


def test_extract_video_id_direct_string():
    assert YouTubeIntelligence.extract_video_id("jNQXAC9IVRw") == "jNQXAC9IVRw"


def test_extract_video_id_invalid():
    assert YouTubeIntelligence.extract_video_id("https://google.com") is None
    assert YouTubeIntelligence.extract_video_id("not_a_valid_id") is None


def test_contains_youtube_link():
    assert YouTubeIntelligence.contains_youtube_link("Can you summarize https://www.youtube.com/watch?v=jNQXAC9IVRw?") is True
    assert YouTubeIntelligence.contains_youtube_link("Check out https://youtu.be/jNQXAC9IVRw please") is True
    assert YouTubeIntelligence.contains_youtube_link("Look at this https://www.youtube.com/shorts/12345678901") is True
    assert YouTubeIntelligence.contains_youtube_link("Hello world, no video here") is False


def test_format_transcript_for_prompt():
    segments = [
        {"start": 0.0, "duration": 2.5, "text": "Hello world."},
        {"start": 2.5, "duration": 3.0, "text": "Welcome to the demonstration."},
    ]
    metadata = {
        "title": "Test Video Title",
        "author_name": "Test Creator",
        "author_url": "https://youtube.com/@test",
    }
    formatted = YouTubeIntelligence.format_transcript_for_prompt(
        video_id="jNQXAC9IVRw",
        transcript_segments=segments,
        metadata=metadata,
    )
    assert "Test Video Title" in formatted
    assert "Test Creator" in formatted
    assert "[00:00] Hello world. Welcome to the demonstration." in formatted


@pytest.mark.asyncio
async def test_process_youtube_url_live():
    # Video jNQXAC9IVRw is "Me at the zoo", the first YouTube video (19 seconds long)
    res = await YouTubeIntelligence.process_youtube_url("https://www.youtube.com/watch?v=jNQXAC9IVRw")
    assert res.get("success") is True
    assert res.get("video_id") == "jNQXAC9IVRw"
    assert "Me at the zoo" in res.get("title", "")
    assert len(res.get("transcript_segments", [])) > 0
    assert "elephants" in res.get("transcript_text", "").lower()
