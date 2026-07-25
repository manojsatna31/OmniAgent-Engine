# tools.py – all the tools the LinkedIn Content Agent uses

# Import the DuckDuckGo search wrapper from LangChain so the agent can search the web.
from langchain_community.tools import DuckDuckGoSearchRun,DuckDuckGoSearchResults

# Import the LangChain Tool class so Python functions can be exposed to the LLM as callable tools.
from langchain_core.tools import Tool

# Import requests so the script can fetch article content from a remote reader service.
import requests

# Import os so the script can create folders and files on the local filesystem.
import os

# Import date and datetime so draft files can be saved into date-based folders with timestamps.
from datetime import date
from datetime import datetime
import trafilatura
from ddgs import DDGS

from pathlib import Path

from concurrent.futures import ThreadPoolExecutor, as_completed
from config import SEARCH_MAX_RESULTS
from logger import setup_logger
# Use a tools-specific logger and file so tool activity is separated from
# the main agent runtime logs. This makes it easier to trace I/O and
# extraction issues originating in the helper functions.
logger = setup_logger("PublishAI")

# Centralized configuration: how many characters of an extracted article
# to return to the LLM/UI. Keeping this as a named constant makes it easy
# to tune for different LLM input limits or UX preferences.
from config import ARTICLE_TRUNCATE_LIMIT

# ---------------------------------------------------------------------
# 1. Robust WebSearch – uses DDGS for structured results with URLs
# ---------------------------------------------------------------------
def structured_search(query: str, max_results: int = None) -> str:
    """
    Search DuckDuckGo and return formatted results with Title, URL, and Snippet.
    Uses the official duckduckgo_search library for reliable URL extraction.
    """
    logger.info("Searching: %s", query)
    if max_results is None:
        max_results = SEARCH_MAX_RESULTS
    try:
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=max_results))
        if not results:
            return f"No search results found for '{query}'."
        formatted = []
        for r in results:
            title = r.get("title", "No title")
            url = r.get("href", "No URL")          # 'href' is the full URL
            snippet = r.get("body", "No snippet")  # 'body' is the snippet
            formatted.append(f"**Title:** {title}\n**URL:** {url}\n**Snippet:** {snippet}\n")
        final_result = "\n\n".join(formatted)
        logger.info("Search results: %s", final_result)
        return final_result
    except Exception as e:
        # Last resort fallback – but the LLM won't get URLs
        logger.error("Structured search failed: %s", str(e))
        return f"Structured search failed: {str(e)}. Please try a simpler query."


def read_articles_batch(urls: str) -> str:
    """
    Read multiple articles concurrently. Input: a JSON list of URLs.
    Example: ["https://...", "https://..."]
    """
    import json
    logger.info("Reading articles from URLs: %s", urls)
    try:
        url_list = json.loads(urls)
    except Exception:
        return "Error: Input must be a JSON list of URLs."
    
    results = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(read_article, url): url for url in url_list}
        for future in as_completed(futures):
            url = futures[future]
            try:
                content = future.result()
                results.append(f"=== Article from {url} ===\n{content}")
            except Exception as e:
                results.append(f"=== Failed: {url} — {str(e)} ===")
                logger.error("Error reading article from %s: %s", url, str(e))
    final_result = "\n\n".join(results)
    logger.info("Batch read results: %s", final_result)
    return final_result


# ---------------------------------------------------------------------
# 2. ReadArticle – Jina first, then direct fetch + trafilatura
# ---------------------------------------------------------------------
def read_article(url: str) -> str:
    """Fetch and extract text from a web article. Tries Jina first, then direct download."""
    logger.info("Reading article: %s", url)
    if not url.startswith("http"):
        return "Error: URL must start with http or https."

    # --- Try 1: Jina AI (fast, clean markdown) ---
    try:
        reader_url = f"https://r.jina.ai/{url}"
        logger.info("Fetching article from Jina: %s", reader_url)
        resp = requests.get(reader_url, timeout=20)  # more generous
        if resp.status_code == 200:
            text = resp.text
            logger.info("Article content fetched from Jina: %s", len(text))
            # If Jina returns an error page, skip it
            if "Error" in text and len(text) < 200:
                logger.info("Jina returned an error page for: %s", url)
                pass  # fall through to next method
            else:
                return text[:ARTICLE_TRUNCATE_LIMIT] + ("..." if len(text) > ARTICLE_TRUNCATE_LIMIT else "")
    except Exception as e:
        logger.exception("Jina fetch failed for %s: %s", url, str(e))
        pass  # Jina failed, try direct

    # --- Try 2: Direct fetch + trafilatura (bypasses blocks) ---
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        logger.info("Fetching article directly from: %s", url)
        direct_resp = requests.get(url, headers=headers, timeout=20)
        if direct_resp.status_code == 200:
            logger.info("Article fetched directly: %s", url)
            # Use trafilatura to extract the main readable content from the fetched HTML.
            #
            # Why we use trafilatura here:
            # - It is purpose-built to isolate an article's main body (removing
            #   navigation, sidebars, ads and other boilerplate), producing a
            #   cleaner text result that's more suitable for LLM consumption.
            # - output_format="markdown" preserves headings and basic
            #   structure so the resulting text remains readable in the UI and
            #   easier for the LLM to interpret. We deliberately set
            #   include_links=False to avoid injecting large lists of links or
            #   noisy anchor text into the prompt; URLs are already surfaced
            #   by the search tool when needed.
            #
            # Important edge-cases and rationale for truncation:
            # - trafilatura may return None when it cannot detect main content
            #   (e.g., heavily JS-driven pages, paywalled content, or non-HTML
            #   responses). We check for that below and return a helpful
            #   message instead of crashing.
            # - We truncate the extracted text to 4000 characters before
            #   returning because:
            #     * Large payloads from long articles can exceed LLM input
            #       size limits or cause excessive latency.
            #     * Truncation keeps the agent's messages predictable in
            #       length while still providing the LLM with the article's
            #       leading content (which usually contains the most context).
            #   If you prefer the full article, consider increasing the limit
            #   or streaming the content in chunks.
            extracted = trafilatura.extract(direct_resp.text, output_format="markdown", include_links=False)
            logger.info("Extracted content from %s: %s", url, extracted[:100] + "..." if extracted and len(extracted) > 100 else extracted)
            if extracted:
                return extracted[:ARTICLE_TRUNCATE_LIMIT] + ("..." if len(extracted) > ARTICLE_TRUNCATE_LIMIT else "")
            else:
                return f"Article fetched but content extraction failed. URL may not contain readable text."
        else:
            return f"Error: HTTP {direct_resp.status_code} when fetching article. The URL may be broken or blocked."
    except Exception as e:
        logger.exception("Direct fetch failed for %s: %s", url, str(e))
        return f"All methods failed to read article: {str(e)}"

# ---------------------------------------------------------------------
# 3. SaveDraft
# ---------------------------------------------------------------------
def save_draft(content: str, filename: str = None) -> str:
#     logger.info("Saving draft: %s", filename)
    if not filename:
        timestamp = datetime.now().strftime("%H%M%S")
        filename = ensure_md_extension(f"draft_{timestamp}")
    else:
        filename = ensure_md_extension(filename)
    today_str = date.today().strftime("%Y-%m-%d")
    folder_path = os.path.join("drafts", today_str)
    os.makedirs(folder_path, exist_ok=True)
    filepath = os.path.join(folder_path, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    logger.info("Draft saved at: %s", filepath)
    return f"Draft saved successfully: {filepath}"

# ---------------------------------------------------------------------
# 4. Wrap as LangChain tools
# ---------------------------------------------------------------------
tools = [
    Tool(
        name="WebSearch",
        func=structured_search,
        description="Search the web for recent articles. Returns titles, URLs, and snippets."
    ),
    Tool(
        name="ReadArticle",
        func=read_article,
        description="Get the full text of a web article from its URL. Input: a URL starting with http."
    ),
    Tool(
        name="SaveDraft",
        func=save_draft,
        description="Save the final content. (Note: The draft is saved automatically – do not call this tool.)"
    ),
]

# ---------------------------------------------------------------------
# 5. Utility function to ensure .md extension
# ---------------------------------------------------------------------
def ensure_md_extension(filename: str) -> str:
    """Always force the file to have a .md extension."""
    return os.path.splitext(filename)[0] + ".md"