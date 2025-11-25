import os
import re
import json
import logging
from typing import Optional
from datetime import datetime
import yt_dlp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class YouTubeBatchTranscriptCrawler:
    def __init__(self, output_dir: str = "output/youtube"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def crawl(self, channel_url: str, lang: Optional[str] = None, max_videos: int = 1):
        """
        Crawl transcripts for videos from a YouTube channel.

        Args:
            channel_url: YouTube channel URL.
            lang: Optional language code (e.g., 'en', 'es'). If None, defaults to 'en'. Falls back to any available language if preferred not found.
            max_videos: Maximum number of videos to process. Defaults to 1.
        """
        try:
            self._process_channel(channel_url, lang, max_videos)
        except Exception as e:
            logger.error(f"Failed to process channel {channel_url}: {e}")

    def _process_channel(self, channel_url: str, lang: Optional[str], max_videos: int):
        logger.info(f"Processing channel: {channel_url} (max {max_videos} videos)")

        # Ensure we're targeting the videos tab
        if '/videos' not in channel_url:
            if channel_url.endswith('/'):
                channel_url = channel_url + 'videos'
            else:
                channel_url = channel_url + '/videos'

        # 1. Get video metadata
        ydl_opts_meta = {
            'extract_flat': 'in_playlist',
            'playlist_items': f'1:{max_videos}',
            'quiet': True,
            'ignoreerrors': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts_meta) as ydl:
            info = ydl.extract_info(channel_url, download=False)

            if not info:
                logger.warning(f"No info found for {channel_url}")
                return

            if 'entries' not in info or not info['entries']:
                logger.warning(f"No videos found for {channel_url}")
                return

            channel_id = info.get('channel_id') or info.get('uploader_id')
            videos = list(info['entries'])
            logger.info(f"Found {len(videos)} video(s) to process")

            for video in videos:
                if not video:
                    continue

                video_id = video.get('id')
                video_title = video.get('title')

                # Fallback for channel_id if not in top level info
                if not channel_id:
                    channel_id = video.get('channel_id')

                if not video_id:
                    logger.warning("Could not determine video ID, skipping")
                    continue

                logger.info(f"Processing video: {video_title} ({video_id})")

                # 2. Check cache / Prepare output path
                # Structure: output/youtube/<channel>/<date>_<video_id>/
                channel_name = channel_id if channel_id else "unknown_channel"
                channel_path = os.path.join(self.output_dir, channel_name)

                # Create folder name with date_videoid
                date_str = datetime.now().strftime("%Y%m%d")
                folder_name = f"{date_str}_{video_id}"
                video_path = os.path.join(channel_path, folder_name)

                # Check if transcript already exists for this video_id
                if os.path.exists(channel_path):
                    existing_folders = [d for d in os.listdir(channel_path) if d.endswith(f"_{video_id}")]
                    if existing_folders:
                        logger.info(f"Transcript already exists for {video_id} in {existing_folders[0]}. Skipping.")
                        continue

                if not os.path.exists(video_path):
                    os.makedirs(video_path)

                # 3. Download transcript and save metadata
                # Always construct URL from video_id since extract_flat returns playlist URLs
                v_url = f"https://www.youtube.com/watch?v={video_id}"

                # Get full video info for metadata
                full_video_info = self._get_full_video_info(v_url)

                # Download transcript
                transcript_result = self._download_transcript(v_url, video_path, lang)

                # Save metadata
                self._save_metadata(
                    video_path=video_path,
                    video_info=full_video_info,
                    transcript_result=transcript_result,
                    channel_url=channel_url
                )

    def _get_full_video_info(self, video_url: str):
        """Get full video information including metadata."""
        ydl_opts = {
            'skip_download': True,
            'quiet': True,
            'ignoreerrors': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(video_url, download=False)
                return info
        except Exception as e:
            logger.error(f"Error getting video info for {video_url}: {e}")
            return {}

    def _download_transcript(self, video_url: str, output_path: str, lang: Optional[str]):
        """
        Download transcript for a video.

        Returns:
            dict: Result containing status, transcript_type, language, and error_message
        """
        logger.info(f"Downloading transcript for {video_url}")

        result = {
            'status': 'not_available',
            'transcript_type': None,
            'language': None,
            'error_message': None
        }

        # Priority: user lang > any manual sub > auto-sub (en, zh)

        # Try manual subs first
        ydl_opts = {
            'skip_download': True,
            'writesubtitles': True,
            'writeautomaticsub': False,
            'subtitleslangs': [lang] if lang else ['all'],  # 'all' gets any available manual sub
            'subtitlesformat': 'vtt',
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'quiet': False,
            'ignoreerrors': True,
        }

        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            # Check if any subtitle was downloaded
            vtt_files = [f for f in os.listdir(output_path) if f.endswith('.vtt')]
            if vtt_files:
                logger.info(f"Successfully downloaded manual subtitle for {video_url}")
                detected_lang = self._detect_language_from_filename(vtt_files[0])
                self._convert_vtt_to_script(output_path)
                result['status'] = 'success'
                result['transcript_type'] = 'manual'
                result['language'] = detected_lang or lang
                return result

            # Fallback: try auto-generated subs (en first, then zh)
            logger.info(f"No manual subs found, trying auto-generated for {video_url}")
            ydl_opts['writesubtitles'] = False
            ydl_opts['writeautomaticsub'] = True
            ydl_opts['subtitleslangs'] = [lang] if lang else ['en', 'zh']

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([video_url])

            vtt_files = [f for f in os.listdir(output_path) if f.endswith('.vtt')]
            if vtt_files:
                logger.info(f"Successfully downloaded auto-generated subtitle for {video_url}")
                detected_lang = self._detect_language_from_filename(vtt_files[0])
                self._convert_vtt_to_script(output_path)
                result['status'] = 'success'
                result['transcript_type'] = 'auto-generated'
                result['language'] = detected_lang or lang
                return result
            else:
                logger.warning(f"No subtitles found for {video_url}")
                result['error_message'] = "No subtitles found for requested languages"
                return result

        except Exception as e:
            logger.error(f"Error downloading transcript for {video_url}: {e}")
            result['status'] = 'failed'
            result['error_message'] = str(e)
            return result

    def _detect_language_from_filename(self, filename: str) -> Optional[str]:
        """Extract language code from VTT filename (e.g., 'video.en.vtt' -> 'en')."""
        match = re.search(r'\.([a-z]{2})(?:-[A-Z]{2})?\.vtt$', filename)
        if match:
            return match.group(1)
        return None

    def _save_metadata(self, video_path: str, video_info: dict, transcript_result: dict, channel_url: str):
        """Save metadata.json file in the video folder."""
        metadata = {
            'video_id': video_info.get('id'),
            'video_title': video_info.get('title'),
            'channel_id': video_info.get('channel_id'),
            'channel_name': video_info.get('channel') or video_info.get('uploader'),
            'channel_url': channel_url,
            'video_url': video_info.get('webpage_url'),
            'crawl_date': datetime.now().isoformat(),
            'transcript_status': transcript_result['status'],
            'transcript_type': transcript_result['transcript_type'],
            'transcript_language': transcript_result['language'],
            'error_message': transcript_result.get('error_message'),
            'duration': video_info.get('duration'),
            'upload_date': video_info.get('upload_date'),
            'view_count': video_info.get('view_count'),
            'description': video_info.get('description', '')[:500] if video_info.get('description') else None
        }

        metadata_path = os.path.join(video_path, 'metadata.json')
        try:
            with open(metadata_path, 'w', encoding='utf-8') as f:
                json.dump(metadata, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved metadata to {metadata_path}")
        except Exception as e:
            logger.error(f"Error saving metadata to {metadata_path}: {e}")

    def _convert_vtt_to_script(self, output_path: str):
        """Convert VTT subtitle files to plain text scripts."""
        for filename in os.listdir(output_path):
            if filename.endswith('.vtt'):
                vtt_path = os.path.join(output_path, filename)
                script_path = os.path.join(output_path, filename.replace('.vtt', '.txt'))

                try:
                    with open(vtt_path, 'r', encoding='utf-8') as f:
                        content = f.read()

                    # Remove VTT header
                    content = re.sub(r'^WEBVTT\n.*?\n\n', '', content, flags=re.DOTALL)

                    # Remove timestamps (e.g., 00:00:01.000 --> 00:00:04.000)
                    content = re.sub(r'\d{2}:\d{2}:\d{2}\.\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}\.\d{3}.*?\n', '', content)

                    # Remove cue identifiers (numeric or other)
                    content = re.sub(r'^\d+\n', '', content, flags=re.MULTILINE)

                    # Remove VTT tags like <c>, </c>, <00:00:01.000>
                    content = re.sub(r'<[^>]+>', '', content)

                    # Remove duplicate lines (common in auto-generated subs)
                    lines = content.split('\n')
                    unique_lines = []
                    prev_line = ''
                    for line in lines:
                        line = line.strip()
                        if line and line != prev_line:
                            unique_lines.append(line)
                            prev_line = line

                    # Join into paragraphs
                    script = ' '.join(unique_lines)

                    # Clean up extra whitespace
                    script = re.sub(r'\s+', ' ', script).strip()

                    with open(script_path, 'w', encoding='utf-8') as f:
                        f.write(script)

                    logger.info(f"Created script: {script_path}")

                except Exception as e:
                    logger.error(f"Error converting {vtt_path} to script: {e}")

if __name__ == "__main__":
    # Example usage
    crawler = YouTubeBatchTranscriptCrawler()

    # Simple CLI interface if run directly
    import sys
    if len(sys.argv) > 1:
        # Parse arguments: channel_url and optional --max-videos N
        channel_url = None
        max_videos = 1
        i = 1
        while i < len(sys.argv):
            if sys.argv[i] == '--max-videos' and i + 1 < len(sys.argv):
                max_videos = int(sys.argv[i + 1])
                i += 2
            else:
                channel_url = sys.argv[i]
                i += 1

        if channel_url:
            crawler.crawl(channel_url, max_videos=max_videos)
        else:
            print("Error: No channel URL provided")
    else:
        print("Usage: python youtube_batch_crawler.py <channel_url> [--max-videos N]")
