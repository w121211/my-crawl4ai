import logging
import os
import tempfile
from typing import Optional

import yt_dlp
from pydantic import BaseModel

from .vtt_converter import vtt_to_text

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class VideoInfo(BaseModel):
    id: str
    title: str
    channel_id: Optional[str] = None


class FetchYoutubeResult(BaseModel):
    success: bool
    error: Optional[str] = None
    video_id: Optional[str] = None
    video_title: Optional[str] = None
    channel_id: Optional[str] = None
    transcript_path: Optional[str] = None
    transcript_text: Optional[str] = None
    video_url: Optional[str] = None


def fetch_youtube_transcript(
    url: str, lang: Optional[str] = None, output_dir: Optional[str] = None
) -> FetchYoutubeResult:
    """
    Crawl a YouTube URL (Channel or Video).

    Args:
        url: YouTube video or channel URL
        lang: Optional language code for transcripts (default: "en")
        output_dir: Optional directory to save transcript files. If None, uses temp directory.

    Returns:
        FetchYoutubeResult with success status and data.
    """
    # Use temp directory if output_dir not specified
    use_temp = output_dir is None
    if use_temp:
        output_dir = tempfile.mkdtemp(prefix="youtube_crawl_")

    # Ensure output directory exists
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        # 1. Identify if it's a channel or video and get the target video ID
        video_info = get_target_video_info(url)
        if not video_info:
            return FetchYoutubeResult(success=False, error="Could not extract video info")

        video_id = video_info.id
        video_title = video_info.title
        channel_id = video_info.channel_id or "unknown_channel"

        logger.info(f"Targeting video: {video_title} ({video_id})")

        # 2. Prepare output path
        # output/youtube_worker/<channel_id>/<video_id>/
        channel_path = os.path.join(output_dir, channel_id)
        video_path = os.path.join(channel_path, video_id)

        if not os.path.exists(video_path):
            os.makedirs(video_path)

        # 3. Download transcript
        # Construct video URL
        video_url = f"https://www.youtube.com/watch?v={video_id}"

        transcript_file = download_transcript(video_url, video_path, lang)

        if transcript_file:
            # Read the transcript content
            try:
                with open(transcript_file, "r", encoding="utf-8") as f:
                    vtt_content = f.read()

                # Convert VTT to clean text
                content = vtt_to_text(vtt_content)

                return FetchYoutubeResult(
                    success=True,
                    video_id=video_id,
                    video_title=video_title,
                    channel_id=channel_id,
                    transcript_path=transcript_file if not use_temp else None,
                    transcript_text=content,
                    video_url=video_url,
                )
            except Exception as e:
                return FetchYoutubeResult(
                    success=False, error=f"Failed to read transcript file: {e}"
                )
        else:
            return FetchYoutubeResult(success=False, error="No transcript available")

    except Exception as e:
        logger.error(f"Crawl failed for {url}: {e}")
        return FetchYoutubeResult(success=False, error=str(e))


def get_target_video_info(url: str) -> Optional[VideoInfo]:
    """
    Extracts video info. If URL is a channel, gets the latest video.
    """
    # Simple heuristic to append /videos if it looks like a channel root
    # This helps yt-dlp focus on the uploaded videos tab
    if "/@" in url and "/videos" not in url and "/watch" not in url:
        url = url.rstrip("/") + "/videos"

    ydl_opts = {
        "extract_flat": True,  # Fast extraction
        "quiet": True,
        "ignoreerrors": True,
        "playlistend": 1,  # Only need the first one if it's a list
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

        if not info:
            return None

        # Check if it's a video or a playlist/channel
        if "entries" in info:
            # It's a playlist or channel
            entries = list(info["entries"])
            if not entries:
                return None
            # Return the first entry (latest video)
            raw_info = entries[0]
        else:
            # It's a single video
            raw_info = info

        return VideoInfo(
            id=raw_info["id"],
            title=raw_info["title"],
            channel_id=raw_info.get("channel_id"),
        )


def download_transcript(
    video_url: str, output_path: str, lang: Optional[str]
) -> Optional[str]:
    """
    Downloads transcript and returns the path to the file.
    """
    langs = [lang] if lang else ["en"]

    # We prefer vtt
    ydl_opts = {
        "skip_download": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": langs,
        "outtmpl": os.path.join(output_path, "%(title)s.%(ext)s"),
        "quiet": True,
        "ignoreerrors": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([video_url])

    # Find the downloaded file
    # yt-dlp might name it "Title.en.vtt" or "Title.vtt"
    files = os.listdir(output_path)
    vtt_files = [f for f in files if f.endswith(".vtt")]

    if not vtt_files:
        return None

    # Return the first one found
    return os.path.join(output_path, vtt_files[0])


if __name__ == "__main__":
    # Test
    # Test with a channel
    # print(fetch_youtube_transcript("https://www.youtube.com/@GoogleDeepMind"))
    # Test with a video
    # print(fetch_youtube_transcript("https://www.youtube.com/watch?v=ad79nYk2keg"))
    pass
