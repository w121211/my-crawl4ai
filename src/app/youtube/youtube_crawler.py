import os
import logging
from typing import List, Optional
import yt_dlp

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class YouTubeTranscriptCrawler:
    def __init__(self, output_dir: str = "output"):
        self.output_dir = output_dir
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)

    def crawl(self, channel_urls: List[str], lang: Optional[str] = None):
        """
        Crawl transcripts for the latest video from a list of YouTube channels.

        Args:
            channel_urls: List of YouTube channel URLs.
            lang: Optional language code (e.g., 'en', 'es'). If None, defaults to 'en'.
        """
        for url in channel_urls:
            try:
                self._process_channel(url, lang)
            except Exception as e:
                logger.error(f"Failed to process channel {url}: {e}")

    def _process_channel(self, channel_url: str, lang: Optional[str]):
        logger.info(f"Processing channel: {channel_url}")

        # 1. Get latest video metadata
        ydl_opts_meta = {
            'extract_flat': True,
            'playlistend': 1,
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
                
            latest_video = info['entries'][0]
            video_id = latest_video.get('id')
            video_title = latest_video.get('title')
            channel_id = info.get('id') # Channel ID might be top level or in entry
            # Fallback for channel_id if not in top level info (sometimes it is, sometimes not for channels)
            if not channel_id:
                channel_id = latest_video.get('channel_id')
            
            if not video_id:
                logger.warning("Could not determine video ID")
                return

            logger.info(f"Found latest video: {video_title} ({video_id})")
            
            # 2. Check cache / Prepare output path
            # Structure: output/<channel_id>/<video_id>/
            # We use channel_id to avoid name collisions and filesystem issues with names
            channel_path = os.path.join(self.output_dir, channel_id if channel_id else "unknown_channel")
            video_path = os.path.join(channel_path, video_id)
            
            if not os.path.exists(video_path):
                os.makedirs(video_path)
            
            # Check if transcript already exists (simple check for any vtt/srt file)
            # yt-dlp naming: title.lang.vtt
            # We will force a specific filename to make checking easier or just let yt-dlp handle it and we check if dir is empty?
            # Better: check if we already ran for this video_id.
            # But user asked to "enable cache". 
            # If we see files in the folder, we might skip.
            existing_files = os.listdir(video_path)
            if any(f.endswith(('.vtt', '.srt', '.ttml')) for f in existing_files):
                logger.info(f"Transcript already exists for {video_id}. Skipping.")
                return

            # 3. Download transcript
            # Construct URL if 'url' is missing
            v_url = latest_video.get('url')
            if not v_url:
                v_url = latest_video.get('webpage_url')
            if not v_url and video_id:
                v_url = f"https://www.youtube.com/watch?v={video_id}"
            
            if not v_url:
                logger.error(f"Could not determine video URL for {video_id}")
                return

            self._download_transcript(v_url, video_path, lang)

    def _download_transcript(self, video_url: str, output_path: str, lang: Optional[str]):
        logger.info(f"Downloading transcript for {video_url}")
        
        # Language selection: 
        # If lang provided: try that.
        # If not: 'en'
        # Also enable auto-generated subs as fallback.
        
        langs = [lang] if lang else ['en']
        
        ydl_opts_down = {
            'skip_download': True, # Only metadata and subs
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': langs,
            'outtmpl': os.path.join(output_path, '%(title)s.%(ext)s'),
            'quiet': False,
            'ignoreerrors': True,
        }
        
        try:
            with yt_dlp.YoutubeDL(ydl_opts_down) as ydl:
                error_code = ydl.download([video_url])
                if error_code:
                     logger.error(f"yt-dlp reported error code {error_code} for {video_url}")
                else:
                     logger.info(f"Successfully processed {video_url}")
        except Exception as e:
            logger.error(f"Error downloading transcript for {video_url}: {e}")

if __name__ == "__main__":
    # Example usage
    crawler = YouTubeTranscriptCrawler()
    
    # Example channels (replace with actual inputs or arg parsing)
    # For testing, we can use a known channel or ask user for input.
    # I will put a placeholder list here.
    channels = [
        # "https://www.youtube.com/@GoogleDeepMind", # Example
    ]
    
    # Simple CLI interface if run directly
    import sys
    if len(sys.argv) > 1:
        channels = sys.argv[1:]
        crawler.crawl(channels)
    else:
        print("Usage: python youtube_crawler.py <channel_url1> <channel_url2> ...")
