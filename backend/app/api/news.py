"""Real-time news feed endpoint."""
from typing import Optional

from fastapi import APIRouter, Query

from ..news.feed import news_feed

router = APIRouter()


@router.get("/news")
async def get_news(limit: int = Query(20, ge=1, le=100), type: Optional[str] = None):
    items = news_feed.items(limit=100)
    if type:
        items = [i for i in items if i.get("type") == type.upper()]
    return {"count": len(items), "news": items[:limit]}


@router.get("/news/summary")
async def news_summary():
    items = news_feed.items(50)
    return {
        "count": len(items),
        "latest": items[0] if items else None,
        "by_type": {t: sum(1 for i in items if i.get("type") == t) for t in sorted({i.get("type") for i in items})},
    }