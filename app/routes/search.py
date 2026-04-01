from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from app.models.schemas import SearchRequest, SearchResponse
from app.services.search_service import SearchService


router = APIRouter(prefix="/api/v1", tags=["search"])
search_service = SearchService()

@router.post("/search", response_model=SearchResponse)
async def search(
    payload: SearchRequest,
    use_cache: bool = Query(default=True),
):
    try:
        result = await search_service.search(payload, use_cache=use_cache)  # ← await
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    if not result.articles:
        raise HTTPException(
            status_code=404,
            detail="No results found. Try a different name or date range."
        )

    return result


@router.get("/debug/playwright")
async def debug_playwright(name: str):
    import asyncio
    import base64
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    from urllib.parse import urlencode
    from bs4 import BeautifulSoup

    def run():
        params = {"q": name, "num": 20, "hl": "en"}
        url = f"https://www.google.com/search?{urlencode(params)}"

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
                page.goto(url, wait_until="domcontentloaded", timeout=15000)

                # Accept consent if present
                try:
                    consent_btn = page.locator("button:has-text('Accept all')")
                    if consent_btn.is_visible(timeout=3000):
                        consent_btn.click()
                        page.wait_for_timeout(1000)
                except PlaywrightTimeout:
                    pass

                # Take screenshot BEFORE waiting for div.g
                screenshot_bytes = page.screenshot(full_page=False)
                screenshot_b64 = base64.b64encode(screenshot_bytes).decode()

                html = page.content()
                soup = BeautifulSoup(html, "html.parser")

                # Try multiple selectors so we can see which one matches
                selectors = {
                    "div.g":            len(soup.select("div.g")),
                    "div#search":       len(soup.select("div#search")),
                    "div#rso":          len(soup.select("div#rso")),
                    "h3":               len(soup.select("h3")),
                    "a[href]":          len(soup.select("a[href]")),
                }

                # Grab first 3000 chars of the rendered HTML
                html_snippet = html[:3000]

            except PlaywrightTimeout as e:
                return {"error": f"Timeout: {e}", "screenshot": None}
            finally:
                browser.close()

        return {
            "url": url,
            "selector_counts": selectors,
            "html_snippet": html_snippet,
            "screenshot_base64": screenshot_b64,
        }

    result = await asyncio.get_event_loop().run_in_executor(None, run)
    return result


@router.get("/debug/screenshot")
async def debug_screenshot(name: str):
    import asyncio
    import base64
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout
    from urllib.parse import urlencode

    def run():
        params = {"q": name, "num": 20, "hl": "en"}
        url = f"https://www.google.com/search?{urlencode(params)}"

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
            page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Wait a moment for JS to settle
            page.wait_for_timeout(3000)

            screenshot = page.screenshot(full_page=False)
            screenshot_b64 = base64.b64encode(screenshot).decode()
            page_title = page.title()
            browser.close()

        return {"title": page_title, "screenshot": screenshot_b64}

    result = await asyncio.get_event_loop().run_in_executor(None, run)

    # Return as HTML so you can see the screenshot directly in the browser
    return HTMLResponse(f"""
        <h2>Page title: {result['title']}</h2>
        <img src="data:image/png;base64,{result['screenshot']}" style="max-width:100%">
    """)