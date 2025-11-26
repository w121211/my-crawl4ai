"""
Simple crawler using crawl4ai with:
- Headed browser (visible)
- Wait until fully rendered
- Cache enabled, crawl4ai's default cache TTL is 7 days

Run with: uv run python src/crawl4ai/simple_crawler.py
"""

import asyncio
import json
import base64
from pathlib import Path
from datetime import datetime
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode


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
        # Screenshot is base64 encoded
        with open(png_path, "wb") as f:
            f.write(base64.b64decode(screenshot_data))
        saved_files["screenshot"] = str(png_path)

    return saved_files


async def crawl_urls(urls: list[str]) -> list[dict]:
    """
    Crawl given URLs with headed browser, wait for render, and cache enabled.

    Args:
        urls: List of URLs to crawl

    Returns:
        List of crawl results with url, success, status, and content
    """

    # Browser config: headed (visible) browser with stealth mode
    browser_config = BrowserConfig(
        headless=False,        # Visible browser
        verbose=True,          # Log details
        enable_stealth=True,   # Basic bot detection evasion
    )

    # Crawler config: wait for render, enable cache
    crawler_config = CrawlerRunConfig(
        # Wait until page is fully rendered
        # Use "domcontentloaded" instead of "networkidle" for sites with continuous requests
        wait_until="domcontentloaded",
        delay_before_return_html=3.0,  # Wait 3 seconds for JS to render
        page_timeout=60000,            # 60 second timeout
        screenshot=True,

        # Enable cache (default 7-day TTL)
        cache_mode=CacheMode.ENABLED,

        verbose=True,
    )

    results = []

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for url in urls:
            print(f"\n{'='*50}")
            print(f"Crawling: {url}")
            print('='*50)

            result = await crawler.arun(url=url, config=crawler_config)

            # Verify crawl success
            crawl_result = {
                "url": result.url,
                "success": result.success,
                "status_code": result.status_code,
                "error": result.error_message if not result.success else None,
                "html_length": len(result.html) if result.html else 0,
                "markdown": None,
                "screenshot": None,
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

                print(f"✓ Success - Status: {result.status_code}")
                print(f"  HTML: {crawl_result['html_length']} bytes")
                print(f"  Markdown: {len(crawl_result['markdown'])} chars")
            else:
                print(f"✗ Failed: {result.error_message}")

            results.append(crawl_result)

    return results


async def main():
    # Example URLs to crawl
    urls = [
        # "https://example.com",
        # Add more URLs here
        # "https://finance.yahoo.com/"
        "https://www.reddit.com/r/stocks/"
    ]

    results = await crawl_urls(urls)

    # Summary
    print(f"\n{'='*50}")
    print("CRAWL SUMMARY")
    print('='*50)

    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"{status} {r['url']} - {r['status_code']}")

        # Save result to files
        screenshot_data = r.pop("screenshot", None)  # Remove from dict before saving
        saved = save_crawl_result(r, screenshot_data)

        print(f"   Saved: {saved.get('json')}")
        if saved.get("markdown"):
            print(f"   Saved: {saved.get('markdown')}")
        if saved.get("screenshot"):
            print(f"   Saved: {saved.get('screenshot')}")

    return results


if __name__ == "__main__":
    results = asyncio.run(main())
