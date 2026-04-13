from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
import os
from app.models.schemas import SearchRequest, SearchResponse, DownloadRequest
from app.services.search_service import SearchService
from app.services.downloader import run_downloads
from pathlib import Path
import asyncio

DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", "/tmp/downloads"))
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


@router.post("/download")
async def download(payload: DownloadRequest):
    """
    Downloads selected items to the local downloads/ folder.
    Videos use yt-dlp, images use HTTP, articles saved as text.
    """
    if not payload.items:
        raise HTTPException(status_code=400, detail="No items provided")

    try:
        results = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: run_downloads(payload.items, payload.query_name)
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return results


@router.get("/files")
async def list_files():
    """Lists all downloaded files grouped by search query."""
    if not DOWNLOADS_DIR.exists():
        return {"folders": []}

    folders = []
    for folder in sorted(DOWNLOADS_DIR.iterdir()):
        if not folder.is_dir():
            continue
        files = [
            {
                "name": f.name,
                "size_kb": round(f.stat().st_size / 1024, 1),
                "download_url": f"/api/v1/files/{folder.name}/{f.name}",
            }
            for f in sorted(folder.iterdir())
            if f.is_file()
        ]
        if files:
            folders.append({"folder": folder.name, "files": files})

    return {"folders": folders}


@router.get("/files/{folder}/{filename}")
async def download_file(folder: str, filename: str):
    """Serves a specific downloaded file."""
    # Sanitize to prevent path traversal attacks
    safe_folder = Path(folder).name
    safe_filename = Path(filename).name
    filepath = DOWNLOADS_DIR / safe_folder / safe_filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(
        path=filepath,
        filename=safe_filename,
        media_type="application/octet-stream",
    )


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


@router.delete("/cache")
async def clear_cache():
    """Delete all saved result JSON files."""
    results_dir = Path(os.getenv("RESULTS_DIR", "results"))
    if not results_dir.exists():
        return JSONResponse({"message": "Cache already empty", "deleted": 0})

    deleted = 0
    for f in results_dir.glob("*.json"):
        f.unlink()
        deleted += 1

    return JSONResponse({"message": f"Cleared {deleted} cached result(s)", "deleted": deleted})

@router.delete("/cache/{filename}")
async def clear_single_cache(filename: str):
    """Delete a single cached result by filename."""
    results_dir = Path(os.getenv("RESULTS_DIR", "results"))
    filepath = results_dir / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Cache file not found")

    filepath.unlink()
    return JSONResponse({"message": f"Deleted {filename}"})


@router.get("/debug/images")
async def debug_images(name: str):
    import asyncio
    import base64
    from playwright.sync_api import sync_playwright
    from urllib.parse import urlencode
    from fastapi.responses import HTMLResponse

    def run():
        params = {"q": name, "tbm": "isch", "hl": "en"}
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
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(3000)

            screenshot = page.screenshot(full_page=False)
            screenshot_b64 = base64.b64encode(screenshot).decode()

            # Count useful selectors
            counts = page.evaluate("""() => ({
                imgs: document.querySelectorAll('img').length,
                encryptedImgs: document.querySelectorAll('img[src*="encrypted-tbn"]').length,
                dataSrc: document.querySelectorAll('img[data-src]').length,
                scripts: document.querySelectorAll('script').length,
                hasAF: document.body.innerHTML.includes('AF_initDataCallback'),
            })""")

            browser.close()
            return screenshot_b64, counts

    screenshot_b64, counts = await asyncio.get_event_loop().run_in_executor(None, run)

    return HTMLResponse(f"""
        <h2>Selector counts: {counts}</h2>
        <img src="data:image/png;base64,{screenshot_b64}" style="max-width:100%">
    """)



@router.get("/debug/files")
async def debug_files():
    import os
    downloads = Path(os.getenv("DOWNLOADS_DIR", "downloads"))
    result = {
        "downloads_dir": str(downloads),
        "exists": downloads.exists(),
        "cwd": os.getcwd(),
        "contents": [],
    }
    if downloads.exists():
        for root, dirs, files in os.walk(downloads):
            for f in files:
                full = os.path.join(root, f)
                result["contents"].append({
                    "path": full,
                    "size": os.path.getsize(full),
                })
    return result