import argparse
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional, Sequence

from atproto import Client
from dotenv import load_dotenv

"""
Fetch Bluesky feeds for a list of actors and store results under output/bluesky/<actor>/<timestamp>.

Example usages:
    # Credentials from environment variables (or a .env file)
    BLUESKY_IDENTIFIER=handle.bsky.social BLUESKY_PASSWORD=app-password \\
        uv run python -m src.bluesky.actor_feed_batch benzinga.bsky.social yahoofinance.com --limit 50

    # With .env configuration already in place
    python -m src.bluesky.actor_feed_batch did:plc:abc123
"""

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class BlueskyFeedBatchFetcher:
    def __init__(self, identifier: str, password: str, output_dir: str = "output/bluesky") -> None:
        self.client = Client()
        self.client.login(identifier, password)

        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def fetch_actor_feeds(
        self,
        actors: Sequence[str],
        *,
        limit: int = 25,
        feed_filter: str = "posts_and_author_threads",
        cursor: Optional[str] = None,
    ) -> None:
        for actor in actors:
            actor = actor.strip()
            if not actor:
                continue

            try:
                response = self.client.get_author_feed(actor=actor, limit=limit, filter=feed_filter, cursor=cursor)
            except Exception as exc:  # pylint: disable=broad-except
                logger.error("Failed to fetch feed for %s: %s", actor, exc)
                continue

            output_path = self._prepare_output_path(actor)
            serialized_feed = self._serialize_response(response)

            feed_file = output_path / "feed.json"
            metadata_file = output_path / "metadata.json"

            with feed_file.open("w", encoding="utf-8") as fp:
                json.dump(serialized_feed, fp, ensure_ascii=False, indent=2)

            metadata = {
                "actor": actor,
                "actor_folder": output_path.parent.name,
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "limit": limit,
                "filter": feed_filter,
                "request_cursor": cursor,
                "response_cursor": response.cursor,
                "post_count": len(response.feed),
                "output_path": str(output_path),
            }

            with metadata_file.open("w", encoding="utf-8") as fp:
                json.dump(metadata, fp, ensure_ascii=False, indent=2)

            logger.info("Stored feed for %s at %s", actor, output_path)

    def _prepare_output_path(self, actor: str) -> Path:
        safe_actor = self._sanitize_actor(actor)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        actor_dir = self.output_dir / safe_actor
        actor_dir.mkdir(parents=True, exist_ok=True)
        output_path = actor_dir / timestamp
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path

    @staticmethod
    def _sanitize_actor(actor: str) -> str:
        return re.sub(r"[^A-Za-z0-9._-]+", "_", actor)

    @staticmethod
    def _serialize_response(response: object):
        if hasattr(response, "model_dump"):
            return response.model_dump()
        if hasattr(response, "dict"):
            return response.dict()
        if hasattr(response, "json"):
            return json.loads(response.json())
        raise TypeError("Response object is not serializable")


def parse_args(argv: Optional[Iterable[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch Bluesky feeds for multiple actors.")
    parser.add_argument(
        "actors",
        nargs="+",
        help="List of actor handles or DIDs to fetch feeds for.",
    )
    parser.add_argument("--limit", type=int, default=25, help="Number of feed items to request per actor.")
    parser.add_argument(
        "--filter",
        default="posts_and_author_threads",
        help="Feed filter to use (see https://docs.bsky.app/docs/tutorials/viewing-feeds).",
    )
    parser.add_argument("--cursor", default=None, help="Cursor for pagination, if you want to continue from a previous run.")
    return parser.parse_args(argv)


def main(argv: Optional[Iterable[str]] = None) -> None:
    args = parse_args(argv)
    load_dotenv()
    identifier = os.getenv("BLUESKY_IDENTIFIER")
    password = os.getenv("BLUESKY_PASSWORD")

    if not identifier or not password:
        raise RuntimeError(
            "Missing Bluesky credentials. Set BLUESKY_IDENTIFIER and BLUESKY_PASSWORD environment variables."
        )

    fetcher = BlueskyFeedBatchFetcher(identifier, password)
    fetcher.fetch_actor_feeds(args.actors, limit=args.limit, feed_filter=args.filter, cursor=args.cursor)


if __name__ == "__main__":
    main()
