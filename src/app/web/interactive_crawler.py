"""
Interactive crawler using crawl4ai with LLM extraction.

Features:
- User provides target URL and extraction instruction
- Headed browser (visible) with human-like behavior
- Polite crawling with delays and stealth mode
- Results saved to output/<date>/

Run with: uv run python src/interactive_crawler.py
"""

import asyncio
import argparse
import json
import base64
import random
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
import os
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import LLMExtractionStrategy


def save_crawl_result(result: dict, screenshot_data: str | None = None) -> dict:
    """
    Save crawl result to output/<date>/<url>_<timestamp>.json/md/png

    Returns dict with saved file paths.
    """
    now = datetime.now()
    date_dir = now.strftime("%Y%m%d")
    timestamp = now.strftime("%Y%m%d_%H%M%S")

    # Clean URL for filename
    parsed = urlparse(result["url"])
    url_clean = parsed.netloc + parsed.path.rstrip("/")
    url_clean = url_clean.replace("/", "_").replace(":", "_").replace("?", "_")
    if len(url_clean) > 100:
        url_clean = url_clean[:100]

    # Create output directory
    output_dir = Path("output") / date_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    base_name = f"{url_clean}_{timestamp}"
    saved_files = {}

    # Save JSON (always)
    json_path = output_dir / f"{base_name}.json"
    json_data = {
        **result,
        "crawled_at": now.isoformat(),
    }
    # Remove markdown from JSON if saving separately
    if result.get("markdown"):
        json_data["markdown_file"] = f"{base_name}.md"
        del json_data["markdown"]

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)
    saved_files["json"] = str(json_path)

    # Save markdown if exists
    if result.get("markdown"):
        md_path = output_dir / f"{base_name}.md"
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(result["markdown"])
        saved_files["markdown"] = str(md_path)

    # Save screenshot if exists
    if screenshot_data:
        png_path = output_dir / f"{base_name}_screenshot.png"
        with open(png_path, "wb") as f:
            f.write(base64.b64decode(screenshot_data))
        saved_files["screenshot"] = str(png_path)

    # Save extracted content if exists
    if result.get("extracted_content"):
        extracted_path = output_dir / f"{base_name}_extracted.json"
        with open(extracted_path, "w", encoding="utf-8") as f:
            f.write(result["extracted_content"])
        saved_files["extracted"] = str(extracted_path)

    return saved_files


async def crawl_with_instruction(url: str, instruction: str) -> dict:
    """
    Crawl a URL with LLM extraction based on user instruction.

    Uses headed browser with human-like behavior for polite crawling.
    """

    # Browser config: headed browser with human-like settings
    browser_config = BrowserConfig(
        headless=False,           # Visible browser
        verbose=True,
        enable_stealth=True,      # Bot detection evasion
        # Human-like viewport
        viewport_width=1280,
        viewport_height=800,
    )

    # LLM extraction strategy
    extraction_strategy = LLMExtractionStrategy(
        provider="openai/gpt-4o-mini",
        api_token=os.getenv("OPENAI_API_KEY"),
        instruction=instruction
    )

    # Crawler config: polite crawling with human-like delays
    crawler_config = CrawlerRunConfig(
        # Wait for page to render
        wait_until="domcontentloaded",
        delay_before_return_html=random.uniform(2.0, 4.0),  # Random delay like human
        page_timeout=60000,
        screenshot=True,

        # LLM extraction
        extraction_strategy=extraction_strategy,

        # Cache enabled
        cache_mode=CacheMode.ENABLED,

        # Simulate human behavior
        simulate_user=True,        # Random mouse movements
        override_navigator=True,   # Hide automation flags

        verbose=True,
    )

    print(f"\n{'='*50}")
    print(f"Crawling: {url}")
    print(f"Instruction: {instruction}")
    print('='*50)

    # Add initial delay before crawling (polite)
    delay = random.uniform(1.0, 3.0)
    print(f"Waiting {delay:.1f}s before starting (polite delay)...")
    await asyncio.sleep(delay)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        result = await crawler.arun(url=url, config=crawler_config)

        crawl_result = {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "error": result.error_message if not result.success else None,
            "html_length": len(result.html) if result.html else 0,
            "markdown": None,
            "screenshot": None,
            "extracted_content": None,
            "instruction": instruction,
        }

        if result.success:
            # Extract markdown content
            if hasattr(result.markdown, 'raw_markdown'):
                crawl_result["markdown"] = result.markdown.raw_markdown
            else:
                crawl_result["markdown"] = str(result.markdown) if result.markdown else ""

            # Capture screenshot data
            if result.screenshot:
                crawl_result["screenshot"] = result.screenshot

            # Capture extracted content
            if result.extracted_content:
                crawl_result["extracted_content"] = result.extracted_content

            print(f"✓ Success - Status: {result.status_code}")
            print(f"  HTML: {crawl_result['html_length']} bytes")
            print(f"  Markdown: {len(crawl_result['markdown'])} chars")
            if result.extracted_content:
                print(f"  Extracted: {len(result.extracted_content)} chars")
        else:
            print(f"✗ Failed: {result.error_message}")

        return crawl_result


async def main():
    parser = argparse.ArgumentParser(
        description="Interactive crawler with LLM extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  uv run python src/interactive_crawler.py https://example.com "Extract all links"
  uv run python src/interactive_crawler.py https://news.ycombinator.com "Extract top 10 story titles and URLs as JSON array"
        """
    )
    parser.add_argument("url", help="Target URL to crawl")
    parser.add_argument("instruction", help="Extraction instruction for LLM")

    args = parser.parse_args()

    # Check for API key
    if not os.getenv("OPENAI_API_KEY"):
        print("Warning: OPENAI_API_KEY not set. LLM extraction may fail.")

    result = await crawl_with_instruction(args.url, args.instruction)

    # Save results
    print(f"\n{'='*50}")
    print("SAVING RESULTS")
    print('='*50)

    screenshot_data = result.pop("screenshot", None)
    saved = save_crawl_result(result, screenshot_data)

    print(f"Saved: {saved.get('json')}")
    if saved.get("markdown"):
        print(f"Saved: {saved.get('markdown')}")
    if saved.get("screenshot"):
        print(f"Saved: {saved.get('screenshot')}")
    if saved.get("extracted"):
        print(f"Saved: {saved.get('extracted')}")

    # Print extracted content preview
    if result.get("extracted_content"):
        print(f"\n{'='*50}")
        print("EXTRACTED CONTENT (preview)")
        print('='*50)
        content = result["extracted_content"]
        print(content[:1000] + "..." if len(content) > 1000 else content)

    return result


if __name__ == "__main__":
    asyncio.run(main())
