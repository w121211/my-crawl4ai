import os

import pytest

from bluesky.actor_feed_batch import fetch_actor_feed


@pytest.mark.skipif(
    not (os.getenv("BLUESKY_IDENTIFIER") and os.getenv("BLUESKY_PASSWORD")),
    reason="Missing BLUESKY_IDENTIFIER or BLUESKY_PASSWORD env vars",
)
def test_fetch_actor_feed_real_api(tmp_path):
    """
    Integration test that hits the real Bluesky API.
    Requires BLUESKY_IDENTIFIER and BLUESKY_PASSWORD to be set.
    """
    # Use a known public actor, e.g., 'bsky.app' or the user's own handle if available.
    # 'bsky.app' is the official Bluesky account.
    actor = "bsky.app"

    output_path = fetch_actor_feed(actor=actor, limit=5, output_dir=str(tmp_path))

    assert output_path.exists()
    assert (output_path / "feed.json").exists()
    assert (output_path / "metadata.json").exists()

    # Verify content is not empty
    feed_content = (output_path / "feed.json").read_text()
    assert len(feed_content) > 0
