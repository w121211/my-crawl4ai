"""
Deep crawler using crawl4ai with:
- BFS deep crawling with configurable depth (max 1)
- Domain-based link filtering
- Sequential crawling with polite delays
- Headed browser (visible)

Run with: uv run python src/deep_crawler.py
"""

import asyncio
from urllib.parse import urlparse
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.deep_crawling import BFSDeepCrawlStrategy
from crawl4ai.deep_crawling.filters import FilterChain, URLPatternFilter

from simple_crawler import save_crawl_result


# =============================================================================
# CONFIGURATION - Modify these for your crawl
# =============================================================================

# URLs to crawl
URLS = [
    # "https://example.com",
    "https://m.cnyes.com/news/cat/headline"
]

# Crawl depth (0 = starting page only, 1 = follow links once)
MAX_DEPTH = 1

# Optional: URL pattern filter (e.g., ["*docs*", "*guide*"])
# Set to None to disable
# URL_FILTERS = None  # or ["*blog*", "*article*"]
URL_FILTERS = ["*news/id/*"]

# Delay between requests (seconds) - be polite!
DELAY_RANGE = (1.0, 2.0)


# =============================================================================
# CRAWLER
# =============================================================================


async def deep_crawl(
    urls: list[str], max_depth: int = 1, link_patterns: list[str] | None = None
):
    """
    Deep crawl URLs with link following and polite delays.

    Args:
        urls: Starting URLs
        max_depth: How many levels to follow links (max 1)
        link_patterns: Optional URL patterns to filter links
    """
    max_depth = min(max_depth, 1)  # Cap at 1

    # Browser config: headed, stealth
    browser_config = BrowserConfig(
        headless=False,
        verbose=True,
        enable_stealth=True,
    )

    # Build filter chain
    filters = []
    if link_patterns:
        filters.append(URLPatternFilter(patterns=link_patterns))

    # Deep crawl strategy
    deep_strategy = BFSDeepCrawlStrategy(
        max_depth=max_depth,
        include_external=False,  # Stay within domain
        filter_chain=FilterChain(filters),  # Empty chain if no filters
    )

    # Crawler config
    crawler_config = CrawlerRunConfig(
        deep_crawl_strategy=deep_strategy,
        # stream=False,
        stream=True,
        semaphore_count=1,  # Process one page at a time
        # Page loading
        wait_until="domcontentloaded",
        delay_before_return_html=2.0,
        page_timeout=60000,
        screenshot=True,
        # Cache
        cache_mode=CacheMode.ENABLED,
        verbose=True,
    )

    results = []

    async with AsyncWebCrawler(config=browser_config) as crawler:
        for start_url in urls:
            print(f"\n{'=' * 60}")
            print(f"Starting deep crawl: {start_url}")
            print(f"Max depth: {max_depth}")
            print("=" * 60)

            # Get domain for logging
            domain = urlparse(start_url).netloc

            # Stream results one-by-one
            crawl_count = 0
            async for result in await crawler.arun(
                url=start_url, config=crawler_config
            ):
                crawl_count += 1

                # Build result dict
                crawl_result = {
                    "url": result.url,
                    "success": result.success,
                    "status_code": result.status_code,
                    "error": result.error_message if not result.success else None,
                    "html_length": len(result.html) if result.html else 0,
                    "markdown": None,
                    "links_found": 0,
                }

                screenshot_data = None

                if result.success:
                    # Extract markdown
                    if hasattr(result.markdown, "raw_markdown"):
                        crawl_result["markdown"] = result.markdown.raw_markdown
                    else:
                        crawl_result["markdown"] = (
                            str(result.markdown) if result.markdown else ""
                        )

                    # Count links
                    if result.links:
                        crawl_result["links_found"] = len(
                            result.links.get("internal", [])
                        )

                    # Screenshot
                    if result.screenshot:
                        screenshot_data = result.screenshot

                    print(f"\n[{crawl_count}] ✓ {result.url}")
                    print(
                        f"    Status: {result.status_code}, Links: {crawl_result['links_found']}"
                    )
                else:
                    print(f"\n[{crawl_count}] ✗ {result.url}")
                    print(f"    Error: {result.error_message}")

                # Save immediately
                saved = save_crawl_result(crawl_result, screenshot_data)
                print(f"    Saved: {saved.get('json')}")

                results.append(crawl_result)

            print(f"\nCompleted {crawl_count} pages from {domain}")

    return results


async def main():
    results = await deep_crawl(
        urls=URLS,
        max_depth=MAX_DEPTH,
        link_patterns=URL_FILTERS,
    )

    # Summary
    print(f"\n{'=' * 60}")
    print("CRAWL SUMMARY")
    print("=" * 60)

    success = sum(1 for r in results if r["success"])
    print(
        f"Total: {len(results)} pages ({success} success, {len(results) - success} failed)"
    )

    for r in results:
        status = "✓" if r["success"] else "✗"
        print(f"  {status} {r['url']}")

    return results


if __name__ == "__main__":
    asyncio.run(main())
