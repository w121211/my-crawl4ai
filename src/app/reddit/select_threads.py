import os
import json
import argparse
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

def get_openai_client():
    """Initialize OpenAI client for OpenRouter."""
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY must be set in .env")
        return None
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key
    )

def load_feed(file_path):
    """Load feed data from JSON file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading feed file: {e}")
        return None

def select_threads(client, posts, criteria, limit=5):
    """Use LLM to select threads based on criteria."""
    
    # Prepare simplified post list for LLM to save tokens
    simplified_posts = []
    for post in posts:
        simplified_posts.append({
            "id": post.get("id"),
            "title": post.get("title"),
            "selftext": post.get("selftext", ""),
            "score": post.get("score"),
            "num_comments": post.get("num_comments")
        })
        
    prompt = f"""
    You are a Reddit analyst. Select the top {limit} threads from the list below that best match the following criteria:
    
    CRITERIA: "{criteria}"
    
    Return a valid JSON object with a "selected_threads" key containing a list of objects.
    Each object must have:
    - "id": The thread ID
    - "reason": A brief explanation of why it was selected
    
    POSTS:
    {json.dumps(simplified_posts, indent=2)}
    """
    
    try:
        response = client.chat.completions.create(
            model="google/gemini-flash-1.5",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that outputs JSON."},
                {"role": "user", "content": prompt}
            ],
            response_format={"type": "json_object"}
        )
        
        content = response.choices[0].message.content
        return json.loads(content)
    except Exception as e:
        print(f"Error calling OpenAI: {e}")
        return None

def save_selection(selection, feed_path, criteria):
    """Save selected threads to a JSON file."""
    # Determine output path based on feed path
    feed_dir = os.path.dirname(feed_path)
    feed_name = os.path.basename(feed_path)
    
    # Try to extract timestamp from feed name (e.g., 20241120_120000_feed.json)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if "_" in feed_name:
        parts = feed_name.split("_")
        if len(parts) >= 2 and parts[0].isdigit():
             # Keep original timestamp if possible, or just append new one
             pass

    output_filename = f"{timestamp}_selected.json"
    output_path = os.path.join(feed_dir, output_filename)
    
    # Add metadata
    output_data = {
        "criteria": criteria,
        "source_feed": feed_path,
        "selection_date": datetime.now().isoformat(),
        "selection": selection.get("selected_threads", [])
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
        
    print(f"Saved selection to {output_path}")
    return output_path

def main():
    parser = argparse.ArgumentParser(description="Select Reddit threads using LLM.")
    parser.add_argument("feed_file", help="Path to the feed JSON file")
    parser.add_argument("--criteria", required=True, help="Selection criteria (e.g., 'market analysis', 'funny memes')")
    parser.add_argument("--limit", type=int, default=5, help="Number of threads to select")
    
    args = parser.parse_args()
    
    client = get_openai_client()
    if not client:
        return
        
    posts = load_feed(args.feed_file)
    if not posts:
        return
        
    print(f"Analyzing {len(posts)} posts with criteria: '{args.criteria}'...")
    selection = select_threads(client, posts, args.criteria, args.limit)
    
    if selection:
        save_selection(selection, args.feed_file, args.criteria)
    else:
        print("Failed to select threads.")

if __name__ == "__main__":
    main()
