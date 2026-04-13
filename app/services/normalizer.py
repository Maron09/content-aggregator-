import re
import logging
from app.models.schemas import ArticleResult, VideoResult, ImageResult, SearchResponse


logger = logging.getLogger(__name__)

SOURCE_NAMES = {
    "wikipedia.org": "Wikipedia",
    "youtube.com": "YouTube",
    "spotify.com": "Spotify",
    "billboard.com": "Billboard",
    "rollingstone.com": "Rolling Stone",
    "pitchfork.com": "Pitchfork",
    "genius.com": "Genius",
    "bbc.com": "BBC",
    "bbc.co.uk": "BBC",
    "theguardian.com": "The Guardian",
    "nytimes.com": "New York Times",
    "allmusic.com": "AllMusic",
    "discogs.com": "Discogs",
    "imdb.com": "IMDb",
    "pulse.ng": "Pulse Nigeria",
    "vanguardngr.com": "Vanguard",
    "punchng.com": "Punch",
    "thecable.ng": "The Cable",
    "guardian.ng": "Guardian Nigeria",
    "premiumtimesng.com": "Premium Times",
    "notjustok.com": "NotJustOk",
    "tooxclusive.com": "TooXclusive",
    "soundcity.tv": "Soundcity",
}

# Source quality scores — higher = shown first
SOURCE_SCORES = {
    "Wikipedia": 100,
    "Billboard": 95,
    "Rolling Stone": 93,
    "Pitchfork": 90,
    "BBC": 88,
    "The Guardian": 85,
    "New York Times": 85,
    "AllMusic": 80,
    "Genius": 78,
    "Pulse Nigeria": 75,
    "Premium Times": 72,
    "Vanguard": 70,
    "Punch": 70,
    "NotJustOk": 68,
    "TooXclusive": 65,
    "Discogs": 60,
    "IMDb": 60,
    "Spotify": 40,
    "YouTube": 30,
}

def _normalize_source(domain: str) -> str:
    """Maps a domain to a clean display name."""
    domain = domain.lower().replace("wwww.", "")
    for key, name in SOURCE_NAMES.items():
        if key in domain:
            return name
    
    parts = domain.split(".")
    return parts[0].capitalize() if parts else domain



def _clean_snippet(snippet: str | None) -> str | None:
    """
    Cleans article snippets:
    - Removes embedded URLs
    - Removes breadcrumb patterns (Home › Music › Artist)
    - Strips excessive whitespace
    - Returns None if too short to be useful
    """
    
    if not snippet:
        return None
    
    snippet = re.sub(r'https?://\S+', '', snippet)

    # Remove breadcrumb patterns
    snippet = re.sub(r'\w[\w\s]*›[\w\s›]*', '', snippet)

    # Remove patterns like "wikipedia.org › wiki › Artist"
    snippet = re.sub(r'\w+\.\w+\s*›.*', '', snippet)

    # Collapse whitespace
    snippet = re.sub(r'\s+', ' ', snippet).strip()
    
    if len(snippet) < 20:
        return None
    
    return snippet


def _score_article(article: ArticleResult) -> int:
    """Returns a quality score for sorting."""
    return SOURCE_SCORES.get(article.source, 50)


def normalize_articles(articles: list[ArticleResult]) -> list[ArticleResult]:
    """Deduplicates, cleans, and sorts article results."""
    seen_urls = set()
    cleaned = []
    
    for article in articles:
        if article.url in seen_urls:
            continue
        seen_urls.add(article.url)
        
        
        if not article.title or len(article.title.strip()) < 5:
            continue
        
        normalized_source = _normalize_source(article.source)
        
        clean_snip = _clean_snippet(article.snippet)
        
        cleaned.append(ArticleResult(
            title=article.title.strip(),
            url=article.url,
            source=normalized_source,
            snippet=clean_snip,
            content_type=article.content_type,
        ))
    cleaned.sort(key=_score_article, reverse=True)
    
    logger.info(f"[Normalizer] Articles: {len(articles)} → {len(cleaned)} after normalization")
    return cleaned

def normalize_videos(videos: list[VideoResult]) -> list[VideoResult]:
    """Deduplicates video results."""
    seen_urls = set()
    cleaned = []
    
    for video in videos:
        if video.url in seen_urls:
            continue
        seen_urls.add(video.url)
        
        if not video.title or len(video.title.strip()) < 3:
            continue
        
        cleaned.append(video)
    
    logger.info(f"[Normalizer] Videos: {len(videos)} → {len(cleaned)} after normalization")
    
    return cleaned



def normalize_images(images: list[ImageResult]) -> list[ImageResult]:
    """Deduplicates and filters image results."""
    seen_urls = set()
    cleaned = []

    for image in images:
        if image.image_url in seen_urls:
            continue
        seen_urls.add(image.image_url)

        # Skip images that are too small to be useful
        if image.width and image.height:
            if image.width < 200 or image.height < 200:
                continue

        cleaned.append(image)

    logger.info(f"[Normalizer] Images: {len(images)} → {len(cleaned)} after normalization")
    return cleaned



def normalize_response(response: SearchResponse) -> SearchResponse:
    """
    Runs all normalizers and returns a cleaned SearchResponse.
    Called in SearchService after all scrapers finish.
    """
    articles = normalize_articles(response.articles)
    videos = normalize_videos(response.videos)
    images = normalize_images(response.images)

    return SearchResponse(
        query_meta=response.query_meta,
        articles=articles,
        videos=videos,
        images=images,
        total=len(articles) + len(videos) + len(images),
        saved_to=response.saved_to,
    )