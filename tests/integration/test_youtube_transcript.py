from pathlib import Path

import pytest

from app.youtube.youtube_transcript import fetch_youtube_transcript


@pytest.mark.integration
def test_youtube_video_transcript():
    """Test fetching transcript from a YouTube video."""
    output_dir = "output/test_youtube"

    # Test with a known short video: "Me at the zoo"
    video_url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"

    result = fetch_youtube_transcript(video_url, output_dir=output_dir)

    # Assertions
    assert result is not None, "Result should not be None"
    assert result.success, (
        f"Fetch should succeed. Error: {getattr(result, 'error', 'Unknown')}"
    )
    assert result.video_title, "Video title should be present"
    assert result.video_url == video_url, "URL should match input"

    # Verify output file was created
    if hasattr(result, "output_file") and result.output_file:
        output_path = Path(result.output_file)
        assert output_path.exists(), f"Output file should exist at {result.output_file}"


@pytest.mark.integration
def test_youtube_channel_latest_video():
    """Test fetching latest video from a YouTube channel."""
    output_dir = "output/test_youtube"

    # Test with a channel URL (using Google DeepMind as example)
    channel_url = "https://www.youtube.com/@GoogleDeepMind"

    result = fetch_youtube_transcript(channel_url, output_dir=output_dir)

    # Assertions
    assert result is not None, "Result should not be None"
    assert result.success, (
        f"Fetch should succeed. Error: {getattr(result, 'error', 'Unknown')}"
    )
    assert result.video_title, "Latest video title should be present"
    assert result.video_url, "Video URL should be present"

    # Verify output file was created
    if hasattr(result, "output_file") and result.output_file:
        output_path = Path(result.output_file)
        assert output_path.exists(), f"Output file should exist at {result.output_file}"
