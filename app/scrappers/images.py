import re
import calendar
import logging
from urllib.parse import urlencode
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
from models.schemas import ImageResult

logger = logging.getLogger(__name__)


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


def scrape_google_images(
    name: str,
    city: str | None,
    year: int | None,
    month: int | None,
    max_results: int = 20,
) -> list[ImageResult]:
    """
    Scrapes Google Images using Playwright.
    Google now serves all thumbnails as base64 data URIs so we
    can't extract them from <img> elements. Instead we extract
    the original full-size image URLs that Google embeds as
    strings inside the page's JavaScript source.
    """
    query = _build_query(name, city, year, month)
    params = {"q": query, "tbm": "isch", "hl": "en"}
    url = f"https://www.google.com/search?{urlencode(params)}"

    logger.info(f"[ImageScraper] Playwright query: {query!r}")

    html = ""

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
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
            page.wait_for_timeout(3000)

            # Handle consent popup
            try:
                consent_btn = page.locator("button:has-text('Accept all')")
                if consent_btn.is_visible(timeout=3000):
                    consent_btn.click()
                    page.wait_for_timeout(1000)
            except PlaywrightTimeout:
                pass

            html = page.content()
            logger.info(f"[ImageScraper] Got page HTML, length: {len(html)}")

        except PlaywrightTimeout:
            logger.error("[ImageScraper] Page load timed out")
            return []
        except Exception as e:
            logger.error(f"[ImageScraper] Unexpected error: {e}")
            return []
        finally:
            browser.close()

    if not html:
        return []

    # Google embeds original image URLs as quoted strings inside
    # script tags, typically followed by their dimensions.
    pattern = re.compile(
        r'"(https?://(?!(?:[^/"]*\.)?(?:google|gstatic|googleapis)\.)'
        r'[^"]+\.(?:jpg|jpeg|png|webp)(?:\?[^"]*)?)"'
        r'[^"]{0,100}?,\s*(\d{2,4}),\s*(\d{2,4})',
        re.IGNORECASE
    )

    seen = set()
    raw_results = []

    for img_url, width, height in pattern.findall(html):
        if img_url in seen:
            continue
        w, h = int(width), int(height)
        if w < 100 or h < 100:
            continue
        seen.add(img_url)
        raw_results.append({
            "image_url": img_url,
            "title": name,
            "width": w,
            "height": h,
        })
        if len(raw_results) >= 30:
            break

    logger.info(f"[ImageScraper] Regex found {len(raw_results)} image URLs in page source")

    # Build ImageResult objects
    image_results = []
    for item in raw_results[:max_results]:
        image_url = item.get("image_url", "")
        if not image_url or not image_url.startswith("http"):
            continue

        image_results.append(ImageResult(
            title=item.get("title") or f"{name} image",
            image_url=image_url,
            source_url=image_url,
            source="images.google.com",
            width=item.get("width"),
            height=item.get("height"),
        ))

    logger.info(f"[ImageScraper] Returning {len(image_results)} images")
    return image_results