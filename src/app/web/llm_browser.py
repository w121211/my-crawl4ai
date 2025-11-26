"""
LLM-guided browsing with Crawl4AI

Features:
- Goal-driven navigation with LLM analysis
- Smart content extraction from any page type
- Automatic URL deduplication to prevent revisiting pages
- Link discovery and sequential exploration
- Customizable field extraction via goal definition
- Max depth = 1 (root page + discovered links)
- Polite browsing with delays

Usage:
    from crawl4ai.llm_browser import LLMBrowser

    browser = LLMBrowser(
        start_url="https://example.com",
        goal="Find recent news articles about AI. Extract: title, date, summary, author"
    )
    await browser.browse()

Run with: uv run python src/crawl4ai/llm_browser.py
"""

import asyncio
import json
import os
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

from dotenv import load_dotenv
from openrouter import OpenRouter

from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig

# Load environment variables
load_dotenv()


class LLMBrowser:
    """LLM-guided web browser using Crawl4AI"""

    def __init__(
        self,
        start_url: str,
        goal: str,
        max_depth: int = 1,
        sleep_between_requests: float = 2.5,
        llm_model: str = "google/gemini-flash-1.5",
        output_base_dir: str = "output/crawl4ai",
    ):
        """
        Initialize LLM Browser

        Args:
            start_url: Starting URL to begin browsing
            goal: Navigation goal with custom field definitions
                  Example: "Find news articles. Extract: title, date, summary"
            max_depth: Maximum depth to explore (default: 1 = root + discovered links)
            sleep_between_requests: Seconds to wait between page requests (polite browsing)
            llm_model: OpenRouter model to use for analysis
            output_base_dir: Base directory for saving results
        """
        self.start_url = start_url
        self.goal = goal
        self.max_depth = max_depth
        self.sleep_seconds = sleep_between_requests
        self.llm_model = llm_model
        self.output_base_dir = output_base_dir

        # Initialize OpenRouter client
        api_key = os.getenv("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY must be set in .env file")

        self.llm_client = OpenRouter(api_key=api_key)

        # Track crawl session
        self.session_start = datetime.now()
        self.pages_crawled = []
        self.visited_urls = set()  # Track visited URLs to prevent duplicates
        self.output_dir: Optional[Path] = None

    def _create_output_directory(self) -> Path:
        """Create output directory: output/crawl4ai/<date>/<timestamp>-<sanitized-url>/"""
        date_str = self.session_start.strftime("%Y%m%d")
        timestamp = self.session_start.strftime("%Y%m%d_%H%M%S")

        # Sanitize start URL for directory name
        parsed = urlparse(self.start_url)
        url_clean = parsed.netloc + parsed.path.rstrip("/")
        url_clean = re.sub(r"[^\w\-.]", "_", url_clean)  # Replace special chars
        if len(url_clean) > 80:
            url_clean = url_clean[:80]

        # Create directory structure
        output_dir = Path(self.output_base_dir) / date_str / f"{timestamp}-{url_clean}"
        output_dir.mkdir(parents=True, exist_ok=True)

        # Create pages subdirectory
        (output_dir / "pages").mkdir(exist_ok=True)

        return output_dir

    def _get_llm_prompt(self, page_content: str, url: str) -> str:
        """Generate LLM prompt for page analysis"""
        return f"""You are analyzing a web page to help with goal-directed browsing.

NAVIGATION GOAL:
{self.goal}

CURRENT PAGE URL:
{url}

TASK:
1. Extract content based on the navigation goal:
   - Extract relevant information from this page according to the goal
   - This could be article content, news summaries, product details, etc.
   - If the page doesn't contain goal-relevant content, return null for content fields

2. Extract relevant links for further navigation:
   - Find links that are relevant to the navigation goal
   - This includes both listing pages AND content pages that link to related content
   - For example: news article links, related posts, category pages, pagination links
   - Return FULL URLs (not relative paths)
   - Limit to top 10 most relevant links

3. Extract custom fields as specified in the navigation goal above.

OUTPUT REQUIREMENTS:
- Return ONLY valid JSON (no markdown, no code blocks, no explanation)
- Required fields: "links" (array of URL strings)
- Custom fields: Include any fields mentioned in the navigation goal
- If a custom field cannot be extracted, set it to null

PAGE CONTENT (Markdown):
{page_content[:15000]}
"""

    async def _crawl_page(self, url: str, crawler: AsyncWebCrawler) -> dict:
        """Crawl a single page and return result"""
        print(f"\n{'=' * 60}")
        print(f"Crawling: {url}")
        print("=" * 60)

        crawler_config = CrawlerRunConfig(
            wait_until="domcontentloaded",
            delay_before_return_html=3.0,
            page_timeout=60000,
            cache_mode=CacheMode.ENABLED,
            verbose=False,
        )

        result = await crawler.arun(url=url, config=crawler_config)

        crawl_result = {
            "url": result.url,
            "success": result.success,
            "status_code": result.status_code,
            "error": result.error_message if not result.success else None,
            "markdown": None,
        }

        if result.success:
            # Extract markdown content
            if hasattr(result.markdown, "raw_markdown"):
                crawl_result["markdown"] = result.markdown.raw_markdown
            else:
                crawl_result["markdown"] = (
                    str(result.markdown) if result.markdown else ""
                )

            print(f"✓ Success - Status: {result.status_code}")
            print(f"  Markdown: {len(crawl_result['markdown'])} chars")
        else:
            print(f"✗ Failed: {result.error_message}")

        return crawl_result

    def _analyze_with_llm(self, page_content: str, url: str) -> dict:
        """Analyze page content with LLM using JSON mode"""
        print("\n  Analyzing with LLM...")

        prompt = self._get_llm_prompt(page_content, url)

        try:
            response = self.llm_client.chat.send(
                model=self.llm_model,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)

            # Validate required fields
            if "links" not in result:
                print(
                    "  ⚠ Warning: LLM response missing 'links' field, using empty list"
                )
                result.setdefault("links", [])

            print(f"  Links found: {len(result.get('links', []))}")

            # Show extracted content info
            custom_fields = {
                k: v for k, v in result.items() if k != "links" and v is not None
            }
            if custom_fields:
                print(f"  Extracted fields: {list(custom_fields.keys())}")

            return result

        except json.JSONDecodeError as e:
            print(f"  ✗ JSON parsing error: {e}")
            print("  Using fallback empty result")
            return {"page_type": "unknown", "links": [], "error": str(e)}
        except Exception as e:
            print(f"  ✗ LLM analysis error: {e}")
            return {"page_type": "unknown", "links": [], "error": str(e)}

    def _save_page_result(self, page_data: dict, page_index: int):
        """Save individual page result to JSON file"""
        domain = urlparse(page_data["url"]).netloc
        safe_domain = re.sub(r"[^\w\-.]", "_", domain)

        filename = f"page-{page_index}-{safe_domain}.json"
        filepath = self.output_dir / "pages" / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(page_data, f, indent=2, ensure_ascii=False)

        print(f"  Saved: {filepath}")
        return str(filepath)

    def _save_summary(self):
        """Save crawl session summary"""
        summary = {
            "start_url": self.start_url,
            "goal": self.goal,
            "session_start": self.session_start.isoformat(),
            "session_end": datetime.now().isoformat(),
            "max_depth": self.max_depth,
            "total_pages_crawled": len(self.pages_crawled),
            "llm_model": self.llm_model,
            "pages": [
                {
                    "index": i,
                    "url": p["url"],
                    "success": p["success"],
                    "depth": p.get("depth", 0),
                }
                for i, p in enumerate(self.pages_crawled)
            ],
            "total_urls_visited": len(self.visited_urls),
            "duplicate_urls_skipped": len(self.visited_urls) - len(self.pages_crawled),
        }

        filepath = self.output_dir / "summary.json"
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)

        print(f"\n{'=' * 60}")
        print(f"Session summary saved: {filepath}")
        print("=" * 60)

    async def browse(self):
        """Execute the browsing session"""
        print(f"\n{'=' * 60}")
        print("LLM-GUIDED BROWSING SESSION")
        print("=" * 60)
        print(f"Start URL: {self.start_url}")
        print(f"Goal: {self.goal}")
        print(f"Max depth: {self.max_depth}")
        print(f"Sleep between requests: {self.sleep_seconds}s")
        print(f"LLM model: {self.llm_model}")

        # Create output directory
        self.output_dir = self._create_output_directory()
        print(f"Output directory: {self.output_dir}")

        # Browser config: headed mode
        browser_config = BrowserConfig(
            headless=False,
            verbose=False,
            enable_stealth=True,
        )

        async with AsyncWebCrawler(config=browser_config) as crawler:
            # Crawl root page (depth 0)
            crawl_result = await self._crawl_page(self.start_url, crawler)

            # Mark start URL as visited
            self.visited_urls.add(self.start_url)

            if not crawl_result["success"]:
                print("\n✗ Failed to crawl start URL. Aborting.")
                return

            # Analyze with LLM
            analysis = self._analyze_with_llm(
                crawl_result["markdown"], crawl_result["url"]
            )

            # Store page data
            page_data = {
                "url": crawl_result["url"],
                "success": crawl_result["success"],
                "status_code": crawl_result["status_code"],
                "depth": 0,
                "crawled_at": datetime.now().isoformat(),
                "analysis": analysis,
                "markdown_length": len(crawl_result["markdown"])
                if crawl_result["markdown"]
                else 0,
            }

            self.pages_crawled.append(page_data)
            self._save_page_result(page_data, 0)

            # Extract links to explore and filter out already visited URLs
            discovered_links = analysis.get("links", [])
            links_to_explore = [
                url for url in discovered_links if url not in self.visited_urls
            ][:10]

            # Show deduplication info
            if len(discovered_links) > len(links_to_explore):
                skipped = len(discovered_links) - len(links_to_explore)
                print(f"\n  Skipped {skipped} already-visited URL(s)")

            if self.max_depth >= 1 and links_to_explore:
                print(f"\nExploring {len(links_to_explore)} new links...")

                for i, link_url in enumerate(links_to_explore, start=1):
                    # Mark as visited before crawling to prevent race conditions
                    self.visited_urls.add(link_url)

                    # Polite browsing: sleep between requests
                    if i > 1:  # Don't sleep before first link
                        print(
                            f"\n  Sleeping {self.sleep_seconds}s (polite browsing)..."
                        )
                        await asyncio.sleep(self.sleep_seconds)

                    # Crawl discovered link
                    print(f"\n[Link {i}/{len(links_to_explore)}]")
                    link_crawl = await self._crawl_page(link_url, crawler)

                    if not link_crawl["success"]:
                        # Save failed page
                        failed_data = {
                            "url": link_url,
                            "success": False,
                            "status_code": link_crawl.get("status_code"),
                            "error": link_crawl.get("error"),
                            "depth": 1,
                            "crawled_at": datetime.now().isoformat(),
                        }
                        self.pages_crawled.append(failed_data)
                        self._save_page_result(failed_data, len(self.pages_crawled) - 1)
                        continue

                    # Analyze with LLM
                    link_analysis = self._analyze_with_llm(
                        link_crawl["markdown"], link_crawl["url"]
                    )

                    # Store page data
                    link_page_data = {
                        "url": link_crawl["url"],
                        "success": link_crawl["success"],
                        "status_code": link_crawl["status_code"],
                        "depth": 1,
                        "crawled_at": datetime.now().isoformat(),
                        "analysis": link_analysis,
                        "markdown_length": len(link_crawl["markdown"])
                        if link_crawl["markdown"]
                        else 0,
                    }

                    self.pages_crawled.append(link_page_data)
                    self._save_page_result(link_page_data, len(self.pages_crawled) - 1)

            # Save session summary
            self._save_summary()

            print(f"\n{'=' * 60}")
            print("BROWSING COMPLETE")
            print("=" * 60)
            print(f"Total pages crawled: {len(self.pages_crawled)}")
            print(f"Successful: {sum(1 for p in self.pages_crawled if p['success'])}")
            print(f"Failed: {sum(1 for p in self.pages_crawled if not p['success'])}")
            print(f"Output: {self.output_dir}")


async def main():
    """Example usage"""

    # Example: News browsing with content extraction
    browser = LLMBrowser(
        start_url="https://news.ycombinator.com/",
        goal="""
        Find interesting tech news articles and extract information from each page.

        For listing/index pages: Extract a brief summary of the top news today.
        For article pages: Extract the full article content.

        Always extract the following fields:
        - title: Page or article title
        - summary: Brief summary of the content (2-3 sentences)
        - topic: Main topic/category (e.g., AI, Web Dev, Hardware)
        - date: Publication date if available
        """,
        max_depth=1,
        sleep_between_requests=3.0,
    )

    await browser.browse()


if __name__ == "__main__":
    asyncio.run(main())
