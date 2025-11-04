import aiohttp
import html2text
from ddgs import DDGS
from loguru import logger
from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.services.llm_service import FunctionCallParams

web_search_schema = FunctionSchema(
    name="web_search",
    description="Fetch relevant information from the web via search",
    properties={
        "query": {
            "type": "string",
            "description": "The search query to look up on the web",
        },
    },
    required=["query"],
)


async def web_search(params: FunctionCallParams):
    query = params.arguments.get("query", "")
    results = DDGS().text(query, max_results=3)
    logger.debug(f"Web search for query '{query}' returned results:")
    logger.debug(results)
    await params.result_callback({"results": results})


web_fetch_schema = FunctionSchema(
    name="web_fetch",
    description="Fetch and extract the main content from a web page",
    properties={
        "url": {
            "type": "string",
            "description": "The URL of the web page to fetch",
        },
    },
    required=["url"],
)


async def web_fetch(params: FunctionCallParams):
    url = params.arguments.get("url", "")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                html = await response.text()

                h = html2text.HTML2Text()
                h.ignore_links = False
                h.ignore_images = True
                text = h.handle(html)

                result = {"url": url, "content": text, "status": "success"}
    except Exception as e:
        result = {"url": url, "error": str(e), "status": "error"}
    await params.result_callback({"result": result})
