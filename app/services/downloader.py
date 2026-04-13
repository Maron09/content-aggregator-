import os
import re
import logging
import requests
from pathlib import Path
from app.models.schemas import DownloadItem, ContentType
import yt_dlp


logger = logging.getLogger(__name__)


DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", "downloads"))


def _ensure_dir(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)


def _safe_filename(title: str, max_len: int = 60) -> str:
    """Strips unsafe characters from a title for use as a filename."""
    safe = re.sub(r'[^\w\s\-]', '', title)
    safe = re.sub(r'\s+', '_', safe.strip())
    return safe[:max_len] or "untitled"


def download_video(item: DownloadItem, folder: Path) -> dict:
    """
    Downloads a YouTube video using yt-dlp.
    Returns best quality mp4 up to 1080p.
    """
    
    _ensure_dir(folder)
    safe_title = _safe_filename(item.title)
    
    ydl_opts = {
        "format": "best[ext=mp4]/best[height<=1080]/best",
        "outtmpl": str(folder / f"{safe_title}.%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
    }
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(item.url, download=True)
            filename = ydl.prepare_filename(info)
            logger.info(f"[Downloader] Video saved: {filename}")
            return {"success": True, "path": filename, "title": item.title}
    except Exception as e:
        logger.error(f"[Downloader] Video download failed: {e}")
        return {"success": False, "error": str(e), "title": item.title}



def download_image(item: DownloadItem, folder: Path) -> dict:
    """
    Downloads an image via HTTP request.
    Infers extension from URL or Content-Type header.
    """
    _ensure_dir(folder)
    safe_title = _safe_filename(item.title)

    try:
        response = requests.get(item.url, timeout=15, stream=True)
        response.raise_for_status()

        # Infer extension
        content_type = response.headers.get("Content-Type", "")
        ext_map = {
            "image/jpeg": "jpg",
            "image/png": "png",
            "image/webp": "webp",
            "image/gif": "gif",
        }
        ext = ext_map.get(content_type.split(";")[0].strip(), "jpg")

        # Also try to get extension from URL
        url_ext = item.url.split("?")[0].rsplit(".", 1)
        if len(url_ext) == 2 and url_ext[1].lower() in ("jpg", "jpeg", "png", "webp", "gif"):
            ext = url_ext[1].lower()
            if ext == "jpeg":
                ext = "jpg"

        filepath = folder / f"{safe_title}.{ext}"

        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        logger.info(f"[Downloader] Image saved: {filepath}")
        return {"success": True, "path": str(filepath), "title": item.title}

    except Exception as e:
        logger.error(f"[Downloader] Image download failed: {e}")
        return {"success": False, "error": str(e), "title": item.title}


def save_article_links(items: list[DownloadItem], folder: Path, query_name: str) -> dict:
    """
    Saves article links as a plain text file.
    One article per entry with title and URL.
    """
    _ensure_dir(folder)
    safe_name = _safe_filename(query_name)
    filepath = folder / f"{safe_name}_articles.txt"

    lines = []
    for item in items:
        lines.append(f"Title: {item.title}")
        lines.append(f"URL:   {item.url}")
        lines.append("")

    with open(filepath, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"[Downloader] Articles saved: {filepath}")
    return {"success": True, "path": str(filepath), "count": len(items)}


def run_downloads(items: list[DownloadItem], query_name: str) -> dict:
    """
    Dispatches each item to the correct downloader based on content_type.
    Returns a summary of results.
    """
    folder = DOWNLOADS_DIR / _safe_filename(query_name)

    results = {"videos": [], "images": [], "articles": [], "folder": str(folder)}

    article_items = []

    for item in items:
        if item.content_type == ContentType.video:
            result = download_video(item, folder)
            results["videos"].append(result)

        elif item.content_type == ContentType.image:
            result = download_image(item, folder)
            results["images"].append(result)

        elif item.content_type == ContentType.article:
            article_items.append(item)

    # Save all articles together in one file
    if article_items:
        result = save_article_links(article_items, folder, query_name)
        results["articles"].append(result)

    total = len(items)
    success = sum(
        1 for r in results["videos"] + results["images"] + results["articles"]
        if r.get("success")
    )

    logger.info(f"[Downloader] Done: {success}/{total} succeeded, folder: {folder}")
    results["summary"] = {"total": total, "success": success, "folder": str(folder)}
    return results