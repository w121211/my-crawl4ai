import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from atproto import Client
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


def fetch_actor_feed(
    actor: str,
    *,
    limit: int = 25,
    feed_filter: str = "posts_and_author_threads",
    cursor: Optional[str] = None,
    output_dir: str = "output/bluesky",
    client: Optional[Client] = None,
    identifier: Optional[str] = None,
    password: Optional[str] = None,
) -> Path:
    """Fetch a single actor feed and persist it to disk."""

    normalized_actor = actor.strip()
    if not normalized_actor:
        raise ValueError("Actor handle or DID must be provided")

    active_client = client or _create_client(identifier, password)

    response = active_client.get_author_feed(
        actor=normalized_actor,
        limit=limit,
        filter=feed_filter,
        cursor=cursor,
    )

    output_path = _store_feed_response(
        normalized_actor,
        response,
        limit=limit,
        feed_filter=feed_filter,
        cursor=cursor,
        output_dir=output_dir,
    )

    logger.info("Stored feed for %s at %s", normalized_actor, output_path)
    return output_path


def _create_client(identifier: Optional[str], password: Optional[str]) -> Client:
    identifier = identifier or os.getenv("BLUESKY_IDENTIFIER")
    password = password or os.getenv("BLUESKY_PASSWORD")

    if not identifier or not password:
        raise RuntimeError(
            "Missing Bluesky credentials. Provide identifier/password or set environment variables."
        )

    client = Client()
    client.login(identifier, password)
    return client


def _store_feed_response(
    actor: str,
    response: object,
    *,
    limit: int,
    feed_filter: str,
    cursor: Optional[str],
    output_dir: str,
) -> Path:
    output_path = _prepare_output_path(actor, output_dir)
    serialized_feed = _serialize_response(response)

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
        "response_cursor": getattr(response, "cursor", None),
        "post_count": len(getattr(response, "feed", [])),
        "output_path": str(output_path),
    }

    with metadata_file.open("w", encoding="utf-8") as fp:
        json.dump(metadata, fp, ensure_ascii=False, indent=2)

    return output_path


def _prepare_output_path(actor: str, output_dir: str) -> Path:
    safe_actor = _sanitize_actor(actor)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    actor_dir = Path(output_dir) / safe_actor
    actor_dir.mkdir(parents=True, exist_ok=True)
    output_path = actor_dir / timestamp
    output_path.mkdir(parents=True, exist_ok=True)
    return output_path


def _sanitize_actor(actor: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", actor)


def _serialize_response(response: object):
    if hasattr(response, "model_dump"):
        return response.model_dump()
    if hasattr(response, "dict"):
        return response.dict()
    if hasattr(response, "json"):
        return json.loads(response.json())
    raise TypeError("Response object is not serializable")
