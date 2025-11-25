import asyncio
import json
import os
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode
from crawl4ai.extraction_strategy import LLMExtractionStrategy


async def crawl_yahoo_finance_news():
    browser_config = BrowserConfig(headless=True)

    async with AsyncWebCrawler(config=browser_config) as crawler:
        # Step 1 & 2: Crawl Yahoo Finance and extract news links via LLM
        extraction_strategy = LLMExtractionStrategy(
            provider="openai/gpt-4o-mini",
            api_token=os.getenv("OPENAI_API_KEY"),
            instruction="""Extract URLs for headline news articles and important financial news from this page.
            Return as a JSON array of objects with 'title' and 'url' fields.
            Only include actual article links, not navigation or category links."""
        )

        print("Crawling Yahoo Finance homepage...")
        result = await crawler.arun(
            url="https://finance.yahoo.com",
            config=CrawlerRunConfig(
                extraction_strategy=extraction_strategy,
                cache_mode=CacheMode.BYPASS
            )
        )

        if not result.success:
            print(f"Failed to crawl Yahoo Finance: {result.error_message}")
            return

        # Parse extracted links
        try:
            news_links = json.loads(result.extracted_content)
            print(f"Found {len(news_links)} news articles")
        except json.JSONDecodeError as e:
            print(f"Failed to parse LLM response: {e}")
            print(f"Raw response: {result.extracted_content}")
            return

        # Step 3: Crawl each link one by one with delay
        results = []
        for i, item in enumerate(news_links):
            url = item.get('url', '')
            title = item.get('title', 'Unknown')

            if not url:
                continue

            print(f"[{i+1}/{len(news_links)}] Crawling: {title[:50]}...")

            article_result = await crawler.arun(
                url=url,
                config=CrawlerRunConfig(
                    cache_mode=CacheMode.BYPASS
                )
            )

            if article_result.success:
                results.append({
                    'title': title,
                    'url': url,
                    'content_length': len(article_result.markdown.raw_markdown),
                    'content': article_result.markdown.raw_markdown[:500]  # Preview
                })
                print(f"    ✓ Content length: {len(article_result.markdown.raw_markdown)}")
            else:
                print(f"    ✗ Failed: {article_result.error_message}")

            # Wait between requests to avoid rate limiting
            await asyncio.sleep(2)

        print(f"\nSuccessfully crawled {len(results)} articles")
        return results


if __name__ == "__main__":
    results = asyncio.run(crawl_yahoo_finance_news())

    # Optionally save results
    if results:
        with open("yahoo_finance_news.json", "w") as f:
            json.dump(results, f, indent=2)
        print("Results saved to yahoo_finance_news.json")
