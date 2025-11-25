"""
Reddit Crawler

Usage:
    python crawl_reddit.py feed r/python --limit 25 --sort hot
    python crawl_reddit.py thread https://reddit.com/r/python/comments/abc123/example
"""

import praw
import os
import json
import argparse
from dotenv import load_dotenv
from urllib.parse import urlparse
from datetime import datetime

# Load environment variables
load_dotenv()

def get_reddit_instance():
    """Initialize and return a PRAW Reddit instance."""
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "python:crawl_reddit:v1.0 (by /u/unknown)")
    
    if not client_id or not client_secret:
        print("Error: REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set in .env")
        return None

    return praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent
    )

def parse_subreddit_from_url(url):
    """Extract subreddit name from a URL."""
    # Handle full URL or just subreddit name
    if "reddit.com/r/" in url:
        path = urlparse(url).path
        parts = path.strip("/").split("/")
        if "r" in parts:
            idx = parts.index("r")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    elif not url.startswith("http"):
        return url # Assume it's just the subreddit name
    return None

def save_data(data, output_path):
    """Save data to a JSON file."""
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"Saved data to {output_path}")

def get_subreddit_feed(reddit, subreddit_url, limit=10, sort_by="hot"):
    """Fetch the latest feed from a subreddit."""
    subreddit_name = parse_subreddit_from_url(subreddit_url)
    if not subreddit_name:
        print(f"Error: Could not parse subreddit from {subreddit_url}")
        return

    print(f"Fetching {sort_by} feed for r/{subreddit_name} (limit={limit})...")
    subreddit = reddit.subreddit(subreddit_name)
    
    posts = []
    try:
        # Get the generator method based on sort_by string
        if not hasattr(subreddit, sort_by):
             print(f"Error: Invalid sort method '{sort_by}'")
             return
             
        post_generator = getattr(subreddit, sort_by)(limit=limit)
        
        for submission in post_generator:
            posts.append({
                "id": submission.id,
                "title": submission.title,
                "url": submission.url,
                "permalink": submission.permalink,
                "selftext": submission.selftext,
                "author": str(submission.author),
                "created_utc": submission.created_utc,
                "score": submission.score,
                "num_comments": submission.num_comments,
                "upvote_ratio": submission.upvote_ratio
            })
    except Exception as e:
        print(f"Error fetching feed: {e}")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    # Metadata
    metadata = {
        "subreddit": subreddit_name,
        "url": subreddit_url,
        "crawl_date": datetime.now().isoformat(),
        "limit": limit,
        "sort_by": sort_by,
        "count": len(posts)
    }
    
    # File paths
    base_path = f"output/reddit/{subreddit_name}/{timestamp}_feed"
    data_file = f"{base_path}.json"
    metadata_file = f"{base_path}_metadata.json"
    
    save_data(posts, data_file)
    save_data(metadata, metadata_file)

def process_comment(comment):
    """Recursively process a comment and its replies."""
    comment_data = {
        "id": comment.id,
        "author": str(comment.author),
        "body": comment.body,
        "created_utc": comment.created_utc,
        "score": comment.score,
        "permalink": comment.permalink,
        "replies": []
    }
    
    for reply in comment.replies:
        comment_data["replies"].append(process_comment(reply))
        
    return comment_data

def get_thread(reddit, thread_url, limit=None):
    """Fetch a thread and its comments."""
    print(f"Fetching thread {thread_url}...")
    try:
        submission = reddit.submission(url=thread_url)
        
        print("Expanding comments...")
        submission.comments.replace_more(limit=limit)
        
        thread_data = {
            "id": submission.id,
            "title": submission.title,
            "url": submission.url,
            "permalink": submission.permalink,
            "selftext": submission.selftext,
            "author": str(submission.author),
            "created_utc": submission.created_utc,
            "score": submission.score,
            "num_comments": submission.num_comments,
            "subreddit": str(submission.subreddit),
            "comments": []
        }
        
        for top_level_comment in submission.comments:
            thread_data["comments"].append(process_comment(top_level_comment))
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        subreddit_name = str(submission.subreddit)
        
        # Metadata
        metadata = {
            "thread_id": submission.id,
            "thread_title": submission.title,
            "thread_url": thread_url,
            "subreddit": subreddit_name,
            "crawl_date": datetime.now().isoformat(),
            "limit": limit,
            "comment_count": submission.num_comments
        }
        
        # File paths
        base_path = f"output/reddit/{subreddit_name}/{timestamp}_thread_{submission.id}"
        data_file = f"{base_path}.json"
        metadata_file = f"{base_path}_metadata.json"
        
        save_data(thread_data, data_file)
        save_data(metadata, metadata_file)
        
    except Exception as e:
        print(f"Error fetching thread: {e}")

def main():
    parser = argparse.ArgumentParser(description="Crawl Reddit data.")
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")

    # Feed command
    feed_parser = subparsers.add_parser("feed", help="Get latest feed from a subreddit")
    feed_parser.add_argument("url", help="Subreddit URL or name")
    feed_parser.add_argument("--limit", type=int, default=10, help="Number of posts to fetch")
    feed_parser.add_argument("--sort", choices=["hot", "new", "top", "rising"], default="hot", help="Sort order (default: hot)")

    # Thread command
    thread_parser = subparsers.add_parser("thread", help="Get a thread and its replies")
    thread_parser.add_argument("url", help="Thread URL")
    thread_parser.add_argument("--limit", type=int, default=None, help="Limit for expanding comments (0=none, None=all)")

    args = parser.parse_args()
    
    reddit = get_reddit_instance()
    if not reddit:
        return

    if args.command == "feed":
        get_subreddit_feed(reddit, args.url, args.limit, args.sort)
    elif args.command == "thread":
        get_thread(reddit, args.url, args.limit)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
