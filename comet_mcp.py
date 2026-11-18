"""
Comet Browser MCP Server
========================
An MCP server that lets Claude Desktop control the Comet browser (Perplexity's
AI browser) via Chrome DevTools Protocol. Claude can type searches, navigate
pages, read content, take screenshots, and interact with web elements.

Usage:
  1. Start Comet yourself with remote debugging (the server never starts or
     closes Comet):
     comet.exe --remote-debugging-port=9222
  2. Start this MCP server (configured in Claude Desktop's config)
  3. Claude can now control your Comet browser!
"""

import asyncio
import json
import os
import re
import time
from typing import Optional
from urllib.parse import quote, urlparse

import sys

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from playwright.async_api import async_playwright, Browser, Page

from content_filter import ContentFilter

_filter = ContentFilter()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_CDP_PORT = 9222
# A trailing slash would make URLs built from CDP_URL contain "//", which DevTools does not serve.
CDP_URL = os.environ.get("COMET_CDP_URL", f"http://localhost:{DEFAULT_CDP_PORT}").rstrip("/")


def _port_of(url: str) -> int:
    """Port named in a CDP URL, or the default when the URL has none."""
    return urlparse(url).port or DEFAULT_CDP_PORT


CDP_PORT = _port_of(CDP_URL)
# Shown when the connect fails. The server never starts Comet: a Comet it started
# could close with the server, because MCP clients end the server's whole process tree.
# PowerShell form, the same as every Windows instruction in the docs.
START_COMMAND_WINDOWS = rf'& "$env:LOCALAPPDATA\Perplexity\Comet\Application\comet.exe" --remote-debugging-port={CDP_PORT}'
START_COMMAND_MACOS = f"/Applications/Comet.app/Contents/MacOS/Comet --remote-debugging-port={CDP_PORT}"
START_COMMAND_OTHER = f"comet --remote-debugging-port={CDP_PORT}"
START_COMMAND = {"win32": START_COMMAND_WINDOWS, "darwin": START_COMMAND_MACOS}.get(sys.platform, START_COMMAND_OTHER)
DEFAULT_TIMEOUT = int(os.environ.get("COMET_TIMEOUT", "30000"))  # ms
MAX_CONTENT_LENGTH = int(os.environ.get("COMET_MAX_CONTENT", "50000"))  # chars
MAX_WAIT_SECONDS = 120  # hard cap for any sleep/wait parameter
VALID_SEARCH_MODES = ("search", "research")
VALID_WAIT_FOR = ("load", "domcontentloaded", "networkidle")
VALID_TAB_ACTIONS = ("list", "new", "switch", "close")
VALID_FINANCE_MODES = ("market", "quote", "screener", "earnings", "predictions")
FINANCE_BASE_URL = "https://www.perplexity.ai/finance"
MAX_TICKER_CHARS = 20
MAX_SCREENER_QUERY_CHARS = 500  # about 15 s of typing at 30 ms a key


def _clamp_wait(value: int, default: int = 10) -> int:
    """Clamp a wait/sleep value to [0, MAX_WAIT_SECONDS]."""
    if not isinstance(value, (int, float)):
        return default
    return max(0, min(int(value), MAX_WAIT_SECONDS))

# ---------------------------------------------------------------------------
# Global state
# ---------------------------------------------------------------------------
_playwright = None
_browser: Optional[Browser] = None
_page: Optional[Page] = None
_search_tabs: list[dict] = []  # [{query, page, url}]
MAX_SEARCH_TABS = 5

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------
mcp = MCPServer("comet_mcp")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
async def _ensure_browser() -> Browser:
    """Connect to Comet via CDP. Never starts Comet; on failure the error says how the user starts it."""
    global _playwright, _browser, _page
    if _browser and _browser.is_connected():
        return _browser

    # Clean up stale state
    if _playwright:
        try:
            await _playwright.stop()
        except Exception:
            pass
        _playwright = None
    _browser = None
    _page = None

    _playwright = await async_playwright().start()

    try:
        # It attaches to the user's own browser, so Playwright must not change its default context.
        _browser = await _playwright.chromium.connect_over_cdp(CDP_URL, no_defaults=True)
        return _browser
    except Exception as error:
        # First line only: Playwright errors carry a long call log after it.
        connect_error = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__

    raise ConnectionError(
        f"Could not connect to Comet at {CDP_URL} ({connect_error}). "
        f"Start Comet with remote debugging: {START_COMMAND}. "
        "If Comet is already open, quit it fully first. On a managed machine the "
        "RemoteDebuggingAllowed policy can block remote debugging."
    )


async def _get_page() -> Page:
    """Get the active page, or the first available one."""
    global _page
    browser = await _ensure_browser()
    contexts = browser.contexts
    if not contexts:
        raise RuntimeError("No browser contexts found. Is Comet open?")
    pages = contexts[0].pages
    if _page and _page in pages and not _page.is_closed():
        return _page
    if pages:
        _page = pages[-1]
        return _page
    _page = await contexts[0].new_page()
    return _page


def _valid_tab_index(tab_index: Optional[int], pages: list) -> bool:
    """Check if tab_index is a valid index into pages."""
    return tab_index is not None and 0 <= tab_index < len(pages)


def _handle_error(e: Exception, context: str = "") -> ToolError:
    """Turn a caught exception into a ToolError; call sites `raise _handle_error(e) from e`.

    MCP 2.x drops the message of a plain exception, so every failure must leave a tool as a ToolError.
    """
    if isinstance(e, ToolError):
        return e  # raised by our own validation inside the try block: keep its message as written
    error_type = type(e).__name__
    if "closed" in str(e).lower():
        return ToolError("Browser connection lost. Use comet_connect to reconnect.")
    if "Timeout" in str(e):
        return ToolError(f"{context} timed out. {e}" if context else f"Timed out. {e}")
    return ToolError(f"{error_type}: {e}")


def _sanitize_and_return(text: str, url: str) -> str:
    """Run content filter and log injections. Returns sanitized text."""
    scan = _filter.sanitize(text, url)
    if scan.injection_detected:
        print(f"⚠️ INJECTION on {url}: {len(scan.threats)} patterns", file=sys.stderr)
    return scan.text


def _safe_title(title: str) -> str:
    """Clean a page title, or withhold it when it matches an injection pattern.

    Titles are page-controlled, but wrapping a whole tool result in the filter would add a header
    and scan the screenshot's base64, so only the title goes through it.
    """
    cleaned, _ = _filter.strip_hidden_content(title)
    # Scan the stripped and the raw text, as comet_security_scan does.
    threats = _filter.detect_injections(cleaned) or _filter.detect_injections(title)
    if threats:
        print(f"⚠️ INJECTION in page title: {len(threats)} patterns", file=sys.stderr)
        return f"[title withheld: {len(threats)} injection pattern(s); run comet_security_scan]"
    return cleaned


_JS_EXTRACT_TEMPLATE = """
(root) => {
    const node = root || document.body;
    const blocks = [];
    const walk = (el) => {
        if (!el) return;
        const tag = el.tagName ? el.tagName.toLowerCase() : '';
        const skip = ['script', 'style', 'noscript', 'svg', 'path', 'nav', 'aside', 'header', 'footer'];
        if (skip.includes(tag)) return;
        if (tag === 'details' && !el.open && !INCLUDE_COLLAPSED) {
            // A collapsed section shows only its summary line, so read just that.
            const summary = el.querySelector(':scope > summary');
            if (summary) walk(summary);
            return;
        }
        if (el.nodeType === Node.TEXT_NODE) {
            const t = el.textContent.trim();
            if (t) blocks.push(t);
            return;
        }
        if (tag === 'a' && el.href && INCLUDE_LINKS) {
            const text = el.textContent.trim();
            if (text) {
                blocks.push(`[${text}](${el.href})`);
                return;
            }
        }
        for (const child of el.childNodes) walk(child);
        const blockTags = ['div', 'p', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
                         'li', 'tr', 'br', 'hr', 'section', 'article'];
        if (blockTags.includes(tag)) blocks.push('\\n');
    };
    walk(node);
    return blocks.join(' ').replace(/\\n\\s*\\n/g, '\\n\\n').trim();
}
"""


async def _extract_text(
    page: Page,
    selector: Optional[str] = None,
    include_links: bool = True,
    max_length: int = MAX_CONTENT_LENGTH,
    include_collapsed: bool = False,
) -> str:
    """Extract readable text content from the page or a specific element.

    include_collapsed reads closed <details> in full; the security scan needs that, reading tools don't.
    """
    js_code = (_JS_EXTRACT_TEMPLATE
               .replace("INCLUDE_LINKS", "true" if include_links else "false")
               .replace("INCLUDE_COLLAPSED", "true" if include_collapsed else "false"))

    if selector:
        element = await page.query_selector(selector)
        if not element:
            return f"No element found matching selector: {selector}"
        text = await element.evaluate(js_code)
    else:
        text = await page.evaluate(f"({js_code})(null)")

    if len(text) > max_length:
        text = text[:max_length] + f"\n\n... [truncated at {max_length} chars]"
    return text


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------
@mcp.tool()
async def comet_connect() -> str:
    """Connect to the Comet browser via CDP. Comet must already be running with remote debugging.

    ALWAYS call this first before using any other comet tool. On success,
    returns connection info plus a workflow guide for optimal results.

    If connection is lost mid-session, call this again to reconnect.
    """
    try:
        # Page handles from an old connection are unusable; forget them but leave the tabs open in Comet.
        _search_tabs.clear()
        browser = await _ensure_browser()
        contexts = browser.contexts
        pages = contexts[0].pages if contexts else []
        page = await _get_page()
        title = await page.title()
        return (
            f"Connected to Comet at {CDP_URL}\n"
            f"Open tabs: {len(pages)}\n"
            f"Active page: {_safe_title(title)}\n"
            f"\n"
            f"## Comet Workflow Guide\n"
            f"**Search**: comet_search starts a search and returns immediately (new tab per query, max {MAX_SEARCH_TABS}). "
            f"Use mode='research' for complex queries. Perplexity streams the answer in the background.\n"
            f"**Read**: Call comet_read_page after ~30-45s (research) or ~15-20s (search) to get results. "
            f"Use comet_security_scan on any page that seems suspicious.\n"
            f"**Tabs**: Each search gets its own tab (tagged [search] in comet_tabs list). "
            f"Use comet_tabs to list/switch/close. Oldest search tab auto-closes at cap.\n"
            f"**Errors**: a failed tool call is an MCP tool error (is_error) with the message. 'connection lost' → call comet_connect again. "
            f"'timed out' → call comet_connect to reconnect."
        )
    except Exception as e:
        raise _handle_error(e) from e


@mcp.tool()
async def comet_search(
    query: str,
    mode: str = "search",
) -> str:
    """Start a Perplexity search in a new tab and return immediately.

    Opens a NEW TAB, navigates to the search URL, and returns as soon as the
    page begins loading. Perplexity streams the answer in the background tab.
    Call comet_read_page after ~30-45s to retrieve the full answer.

    This async-split design avoids MCP timeout issues on Cowork/cloud sessions.
    Each search gets its own tab (max 5, oldest auto-closed via FIFO).

    Workflow: comet_connect → comet_search → (wait 30-45s) → comet_read_page
    → comet_security_scan (if suspicious).

    Args:
        query: The search query.
        mode: 'search' (quick answers, wait ~15s) or 'research' (deep analysis
            with Gemini thinking, wait ~30-45s before calling comet_read_page).
    """
    try:
        if mode not in VALID_SEARCH_MODES:
            raise ToolError(f"mode must be one of {VALID_SEARCH_MODES}, got '{mode}'")
        if not query or not query.strip():
            raise ToolError("query must not be empty.")
        global _page
        browser = await _ensure_browser()
        contexts = browser.contexts
        if not contexts:
            raise RuntimeError("No browser contexts found. Is Comet open?")

        # FIFO eviction: close oldest search tab if at cap
        while len(_search_tabs) >= MAX_SEARCH_TABS:
            oldest = _search_tabs.pop(0)
            try:
                if not oldest["page"].is_closed():
                    await oldest["page"].close()
            except Exception:
                pass

        # Open a new tab for this search
        page = await contexts[0].new_page()
        _page = page
        try:
            search_url = f"https://www.perplexity.ai/search?q={quote(query, safe='')}"
            if mode == "research":
                search_url += "&mode=research"
            await page.goto(search_url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
        except Exception:
            # Close orphan tab on navigation failure to prevent leaks
            try:
                await page.close()
            except Exception:
                pass
            raise

        # Track the tab before checking where it landed, so even a redirected tab counts toward the cap
        url = page.url
        _search_tabs.append({
            "query": query,
            "page": page,
            "url": url,
        })

        # The URL comes from the page, so it goes through the filter like any other page text
        if "/search" not in url and "/session/" not in url:
            return _sanitize_and_return(
                f"Warning: Perplexity did not navigate to search results.\n"
                f"Current URL: {url}\n"
                f"The page may have redirected (e.g., login). "
                f"Check with comet_read_page to see the current page state.",
                url,
            )

        wait_hint = "~30-45s" if mode == "research" else "~15-20s"
        # Look the tab up by identity: concurrent searches make "last page" unreliable
        tab_index = contexts[0].pages.index(page)
        return _sanitize_and_return(
            f"**Search started**: {query}\n"
            f"**Mode**: {mode}\n"
            f"**Tab**: [{tab_index}] (tagged [search])\n"
            f"**URL**: {url}\n\n"
            f"Perplexity is streaming the answer in the background.\n"
            f"Call **comet_read_page** in {wait_hint} to retrieve the full results.",
            url,
        )
    except Exception as e:
        raise _handle_error(e, "Search") from e


@mcp.tool()
async def comet_search_finance(
    mode: str = "market",
    ticker: Optional[str] = None,
    query: Optional[str] = None,
) -> str:
    """Search Perplexity Finance for market data, stock quotes, or screener results.

    Navigates the active tab to the appropriate Perplexity Finance page and
    returns immediately. Call comet_read_page(selector="main") after ~3-5s to
    retrieve the full data. Screener mode returns after typing the query.

    Modes:
    - "market": Dashboard — indices, sectors, movers, crypto, AI market summary
    - "quote": Stock/ETF/crypto detail — price, P/E, EPS, 52W range, AI analysis
    - "screener": Natural-language stock screener — type a query, get matches.
      The screener runs on Perplexity's Computer feature.
    - "earnings": Earnings calendar for the current week
    - "predictions": Prediction markets (Polymarket) — rates, oil, elections

    Args:
        mode: One of 'market', 'quote', 'screener', 'earnings', 'predictions'.
        ticker: Ticker symbol for 'quote' mode (e.g., 'NVDA', 'BTCUSD', 'XLK').
        query: Natural language query for 'screener' mode
            (e.g., 'semiconductor stocks with revenue growth > 20%').
    """
    try:
        if mode not in VALID_FINANCE_MODES:
            raise ToolError(f"mode must be one of {VALID_FINANCE_MODES}, got '{mode}'")

        if mode == "quote":
            if not ticker or not ticker.strip():
                raise ToolError("ticker is required for 'quote' mode (e.g., ticker='NVDA').")
            ticker = ticker.strip().upper()
            # Letters, digits, dots, hyphens and carets (^VIX), with at least one letter or digit:
            # a ticker of only dots would resolve /finance/.. to the Perplexity home page.
            if (not re.fullmatch(r"[A-Z0-9.\-^]+", ticker) or not any(ch.isalnum() for ch in ticker)
                    or len(ticker) > MAX_TICKER_CHARS):
                raise ToolError(f"invalid ticker '{ticker}'. Use a symbol such as 'NVDA', 'BTCUSD' or '^VIX'.")

        if mode == "screener":
            if not query or not query.strip():
                raise ToolError("query is required for 'screener' mode.")
            # The query is typed key by key (30 ms each), so a long one would block the tool for minutes.
            if len(query.strip()) > MAX_SCREENER_QUERY_CHARS:
                raise ToolError(f"screener query is longer than {MAX_SCREENER_QUERY_CHARS} characters.")

        page = await _get_page()

        # Build the target URL
        if mode == "market":
            url = FINANCE_BASE_URL
        elif mode == "quote":
            url = f"{FINANCE_BASE_URL}/{ticker}"
        elif mode == "screener":
            url = f"{FINANCE_BASE_URL}/screener"
        elif mode == "earnings":
            url = f"{FINANCE_BASE_URL}/earnings"
        elif mode == "predictions":
            url = f"{FINANCE_BASE_URL}/predictions"

        await page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)

        # For screener mode, type the query into the search input and submit.
        # The screener uses a contenteditable div (role="textbox"), NOT a regular input.
        # We use JS to find+focus it, then keyboard.type to enter the query.
        if mode == "screener":
            await asyncio.sleep(2)  # Wait for React hydration
            typed_ok = False
            # No try/except here: a lost connection must reach _handle_error, not read as "input not found".
            # Use JS to find the textbox, focus it, and clear it
            found = await page.evaluate("""() => {
                    const el = document.querySelector('[role="textbox"]')
                        || document.querySelector('[contenteditable="true"]')
                        || document.querySelector('textarea')
                        || document.querySelector('input[type="text"]');
                    if (el) {
                        el.focus();
                        if (el.contentEditable === 'true') {
                            el.textContent = '';
                        } else {
                            el.value = '';
                        }
                        return true;
                    }
                    return false;
                }""")
            if found:
                await asyncio.sleep(0.3)
                await page.keyboard.type(query.strip(), delay=30)
                await asyncio.sleep(0.3)
                await page.keyboard.press("Enter")
                typed_ok = True

            if not typed_ok:
                return (
                    f"**Finance screener opened**: {url}\n\n"
                    f"Could not auto-type the query. The screener input was not found.\n"
                    f"Use **comet_type** to enter the query manually, then "
                    f"**comet_read_page(selector=\"main\")** for results."
                )

        title = await page.title()
        final_url = page.url

        # Wait hints per mode
        wait_hints = {
            "market": "~3-5s",
            "quote": "~3-5s",
            "screener": "~10-20s",
            "earnings": "~3-5s",
            "predictions": "~3-5s",
        }

        # Human-readable mode descriptions (conditional to avoid None.strip())
        if mode == "quote":
            label = f"Quote: {ticker} (price, fundamentals, AI daily analysis)"
        elif mode == "screener":
            label = f"Screener: \"{query.strip()}\""
        elif mode == "earnings":
            label = "Earnings calendar"
        elif mode == "predictions":
            label = "Prediction markets (Polymarket)"
        else:
            label = "Market dashboard (indices, sectors, movers, crypto, AI news, fixed income)"

        # The page title is page-controlled text, so the result goes through the filter
        return _sanitize_and_return(
            f"**Finance ({mode})**: {label}\n"
            f"**URL**: {final_url}\n"
            f"**Title**: {title}\n\n"
            f"Dynamic data is loading in the background.\n"
            f"Call **comet_read_page(selector=\"main\")** in {wait_hints[mode]} to retrieve the data.",
            final_url,
        )
    except Exception as e:
        raise _handle_error(e, f"Finance ({mode})") from e


@mcp.tool()
async def comet_navigate(
    url: str,
    wait_for: str = "domcontentloaded",
) -> str:
    """Navigate Comet to a specific URL in the active tab.

    Use this to visit specific pages (docs, APIs, articles). For web searches,
    prefer comet_search instead. Content is auto-sanitized for injection detection.

    Args:
        url: The URL to navigate to.
        wait_for: Wait condition -- 'load', 'domcontentloaded', or 'networkidle'.
    """
    try:
        if wait_for not in VALID_WAIT_FOR:
            raise ToolError(f"wait_for must be one of {VALID_WAIT_FOR}, got '{wait_for}'")
        page = await _get_page()
        await page.goto(url, wait_until=wait_for, timeout=DEFAULT_TIMEOUT)
        title = await page.title()
        final_url = page.url
        preview = await _extract_text(page, max_length=3000)
        combined = f"**Navigated to**: {final_url}\n**Title**: {title}\n\n**Preview** (first ~3000 chars):\n{preview}"
        return _sanitize_and_return(combined, final_url)
    except Exception as e:
        raise _handle_error(e, f"Navigation to {url}") from e


@mcp.tool()
async def comet_read_page(
    selector: Optional[str] = None,
    include_links: bool = True,
    max_length: int = 50000,
) -> str:
    """Read the text content of the current page (or active tab) in Comet.

    PRIMARY USE: Call this after comet_search to retrieve the streamed answer.
    Wait ~30-45s (research mode) or ~15-20s (search mode) before calling.
    If the answer is still loading ("Searching the web" in output), wait
    longer and call again.

    Also use to drill into specific page sections or re-read content.
    Content is auto-sanitized — if injections are detected, run comet_security_scan.

    Args:
        selector: Optional CSS selector to read specific content (e.g. 'main').
        include_links: Whether to include href URLs from links.
        max_length: Maximum characters to return (default 50000).
    """
    try:
        max_length = min(max(0, max_length), MAX_CONTENT_LENGTH)
        page = await _get_page()
        title = await page.title()
        url = page.url
        text = await _extract_text(
            page,
            selector=selector,
            include_links=include_links,
            max_length=max_length,
        )
        combined = f"**Page**: {title}\n**URL**: {url}\n**Selector**: {selector or '(full page)'}\n\n---\n\n{text}"
        return _sanitize_and_return(combined, url)
    except Exception as e:
        raise _handle_error(e) from e


@mcp.tool()
async def comet_screenshot(full_page: bool = False) -> str:
    """Take a screenshot of the current Comet page. Returns base64 PNG.

    Uses raw CDP (not Playwright) to avoid font-renderer hangs. Useful for
    visual verification after navigation or to capture charts/images that
    text extraction misses.

    Args:
        full_page: Whether to capture the full scrollable page (not just viewport).
    """
    try:
        page = await _get_page()
        # Use CDP directly — Playwright's screenshot hangs on Comet's font renderer
        cdp = await page.context.new_cdp_session(page)
        try:
            params = {"format": "png"}
            if full_page:
                params["captureBeyondViewport"] = True
            result = await cdp.send("Page.captureScreenshot", params)
            b64 = result["data"]
        finally:
            await cdp.detach()
        title = await page.title()
        return (
            f"**Screenshot of**: {_safe_title(title)}\n"
            f"**URL**: {page.url}\n\n"
            f"![screenshot](data:image/png;base64,{b64})"
        )
    except Exception as e:
        raise _handle_error(e) from e


@mcp.tool()
async def comet_click(selector: str, wait_after: int = 2) -> str:
    """Click an element on the current Comet page.

    Use 'text=...' for visible text matching (preferred over brittle CSS selectors).
    Waits after click for page to settle. If the element is not found, the tool raises an error —
    use comet_read_page first to verify the element exists.

    Args:
        selector: CSS selector or 'text=Something' for text matching.
        wait_after: Seconds to wait after clicking (default 2).
    """
    try:
        page = await _get_page()
        wait_after = _clamp_wait(wait_after, default=2)
        await page.click(selector, timeout=DEFAULT_TIMEOUT)
        if wait_after > 0:
            await asyncio.sleep(wait_after)
        title = await page.title()
        url = page.url
        return (
            f"**Clicked**: {selector}\n"
            f"**Current page**: {_safe_title(title)}\n"
            f"**URL**: {url}"
        )
    except Exception as e:
        raise _handle_error(e) from e


@mcp.tool()
async def comet_type(
    selector: str,
    text: str,
    press_enter: bool = False,
    clear_first: bool = True,
) -> str:
    """Type text into an input field in the current Comet page.

    For Perplexity searches, prefer comet_search (URL-based, no selectors needed).
    Use this for form inputs on other sites. Clears the field by default before typing.

    Args:
        selector: CSS selector of the input field.
        text: Text to type into the field.
        press_enter: Whether to press Enter after typing.
        clear_first: Whether to clear the field before typing (default true).
    """
    try:
        page = await _get_page()
        if clear_first:
            await page.fill(selector, "")
        await page.type(selector, text, delay=50)
        if press_enter:
            await page.press(selector, "Enter")
            await asyncio.sleep(1)
        return (
            f"**Typed**: '{text}' into {selector}\n"
            f"**Enter pressed**: {press_enter}"
        )
    except Exception as e:
        raise _handle_error(e) from e


@mcp.tool()
async def comet_tabs(
    action: str = "list",
    tab_index: Optional[int] = None,
    url: Optional[str] = None,
) -> str:
    """Manage tabs in the Comet browser. Each comet_search opens a new tab
    (tagged [search] in list output). Use 'list' to see all tabs, 'switch' to
    go back to a previous search result, 'close' to free memory.

    Tab hygiene: list tabs periodically and close old ones. Max 5 search tabs
    are kept (oldest auto-closed). Closing a tab removes it from search tracking.

    Args:
        action: 'list' (show all), 'new' (open tab), 'switch' (by index), 'close' (by index).
        tab_index: Tab index for 'switch' or 'close' (0-based, from 'list' output).
        url: URL for 'new' tab action (opens blank if omitted).
    """
    global _page
    try:
        if action not in VALID_TAB_ACTIONS:
            raise ToolError(f"action must be one of {VALID_TAB_ACTIONS}, got '{action}'")
        browser = await _ensure_browser()
        contexts = browser.contexts
        if not contexts:
            raise ToolError("No browser contexts found.")
        pages = contexts[0].pages

        if action == "list":
            search_pages = {entry["page"] for entry in _search_tabs}
            lines = []
            for i, p in enumerate(pages):
                active = " <- active" if p == _page else ""
                search = " [search]" if p in search_pages else ""
                try:
                    title = await p.title()
                except Exception:
                    title = "(untitled)"
                lines.append(f"  [{i}] {_safe_title(title)} - {p.url}{active}{search}")
            return f"**Open tabs** ({len(pages)}):\n" + "\n".join(lines)

        elif action == "new":
            new_page = await contexts[0].new_page()
            if url:
                await new_page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
            _page = new_page
            return f"**Opened new tab**: {url or 'about:blank'}"

        elif action == "switch":
            if not _valid_tab_index(tab_index, pages):
                raise ToolError(f"Invalid tab index. Available: 0-{len(pages)-1}")
            try:
                _page = pages[tab_index]
                title = await _page.title()
                return f"**Switched to tab [{tab_index}]**: {_safe_title(title)} - {_page.url}"
            except Exception as tab_err:
                raise ToolError(f"Tab {tab_index} is no longer available: {tab_err}")

        elif action == "close":
            if not _valid_tab_index(tab_index, pages):
                raise ToolError(f"Invalid tab index. Available: 0-{len(pages)-1}")
            if len(pages) <= 1:
                raise ToolError("Cannot close the last tab.")
            try:
                target = pages[tab_index]
                title = await target.title()
                await target.close()
                # Remove from search tab registry if tracked
                _search_tabs[:] = [e for e in _search_tabs if e["page"] != target]
                if _page == target:
                    remaining = contexts[0].pages
                    _page = remaining[-1] if remaining else None
                return f"**Closed tab [{tab_index}]**: {_safe_title(title)}"
            except Exception as tab_err:
                raise ToolError(f"Tab {tab_index} is no longer available: {tab_err}")

        raise ToolError(f"Unknown action '{action}'. Use: list, new, switch, close")
    except Exception as e:
        raise _handle_error(e) from e


@mcp.tool()
async def comet_evaluate(expression: str) -> str:
    """Evaluate a JavaScript expression in the current Comet page.

    Powerful but use with care — string results are sanitized for injection
    detection. Use for DOM queries, data extraction, or page manipulation
    that other tools don't cover.

    Args:
        expression: JavaScript expression to evaluate (e.g. 'document.title').
    """
    try:
        page = await _get_page()
        result = await page.evaluate(expression)
        if isinstance(result, (dict, list)):
            result_str = json.dumps(result, indent=2, ensure_ascii=False)
        else:
            result_str = str(result)
        return _sanitize_and_return(result_str, page.url)
    except Exception as e:
        raise _handle_error(e) from e


@mcp.tool()
async def comet_wait(
    selector: Optional[str] = None,
    seconds: Optional[int] = None,
) -> str:
    """Wait for a specific element to appear or a fixed duration.

    Use after comet_click or comet_navigate when content loads asynchronously.
    Provide either selector OR seconds, not both. comet_search returns before the answer is ready, so wait with comet_wait or a fixed
    delay, then call comet_read_page.

    Args:
        selector: CSS selector to wait for (e.g. 'div.results').
        seconds: Fixed seconds to wait (0-120).
    """
    try:
        page = await _get_page()
        if selector:
            await page.wait_for_selector(selector, timeout=DEFAULT_TIMEOUT)
            return f"**Element found**: {selector}"
        elif seconds is not None:
            seconds = _clamp_wait(seconds, default=5)
            await asyncio.sleep(seconds)
            return f"**Waited**: {seconds} seconds"
        else:
            raise ToolError("Provide either 'selector' or 'seconds'.")
    except Exception as e:
        raise _handle_error(e, f"Waiting for '{selector}'" if selector else "") from e


# ---------------------------------------------------------------------------
# Deep Security Scan Tool
# ---------------------------------------------------------------------------
@mcp.tool()
async def comet_security_scan() -> str:
    """Deep security scan of current page for prompt injection and hidden content.

    Run this when: content filter flags injections, page seems suspicious, or
    you want to verify a page is clean before trusting its content. Checks
    CSS-hidden elements, zero-width chars, HTML comments, and 39 injection patterns."""
    try:
        page = await _get_page()
        url = page.url
        title = await page.title()

        # 1. Detect CSS-hidden elements and HTML comments via JS
        hidden_elements = await page.evaluate("""(() => {
            const suspicious = [];
            for (const el of document.querySelectorAll('*')) {
                const style = getComputedStyle(el);
                const text = el.textContent?.trim() || '';
                if (text.length < 20) continue;
                const isHidden = (
                    style.display === 'none' ||
                    style.visibility === 'hidden' ||
                    style.opacity === '0' ||
                    parseFloat(style.fontSize) < 2 ||
                    parseInt(style.height) === 0 ||
                    parseInt(style.width) === 0 ||
                    (style.position === 'absolute' && parseInt(style.left) < -1000) ||
                    (style.position === 'absolute' && parseInt(style.top) < -1000) ||
                    style.clipPath === 'inset(100%)'
                );
                const isSameColor = style.color === style.backgroundColor;
                if (isHidden || isSameColor) {
                    suspicious.push({
                        tag: el.tagName,
                        classes: el.className?.toString().substring(0, 100) || '',
                        text: text.substring(0, 300),
                        reason: isHidden ? 'css-hidden' : 'same-color-text'
                    });
                }
            }
            const comments = [...document.documentElement.outerHTML.matchAll(/<!--([\\s\\S]*?)-->/g)]
                .filter(m => m[1].trim().length > 50)
                .map(m => ({ tag: 'COMMENT', text: m[1].trim().substring(0, 300), reason: 'html-comment' }));
            return [...suspicious, ...comments];
        })()""")

        # 2. Scan visible content
        visible_text = await _extract_text(page, include_collapsed=True)
        visible_scan = _filter.sanitize(visible_text, url)

        # 3. Scan hidden elements for injections
        hidden_threats = []
        for el in (hidden_elements or []):
            raw_text = el.get("text", "")
            # Check the raw text and the zero-width-stripped text: either form can carry the payload.
            el_threats = (_filter.detect_injections(raw_text)
                          or _filter.detect_injections(_filter.strip_hidden_content(raw_text)[0]))
            if el_threats:
                hidden_threats.append({"element": el, "threats": el_threats})

        # 4. Separate comments from hidden elements
        comments = [el for el in (hidden_elements or []) if el.get("reason") == "html-comment"]
        css_hidden = [el for el in (hidden_elements or []) if el.get("reason") != "html-comment"]

        # 5. Determine overall assessment
        total_threats = len(visible_scan.threats) + sum(len(h["threats"]) for h in hidden_threats)
        has_hidden = len(css_hidden) > 0 or len(comments) > 0
        if total_threats > 0:
            overall = "HOSTILE"
        elif has_hidden:
            overall = "SUSPICIOUS"
        else:
            overall = "CLEAN"

        # 6. Build report
        report = []
        report.append(f"🔍 DEEP SECURITY SCAN: {url}")
        report.append("════════════════════════════════════════")
        report.append(f"\nPage Trust Tier: {visible_scan.trust_tier.value}")
        report.append(f"\nVisible Content:")
        report.append(f"  Injection patterns: {len(visible_scan.threats)} found")
        for t in visible_scan.threats:
            report.append(f'  • [{t.category.value}] {t.pattern_name}: "{t.matched_text[:60]}" (pos {t.position})')

        report.append(f"\nHidden Elements: {len(css_hidden)} found")
        for h in hidden_threats:
            el = h["element"]
            if el.get("reason") == "html-comment":
                continue
            report.append(f'  • [{el.get("reason")}] <{el.get("tag")}>: "{el.get("text", "")[:80]}..."')
            report.append(f"    Injections in hidden text: {len(h['threats'])}")

        report.append(f"\nHTML Comments: {len(comments)} suspicious")
        for c in comments:
            report.append(f'  • "{c.get("text", "")[:80]}..."')
            # Check for injections in comments too
            comment_text = c.get("text", "")
            comment_threats = (_filter.detect_injections(comment_text)
                               or _filter.detect_injections(_filter.strip_hidden_content(comment_text)[0]))
            if comment_threats:
                report.append(f"    Injections found: {len(comment_threats)}")

        report.append(f"\nOverall: {overall}")
        report.append("════════════════════════════════════════")

        return "\n".join(report)
    except Exception as e:
        raise _handle_error(e) from e


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    """Entry point for console_scripts and direct execution."""
    mcp.run()


if __name__ == "__main__":
    main()
