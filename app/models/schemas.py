from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum


class ContentType(str, Enum):
    article = "article"
    video = "video"
    image = "image"


class SearchRequest(BaseModel):
    name: str = Field(..., min_length=1, description="Person or subject name")
    city: Optional[str] = Field(None, description="City context for search")
    year: Optional[int] = Field(None, ge=1900, le=2100, description="Leave empty to search all years")
    month: Optional[int] = Field(None, ge=1, le=12, description="Leave empty to search full year")
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Albert Einstein",
                "city": "Princeton",
                "year": 1921,
                "month": 11
            }
        }


class ArticleResult(BaseModel):
    title: str
    url: str
    source: str           # e.g. "Billboard", "Wikipedia"
    snippet: Optional[str] = None
    content_type: ContentType = ContentType.article

class VideoResult(BaseModel):
    title: str
    url: str
    source: str = "youtube.com"
    channel: str
    thumbnail: Optional[str] = None
    published_at: Optional[str] = None
    view_count: Optional[str] = None
    duration: Optional[str] = None  
    content_type: ContentType = ContentType.video


class ImageResult(BaseModel):
    title: str
    image_url: str
    source_url: str
    source: str
    width: Optional[int] = None
    height: Optional[int] = None
    content_type: ContentType = ContentType.image

class SearchResponse(BaseModel):
    query_meta: dict      # stores the original input for traceability
    articles: list[ArticleResult]
    videos: list[VideoResult] = []
    images: list[ImageResult] = []
    total: int
    saved_to: Optional[str] = None


class DownloadItem(BaseModel):
    url: str
    content_type: ContentType
    title: str = "untitled"


class DownloadRequest(BaseModel):
    items: list[DownloadItem]
    query_name: str = "download"