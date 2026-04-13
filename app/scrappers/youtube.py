import calendar
import logging
import yt_dlp
from app.models.schemas import VideoResult

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


def _format_views(count) -> str | None:
    if not count:
        return None
    n = int(count)
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M views"
    if n >= 1_000:
        return f"{n / 1_000:.0f}K views"
    return f"{n} views"


def _format_duration(seconds) -> str | None:
    if not seconds:
        return None
    seconds = int(seconds)  # handles both int and float
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def search_youtube(
    name: str,
    city: str | None,
    year: int | None,
    month: int | None,
    max_results: int = 10,
) -> list[VideoResult]:
    """
    Uses yt-dlp to search YouTube directly.
    No API key needed, no quota limits.
    """
    query = _build_query(name, city, year, month)
    logger.info(f"[YouTube] yt-dlp query: {query!r}")

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": True,       # don't download, just get metadata
        "playlist_items": f"1-{max_results}",
    }

    results = []

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            search_url = f"ytsearch{max_results}:{query}"
            info = ydl.extract_info(search_url, download=False)

            entries = info.get("entries", [])
            logger.info(f"[YouTube] Got {len(entries)} entries")

            for entry in entries:
                if not entry:
                    continue

                video_id = entry.get("id", "")
                if not video_id:
                    continue

                results.append(VideoResult(
                    title=entry.get("title", "Untitled"),
                    url=f"https://www.youtube.com/watch?v={video_id}",
                    source="youtube.com",                    # ← add this line
                    channel=entry.get("channel") or entry.get("uploader") or "Unknown",
                    thumbnail=entry.get("thumbnail") or f"https://img.youtube.com/vi/{video_id}/mqdefault.jpg",
                    published_at=str(entry.get("upload_date", ""))[:10] or None,
                    view_count=_format_views(entry.get("view_count")),
                    duration=_format_duration(entry.get("duration")),
                ))

    except Exception as e:
        logger.error(f"[YouTube] yt-dlp error: {e}")
        return []

    logger.info(f"[YouTube] Found {len(results)} videos")
    return results