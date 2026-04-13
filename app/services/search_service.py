import logging
from app.scrappers.google import scrape_google_articles
from app.scrappers.youtube import search_youtube
from app.scrappers.images import scrape_google_images
from app.services.storage import save_results, load_results
from app.models.schemas import SearchRequest, SearchResponse
from app.services.normalizer import normalize_response
import asyncio


logger = logging.getLogger(__name__)


class SearchService:
    """
    Orchestrates all scrapers and normalises their output
    into a unified SearchResponse.

    In future phases this class will also call:
        - YouTubeSearcher (Phase 2)
        - ImageSearcher (Phase 3)
    """
    async def search(
        self,
        request: SearchRequest,
        use_cache: bool = True,
    ) -> SearchResponse:

        # --- Cache check ---
        if use_cache:
            cached = load_results(request.name, request.year, request.month)
            if cached:
                logger.info("[SearchService] Returning cached result")
                return SearchResponse(**{
                    k: cached[k]
                    for k in SearchResponse.model_fields
                    if k in cached
                })

        logger.info(f"[SearchService] Searching for {request.name!r}")
        
        loop = asyncio.get_event_loop()

        # Run both scrapers concurrently in thread pool
        articles_task = loop.run_in_executor(
            None,
            lambda: scrape_google_articles(
                name=request.name,
                city=request.city,
                year=request.year,
                month=request.month,
            )
        )

        videos_task = loop.run_in_executor(
            None,
            lambda: search_youtube(
                name=request.name,
                city=request.city,
                year=request.year,
                month=request.month,
            )
        )
        
        image_task = loop.run_in_executor(
            None,
            lambda: scrape_google_images(
                name=request.name,
                city=request.city,
                year=request.year,
                month=request.month,
            )
        )

        # Run the blocking Playwright call in a thread pool
        # so FastAPI's async event loop stays unblocked
        articles, videos, images = await asyncio.gather(articles_task, videos_task, image_task)

        query_meta = {
            "name": request.name,
            "city": request.city,
            "year": request.year,
            "month": request.month,
        }

        response = SearchResponse(
            query_meta=query_meta,
            articles=articles,
            videos=videos,
            images=images,
            total=len(articles) + len(videos),
        )

        response = normalize_response(response)
        saved_path = save_results(response.model_dump())
        response.saved_to = saved_path

        return response