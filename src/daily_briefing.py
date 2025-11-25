import asyncio
import os
import json
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

async def fetch_all_contents(urls):
    """
    Fetches content for multiple URLs sequentially using a single browser instance
    with persistent context (headed, chrome, user data in cwd).
    Implements polite browsing: delays between requests and before closing pages.
    """
    results = []
    user_data_dir = os.path.join(os.getcwd(), "chrome_user_data")
    
    try:
        async with async_playwright() as p:
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=False,
                channel="chrome",
                args=["--disable-blink-features=AutomationControlled"]
            )
            
            async def fetch_single(url):
                result = {"url": url, "content": None, "error": None}
                try:
                    page = await context.new_page()
                    await page.goto(url, timeout=30000)
                    snapshot = await page.accessibility.snapshot()
                    result["content"] = snapshot
                    
                    # Wait a few seconds before closing (politeness)
                    await asyncio.sleep(3)
                    await page.close()
                except Exception as e:
                    print(f"Error fetching {url}: {e}")
                    result["error"] = str(e)
                return result

            for i, url in enumerate(urls):
                # Open one and wait a moment before opening another (if not the first one)
                if i > 0:
                    await asyncio.sleep(2)
                
                results.append(await fetch_single(url))
                
            await context.close()
    except Exception as e:
        print(f"Error in Playwright execution: {e}")
    
    return results

def generate_briefing(client, contents, prompt_template):
    """Generates a briefing using the OpenAI client."""
    
    # Filter out failed fetches for the prompt
    valid_contents = [c for c in contents if c["content"] is not None]
    
    if not valid_contents:
        return "No content could be fetched to generate a briefing."

    # Prepare the content for the LLM
    # We'll dump the a11y tree to JSON to make it readable for the LLM
    context_str = json.dumps(valid_contents, indent=2)
    
    full_prompt = f"{prompt_template}\n\nSource Data:\n{context_str}"

    try:
        response = client.chat.completions.create(
            model="google/gemini-flash-1.5", # Using the same model as in select_threads.py
            messages=[
                {"role": "system", "content": "You are a helpful assistant creating a daily briefing."},
                {"role": "user", "content": full_prompt}
            ]
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error generating briefing: {e}"

async def main():
    # Example usage
    # In a real scenario, these might come from arguments or a config file
    urls = [
        "https://news.ycombinator.com/",
        "https://www.bbc.com/news"
    ]
    
    prompt = "Please provide a summary of the top stories from these sources."
    
    print(f"Fetching content from {len(urls)} sources...")
    contents = await fetch_all_contents(urls)
    
    client = get_openai_client()
    if not client:
        return

    print("Generating briefing...")
    briefing = generate_briefing(client, contents, prompt)
    
    print("\n=== Daily Briefing ===\n")
    print(briefing)

if __name__ == "__main__":
    asyncio.run(main())
