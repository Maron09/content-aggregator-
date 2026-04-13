import calendar
import logging
import time
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

from models.schemas import ArticleResult

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
    Tries multiple selector strategies so it works across
    different Google HTML structures and environments.
    """
    soup = BeautifulSoup(html, "html.parser")
    results: list[ArticleResult] = []

    # --- Strategy 1: div#rso > h3 > parent anchor (current approach) ---
    rso = soup.select_one("div#rso")
    if rso:
        logger.info(f"[GoogleScraper] Strategy 1 — h3 count in rso: {len(rso.find_all('h3'))}")
        for h3 in rso.find_all("h3"):
            anchor = h3.find_parent("a")
            if not anchor:
                continue
            href = anchor.get("href", "")
            if not href.startswith("http") or _is_blocked(href):
                continue
            title = h3.get_text(strip=True)
            if not title:
                continue
            snippet = _extract_snippet(anchor)
            results.append(ArticleResult(
                title=title,
                url=href,
                source=_extract_domain(href),
                snippet=snippet,
            ))
            if len(results) >= max_results:
                break

    if results:
        logger.info(f"[GoogleScraper] Strategy 1 succeeded: {len(results)} results")
        return results

    # --- Strategy 2: any h3 with a parent anchor containing http ---
    logger.info("[GoogleScraper] Strategy 1 failed, trying Strategy 2")
    for h3 in soup.find_all("h3"):
        anchor = h3.find_parent("a")
        if not anchor:
            continue
        href = anchor.get("href", "")
        if not href.startswith("http") or _is_blocked(href):
            continue
        title = h3.get_text(strip=True)
        if not title:
            continue
        snippet = _extract_snippet(anchor)
        results.append(ArticleResult(
            title=title,
            url=href,
            source=_extract_domain(href),
            snippet=snippet,
        ))
        if len(results) >= max_results:
            break

    if results:
        logger.info(f"[GoogleScraper] Strategy 2 succeeded: {len(results)} results")
        return results

    # --- Strategy 3: all anchors with href starting http that have text ---
    logger.info("[GoogleScraper] Strategy 2 failed, trying Strategy 3")
    seen = set()
    for anchor in soup.find_all("a", href=True):
        href = anchor["href"]
        if not href.startswith("http") or _is_blocked(href):
            continue
        if href in seen:
            continue
        title = anchor.get_text(strip=True)
        if len(title) < 20:  # skip nav links and short labels
            continue
        seen.add(href)
        results.append(ArticleResult(
            title=title[:120],
            url=href,
            source=_extract_domain(href),
            snippet=None,
        ))
        if len(results) >= max_results:
            break

    logger.info(f"[GoogleScraper] Strategy 3 result count: {len(results)}")
    return results


def _extract_snippet(anchor) -> str | None:
    """
    Walks up from the anchor to find a nearby text block
    that looks like a description snippet.
    """
    container = anchor.find_parent("div")
    if not container:
        return None
    for div in container.find_all("div"):
        text = div.get_text(strip=True)
        if 40 < len(text) < 400:
            return text
    return None


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

            # Handle consent popup
            try:
                consent_btn = page.locator("button:has-text('Accept all')")
                if consent_btn.is_visible(timeout=3000):
                    consent_btn.click()
                    page.wait_for_timeout(1000)
            except PlaywrightTimeout:
                pass

            # Try div#rso first, fall back to just waiting for h3
            try:
                page.wait_for_selector("div#rso", timeout=10000)
            except PlaywrightTimeout:
                logger.warning("[GoogleScraper] div#rso not found, trying h3 fallback")
                try:
                    page.wait_for_selector("h3", timeout=8000)
                except PlaywrightTimeout:
                    logger.error("[GoogleScraper] No results structure found at all")
                    return []

            html = page.content()

        except PlaywrightTimeout:
            logger.error("[GoogleScraper] Page load timed out")
            return []
        except Exception as e:
            logger.error(f"[GoogleScraper] Unexpected error: {e}")
            return []
        finally:
            browser.close()

    results = _parse_results(html, max_results)
    logger.info(f"[GoogleScraper] Found {len(results)} results")
    return results