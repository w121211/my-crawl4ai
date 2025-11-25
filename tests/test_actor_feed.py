import json

from bluesky.actor_feed_batch import _store_feed_response


class FakeResponse:
    def __init__(self, feed, cursor):
        self.feed = feed
        self.cursor = cursor

    def model_dump(self):
        return {
            "feed": self.feed,
            "cursor": self.cursor,
            "extra": "value",
        }


def test_store_feed_response_writes_expected_files(tmp_path):
    actor = "alice test"
    response = FakeResponse(feed=[{"uri": "1"}, {"uri": "2"}], cursor="next-cursor")

    output_path = _store_feed_response(
        actor,
        response,
        limit=2,
        feed_filter="posts",
        cursor="cursor-in",
        output_dir=str(tmp_path),
    )

    assert output_path.exists()
    assert output_path.parent.name == "alice_test"

    feed_file = output_path / "feed.json"
    metadata_file = output_path / "metadata.json"

    assert feed_file.exists()
    assert metadata_file.exists()

    saved_feed = json.loads(feed_file.read_text(encoding="utf-8"))
    assert saved_feed == response.model_dump()

    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    assert metadata["actor"] == actor
    assert metadata["actor_folder"] == "alice_test"
    assert metadata["limit"] == 2
    assert metadata["filter"] == "posts"
    assert metadata["request_cursor"] == "cursor-in"
    assert metadata["response_cursor"] == "next-cursor"
    assert metadata["post_count"] == 2
    assert metadata["output_path"] == str(output_path)
