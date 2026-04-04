import calendar
import logging
import requests
import os
from app.models.schemas import ArticleResult

logger = logging.getLogger(__name__)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")

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


def search_google_api(
    name: str,
    city: str | None,
    year: int | None,
    month: int | None,
    max_results: int = 10,
) -> list[ArticleResult]:
    """
    Uses the official Google Custom Search JSON API.
    No browser needed — works reliably on any server.
    Free for 100 queries/day.
    """
    if not GOOGLE_API_KEY or not GOOGLE_CSE_ID:
        logger.error("[GoogleAPI] GOOGLE_API_KEY or GOOGLE_CSE_ID not set")
        return []

    query = _build_query(name, city, year, month)
    logger.info(f"[GoogleAPI] Query: {query!r}")

    results: list[ArticleResult] = []

    # Google CSE returns max 10 per request, so we make 2 requests for 20 total
    for start in [1, 11]:
        if len(results) >= max_results:
            break

        try:
            response = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_API_KEY,
                    "cx": GOOGLE_CSE_ID,
                    "q": query,
                    "num": 10,
                    "start": start,
                },
                timeout=10,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            logger.error(f"[GoogleAPI] Request error: {e}")
            break

        items = data.get("items", [])
        if not items:
            logger.info("[GoogleAPI] No more items returned")
            break

        for item in items:
            url = item.get("link", "")
            if not url.startswith("http") or _is_blocked(url):
                continue

            results.append(ArticleResult(
                title=item.get("title", "Untitled"),
                url=url,
                source=_extract_domain(url),
                snippet=item.get("snippet"),
            ))

            if len(results) >= max_results:
                break

    logger.info(f"[GoogleAPI] Found {len(results)} results")
    return results