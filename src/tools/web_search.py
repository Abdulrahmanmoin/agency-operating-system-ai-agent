"""Tavily web search tool used by the Risk (and later Planning) agents."""

from tenacity import retry, stop_after_attempt, wait_exponential

from config import settings


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8))
async def tavily_search(query: str, max_results: int = 5, include_answer: bool = True) -> dict:
    """Run a Tavily search. Returns {query, answer, results:[{title,url,content,score}]}.

    Raises if no API key is configured — callers that want graceful degradation should check
    `settings.tavily_api_key` first.
    """
    from tavily import AsyncTavilyClient

    client = AsyncTavilyClient(api_key=settings.tavily_api_key)
    resp = await client.search(
        query=query,
        max_results=max_results,
        search_depth="basic",
        include_answer=include_answer,
    )
    return {
        "query": query,
        "answer": resp.get("answer"),
        "results": resp.get("results", []),
    }
