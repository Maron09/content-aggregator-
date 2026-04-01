import calendar
import logging
import time
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from app.models.schemas import ArticleResult

logger = logging.getLogger(__name__)

BLOCKLIST = {
    "google.com", "accounts.google.com",
    "facebook.com", "twitter.com", "instagram.com",
    "amazon.com", "ebay.com",
}


def _build_query(name: str, city: str | None, year: int | None, month: int | None) -> str:
    parts = [name]
    if city:
        parts.append(city)
    if month is not None:
        parts.append(calendar.month_name[month])
    if year is not None:
        parts.append(str(year))
    return " ".join(parts)


def _extract_domain(url: str) -> str:
    from urllib.parse import urlparse
    return urlparse(url).netloc.replace("www.", "")


def _is_blocked(url: str) -> bool:
    domain = _extract_domain(url)
    return any(blocked in domain for blocked in BLOCKLIST)


def _parse_results(html: str, max_results: int) -> list[ArticleResult]:
    """
    Parses the fully rendered Google HTML using BeautifulSoup.
    Playwright fetches the page, this function extracts the data.
    Keeping them separate makes it easy to unit test parsing logic.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[ArticleResult] = []

    rso = soup.select_one("div#rso")
    if not rso:
        logger.warning("[GoogleScraper] div#rso not found")
        return []

    all_h3s = rso.find_all("h3")
    logger.info(f"[GoogleScraper] h3 count in rso: {len(all_h3s)}")

    for i, h3 in enumerate(all_h3s):
        title = h3.get_text(strip=True)
        logger.info(f"[GoogleScraper] h3[{i}] title: {title!r}")

        anchor = h3.find_parent("a")
        if not anchor:
            logger.info(f"[GoogleScraper] h3[{i}] — no parent <a> found, skipping")
            continue

        href = anchor.get("href", "")
        logger.info(f"[GoogleScraper] h3[{i}] — href: {href!r}")

        if not href.startswith("http"):
            logger.info(f"[GoogleScraper] h3[{i}] — skipped: not http")
            continue

        if _is_blocked(href):
            logger.info(f"[GoogleScraper] h3[{i}] — skipped: blocked domain")
            continue

        source = _extract_domain(href)
        results.append(ArticleResult(
            title=title,
            url=href,
            source=source,
            snippet=None,
        ))

        if len(results) >= max_results:
            break

    logger.info(f"[GoogleScraper] Final result count: {len(results)}")
    return results


def scrape_google_articles(
    name: str,
    city: str | None,
    year: int,
    month: int | None,
    max_results: int = 10,
) -> list[ArticleResult]:
    """
    Uses a headless Chromium browser via Playwright to fetch
    fully JavaScript-rendered Google search results.

    Flow:
      1. Launch headless Chromium with realistic browser fingerprint
      2. Navigate to Google search URL
      3. Wait for results container to appear in the DOM
      4. Extract the rendered HTML and pass to _parse_results()
      5. Close browser cleanly
    """
    query = _build_query(name, city, year, month)
    params = {"q": query, "num": 20, "hl": "en"}
    url = f"https://www.google.com/search?{urlencode(params)}"

    logger.info(f"[GoogleScraper] Playwright query: {query!r}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",  # hides headless flag
            ],
        )

        # Use a realistic viewport + locale so Google returns proper results
        context = browser.new_context(
            viewport={"width": 1280, "height": 800},
            locale="en-US",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
        )

        page = context.new_page()

        try:
            page.goto(url, wait_until="networkidle", timeout=30000)

            page.wait_for_timeout(2000)

            try:
                consent_btn = page.locator("button:has-text('Accept all')")
                if consent_btn.is_visible(timeout=3000):
                    consent_btn.click()
                    page.wait_for_timeout(1000)
            except PlaywrightTimeout:
                pass

            page.wait_for_selector("div#rso", timeout=15000)
            html = page.content()

        except PlaywrightTimeout:
            logger.error("[GoogleScraper] Timed out waiting for results")
            return []
        except Exception as e:
            logger.error(f"[GoogleScraper] Unexpected error: {e}")
            return []
        finally:
            browser.close()

    results = _parse_results(html, max_results)
    logger.info(f"[GoogleScraper] Found {len(results)} results")
    return results