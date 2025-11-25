import asyncio
import os
import json
import hashlib
import argparse
from urllib.parse import urlparse
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from playwright.async_api import async_playwright

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

def get_url_hash(url):
    """Generate a short hash for the URL to use in filenames."""
    return hashlib.md5(url.encode()).hexdigest()[:8]

def get_domain(url):
    """Extract domain from URL."""
    return urlparse(url).netloc

async def save_crawl_data(url, content, error, output_base_dir):
    """Saves crawled data to the specified directory."""
    domain = get_domain(url)
    url_hash = get_url_hash(url)
    date_str = datetime.now().strftime("%Y%m%d")
    
    # Structure: output_base_dir/<domain>/<date>_<hash>/
    # This groups by domain, then by specific crawl instance
    save_dir = os.path.join(output_base_dir, domain, f"{date_str}_{url_hash}")
    os.makedirs(save_dir, exist_ok=True)
    
    metadata = {
        "url": url,
        "crawl_timestamp": datetime.now().isoformat(),
        "domain": domain,
        "error": error
    }
    
    # Save metadata
    with open(os.path.join(save_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
        
    # Save content (a11y tree) if available
    if content:
        with open(os.path.join(save_dir, "a11y_tree.json"), "w", encoding="utf-8") as f:
            # Content is likely a dict or list from the snapshot, dump as json
            json.dump(content, f, indent=2)
            
    print(f"Saved data for {url} to {save_dir}")

async def fetch_and_save(urls, output_dir):
    """
    Fetches content for multiple URLs and saves them to disk.
    """
    user_data_dir = os.path.join(os.getcwd(), "chrome_user_data")
    
    print(f"Starting crawl of {len(urls)} URLs...")
    
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"]
            )
            
            for i, url in enumerate(urls):
                if i > 0:
                    await asyncio.sleep(2) # Politeness delay
                
                print(f"Fetching {url}...")
                content = None
                error = None
                
                try:
                    page = await context.new_page()
                    await page.goto(url, timeout=30000)
                    # Get accessibility snapshot
                    content = await page.accessibility.snapshot()
                    
                    await asyncio.sleep(3) # Wait a bit before closing
                    await page.close()
                except Exception as e:
                    print(f"Error fetching {url}: {e}")
                    error = str(e)
                
                await save_crawl_data(url, content, error, output_dir)
                
            await context.close()
    except Exception as e:
        print(f"Error in Playwright execution: {e}")

def read_crawled_data(input_dir):
    """
    Reads crawled data from the specified directory.
    Recursively searches for metadata.json and a11y_tree.json pairs.
    """
    results = []
    
    if not os.path.exists(input_dir):
        print(f"Input directory {input_dir} does not exist.")
        return results

    print(f"Reading crawled data from {input_dir}...")
    
    for root, dirs, files in os.walk(input_dir):
        if "metadata.json" in files:
            meta_path = os.path.join(root, "metadata.json")
            content_path = os.path.join(root, "a11y_tree.json")
            
            try:
                with open(meta_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                
                content = None
                if os.path.exists(content_path):
                    with open(content_path, "r", encoding="utf-8") as f:
                        content = json.load(f)
                
                # Only include if we have content and no error (or handle errors as needed)
                if content:
                    results.append({
                        "url": metadata.get("url"),
                        "metadata": metadata,
                        "content": content
                    })
            except Exception as e:
                print(f"Error reading data in {root}: {e}")
                
    return results

def generate_briefing(client, contents, prompt_template, model="google/gemini-flash-1.5"):
    """Generates a briefing using the OpenAI client."""
    
    if not contents:
        return "No content available to generate a briefing."

    # Prepare the content for the LLM
    # We'll dump the a11y tree to JSON to make it readable for the LLM
    # We might want to limit the size if it's too huge, but for now let's dump it.
    context_data = []
    for item in contents:
        context_data.append({
            "url": item["url"],
            "content": item["content"]
        })
        
    context_str = json.dumps(context_data, indent=2)
    
    full_prompt = f"{prompt_template}\n\nSource Data:\n{context_str}"

    try:
        response = client.chat.completions.create(
            model=model, 
            messages=[
                {"role": "system", "content": "You are a helpful assistant creating a daily briefing."},
                {"role": "user", "content": full_prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error generating briefing: {e}"

async def main():
    parser = argparse.ArgumentParser(description="Batch Briefing Script")
    parser.add_argument("--urls", nargs="+", help="List of URLs to crawl")
    parser.add_argument("--output-dir", default="output/briefing", help="Directory to save crawled data")
    parser.add_argument("--input-dir", help="Directory to read crawled data from. If set, crawling is skipped.")
    parser.add_argument("--prompt", default="Please provide a summary of the top stories from these sources.", help="Prompt for the LLM")
    parser.add_argument("--model", default="google/gemini-flash-1.5", help="LLM model to use (default: google/gemini-flash-1.5)")
    
    args = parser.parse_args()
    
    # Part 1: Browsing / Loading Data
    crawled_data_dir = args.output_dir
    
    if args.input_dir:
        print(f"Input directory provided: {args.input_dir}. Skipping crawl.")
        crawled_data_dir = args.input_dir
    else:
        if not args.urls:
            print("Error: You must provide --urls OR --input-dir")
            return
            
        print("Starting Browsing Phase...")
        await fetch_and_save(args.urls, args.output_dir)
        crawled_data_dir = args.output_dir

    # Part 2: LLM Generation
    print("\nStarting LLM Generation Phase...")
    
    contents = read_crawled_data(crawled_data_dir)
    
    if not contents:
        print("No valid content found to process.")
        return

    client = get_openai_client()
    if not client:
        return

    print(f"Generating briefing from {len(contents)} sources...")
    briefing = generate_briefing(client, contents, args.prompt, args.model)
    
    print("\n=== Daily Briefing ===\n")
    print(briefing)

if __name__ == "__main__":
    asyncio.run(main())
