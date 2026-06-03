"""Tavily web search tool used by Planning and Risk agents."""

from tenacity import retry, stop_after_attempt, wait_exponential



@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=10))
async def tavily_search(query: str, max_results: int = 5) -> list[dict]:
    """Perform a Tavily search and return the result list."""
    # TODO: use tavily.AsyncTavilyClient
    raise NotImplementedError
