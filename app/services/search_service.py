import asyncio
import logging
from app.scrapers.google_api import search_google_api
from app.services.storage import save_results, load_results
from app.models.schemas import SearchRequest, SearchResponse

logger = logging.getLogger(__name__)


class SearchService:

    async def search(
        self,
        request: SearchRequest,
        use_cache: bool = True,
    ) -> SearchResponse:

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

        # Now just a regular async call — no thread executor needed
        # because requests library is used instead of Playwright
        articles = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: search_google_api(
                name=request.name,
                city=request.city,
                year=request.year,
                month=request.month,
            )
        )

        query_meta = {
            "name": request.name,
            "city": request.city,
            "year": request.year,
            "month": request.month,
        }

        response = SearchResponse(
            query_meta=query_meta,
            articles=articles,
            total=len(articles),
        )

        saved_path = save_results(response.model_dump())
        response.saved_to = saved_path

        return response