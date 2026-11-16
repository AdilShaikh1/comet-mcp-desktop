"""
Comet Browser MCP Server
========================
An MCP server that lets Claude Desktop control the Comet browser (Perplexity's
AI browser) via Chrome DevTools Protocol. Claude can type searches, navigate
pages, read content, take screenshots, and interact with web elements.

Usage:
  1. Launch Comet with remote debugging:
     comet.exe --remote-debugging-port=9222
  2. Start this MCP server (configured in Claude Desktop's config)
  3. Claude can now control your Comet browser!
"""

import asyncio
import json
import os
import subprocess
import time
import urllib.request
from typing import Optional
from urllib.parse import quote, urlparse

import sys

from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright, Browser, Page

from content_filter import ContentFilter

_filter = ContentFilter()

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
DEFAULT_CDP_PORT = 9222
# A trailing slash would make the poll URL "//json/version", which DevTools does not serve.
CDP_URL = os.environ.get("COMET_CDP_URL", f"http://localhost:{DEFAULT_CDP_PORT}").rstrip("/")
LOCAL_HOSTS = ("localhost", "127.0.0.1", "::1")  # auto-launch only starts a local Comet


def _port_of(url: str) -> int:
    """Port named in a CDP URL, or the default when the URL has none."""
    return urlparse(url).port or DEFAULT_CDP_PORT


CDP_PORT = _port_of(CDP_URL)
LAUNCH_POLL_ATTEMPTS = 20  # x LAUNCH_POLL_INTERVAL = 10 s when the port refuses; up to 30 s if it stalls
LAUNCH_POLL_INTERVAL = 0.5  # s
PROCESS_CHECK_TIMEOUT = 5  # s
DEFAULT_TIMEOUT = int(os.environ.get("COMET_TIMEOUT", "30000"))  # ms
MAX_CONTENT_LENGTH = int(os.environ.get("COMET_MAX_CONTENT", "50000"))  # chars
MAX_WAIT_SECONDS = 120  # hard cap for any sleep/wait parameter
VALID_SEARCH_MODES = ("search", "research")
VALID_WAIT_FOR = ("load", "domcontentloaded", "networkidle")
VALID_TAB_ACTIONS = ("list", "new", "switch", "close")


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
mcp = FastMCP("comet_mcp")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _find_comet_path() -> Optional[str]:
    """Find the Comet executable on Windows or macOS (Comet has no Linux build)."""
    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    # Env-derived entries are skipped when the variable is unset, so no relative path is probed.
    candidates = [
        os.environ.get("COMET_PATH"),  # an explicit override wins
        local_app_data and os.path.join(local_app_data, "Perplexity", "Comet", "Application", "comet.exe"),
        local_app_data and os.path.join(local_app_data, "Perplexity", "Comet", "comet.exe"),  # reported, unverified
        program_files and os.path.join(program_files, "Perplexity", "Comet", "Application", "comet.exe"),
        "/Applications/Comet.app/Contents/MacOS/Comet",
        "/Applications/Perplexity Comet.app/Contents/MacOS/comet",  # reported, unverified
    ]
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return None


def _comet_running() -> bool:
    """True if a Comet process exists. Used only to avoid a second launch, never to kill."""
    try:
        if sys.platform == "win32":
            # Full path: a bare name would let a tasklist.exe in the current folder run first.
            tasklist = os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tasklist.exe")
            result = subprocess.run(
                [tasklist, "/FI", "IMAGENAME eq comet.exe", "/NH"],
                capture_output=True, text=True, timeout=PROCESS_CHECK_TIMEOUT,
            )
            return "comet.exe" in result.stdout.lower()
        if sys.platform == "darwin":
            return subprocess.run(
                ["pgrep", "-ix", "comet"], capture_output=True, timeout=PROCESS_CHECK_TIMEOUT,
            ).returncode == 0
    except Exception:
        pass
    return False


async def _launch_comet(path: str) -> bool:
    """Start Comet detached with remote debugging; True once the CDP endpoint answers.

    Raises ConnectionError when the executable cannot be started at all.
    """
    try:
        # Comet must not hold the MCP stdio pipes: they carry the JSON-RPC stream.
        subprocess.Popen(
            [path, f"--remote-debugging-port={CDP_PORT}"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=getattr(subprocess, "DETACHED_PROCESS", 0),  # Windows
            start_new_session=True,  # POSIX; ignored on Windows
        )
    except OSError as error:
        raise ConnectionError(f"Could not start Comet at {path}: {error}") from error
    for _ in range(LAUNCH_POLL_ATTEMPTS):
        try:
            urllib.request.urlopen(f"{CDP_URL}/json/version", timeout=1)
            return True
        except Exception:
            await asyncio.sleep(LAUNCH_POLL_INTERVAL)
    return False


async def _ensure_browser() -> Browser:
    """Connect to Comet via CDP, launching it only when it is not already running."""
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
        _browser = await _playwright.chromium.connect_over_cdp(CDP_URL)
        return _browser
    except Exception as error:
        # First line only: Playwright errors carry a long call log after it.
        connect_error = str(error).strip().splitlines()[0] if str(error).strip() else type(error).__name__

    if urlparse(CDP_URL).hostname not in LOCAL_HOSTS:
        raise ConnectionError(f"Could not connect to Comet at {CDP_URL} ({connect_error}).")
    # A second launch would only open a window in the running instance, so ask the user instead.
    if _comet_running():
        raise ConnectionError(
            f"Comet is running but {CDP_URL} did not accept a connection ({connect_error}). "
            f"If Comet was started without remote debugging, quit it fully and start it with "
            f"--remote-debugging-port={CDP_PORT}; on a managed machine the RemoteDebuggingAllowed "
            "policy may block debugging."
        )
    path = _find_comet_path()
    if not path:
        raise ConnectionError(
            "Comet not found. Set COMET_PATH to the Comet executable; "
            "Comet runs on Windows and macOS only."
        )
    if not await _launch_comet(path):
        raise ConnectionError(
            f"Launched Comet but {CDP_URL} did not answer. "
            "The RemoteDebuggingAllowed policy may block remote debugging."
        )
    _browser = await _playwright.chromium.connect_over_cdp(CDP_URL)
    return _browser


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


def _handle_error(e: Exception, context: str = "") -> str:
    """Format tool errors consistently."""
    error_type = type(e).__name__
    if "closed" in str(e).lower():
        return "Error: Browser connection lost. Use comet_connect to reconnect."
    if "Timeout" in str(e):
        return f"Error: {context} timed out. {e}" if context else f"Error: Timed out. {e}"
    return f"Error ({error_type}): {e}"


def _sanitize_and_return(text: str, url: str) -> str:
    """Run content filter and log injections. Returns sanitized text."""
    scan = _filter.sanitize(text, url)
    if scan.injection_detected:
        print(f"⚠️ INJECTION on {url}: {len(scan.threats)} patterns", file=sys.stderr)
    return scan.text


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
    """Connect to the Comet browser via CDP. Auto-launches Comet if needed.

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
            f"Active page: {title}\n"
            f"\n"
            f"## Comet Workflow Guide\n"
            f"**Search**: comet_search starts a search and returns immediately (new tab per query, max {MAX_SEARCH_TABS}). "
            f"Use mode='research' for complex queries. Perplexity streams the answer in the background.\n"
            f"**Read**: Call comet_read_page after ~30-45s (research) or ~15-20s (search) to get results. "
            f"Use comet_security_scan on any page that seems suspicious.\n"
            f"**Tabs**: Each search gets its own tab (tagged [search] in comet_tabs list). "
            f"Use comet_tabs to list/switch/close. Oldest search tab auto-closes at cap.\n"
            f"**Errors**: 'connection lost' → call comet_connect again. "
            f"'timed out' → call comet_connect to reconnect."
        )
    except Exception as e:
        return _handle_error(e)


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
            return f"Error: mode must be one of {VALID_SEARCH_MODES}, got '{mode}'"
        if not query or not query.strip():
            return "Error: query must not be empty."
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
        return _handle_error(e, "Search")


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
            return f"Error: wait_for must be one of {VALID_WAIT_FOR}, got '{wait_for}'"
        page = await _get_page()
        await page.goto(url, wait_until=wait_for, timeout=DEFAULT_TIMEOUT)
        title = await page.title()
        final_url = page.url
        preview = await _extract_text(page, max_length=3000)
        combined = f"**Navigated to**: {final_url}\n**Title**: {title}\n\n**Preview** (first ~3000 chars):\n{preview}"
        return _sanitize_and_return(combined, final_url)
    except Exception as e:
        return _handle_error(e, f"Navigation to {url}")


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
        return _handle_error(e)


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
            f"**Screenshot of**: {title}\n"
            f"**URL**: {page.url}\n\n"
            f"![screenshot](data:image/png;base64,{b64})"
        )
    except Exception as e:
        return _handle_error(e)


@mcp.tool()
async def comet_click(selector: str, wait_after: int = 2) -> str:
    """Click an element on the current Comet page.

    Use 'text=...' for visible text matching (preferred over brittle CSS selectors).
    Waits after click for page to settle. If element not found, returns error —
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
            f"**Current page**: {title}\n"
            f"**URL**: {url}"
        )
    except Exception as e:
        return _handle_error(e)


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
        return _handle_error(e)


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
            return f"Error: action must be one of {VALID_TAB_ACTIONS}, got '{action}'"
        browser = await _ensure_browser()
        contexts = browser.contexts
        if not contexts:
            return "Error: No browser contexts found."
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
                lines.append(f"  [{i}] {title} - {p.url}{active}{search}")
            return f"**Open tabs** ({len(pages)}):\n" + "\n".join(lines)

        elif action == "new":
            new_page = await contexts[0].new_page()
            if url:
                await new_page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_TIMEOUT)
            _page = new_page
            return f"**Opened new tab**: {url or 'about:blank'}"

        elif action == "switch":
            if not _valid_tab_index(tab_index, pages):
                return f"Error: Invalid tab index. Available: 0-{len(pages)-1}"
            try:
                _page = pages[tab_index]
                title = await _page.title()
                return f"**Switched to tab [{tab_index}]**: {title} - {_page.url}"
            except Exception as tab_err:
                return f"Error: Tab {tab_index} is no longer available: {tab_err}"

        elif action == "close":
            if not _valid_tab_index(tab_index, pages):
                return f"Error: Invalid tab index. Available: 0-{len(pages)-1}"
            if len(pages) <= 1:
                return "Error: Cannot close the last tab."
            try:
                target = pages[tab_index]
                title = await target.title()
                await target.close()
                # Remove from search tab registry if tracked
                _search_tabs[:] = [e for e in _search_tabs if e["page"] != target]
                if _page == target:
                    remaining = contexts[0].pages
                    _page = remaining[-1] if remaining else None
                return f"**Closed tab [{tab_index}]**: {title}"
            except Exception as tab_err:
                return f"Error: Tab {tab_index} is no longer available: {tab_err}"

        return f"Error: Unknown action '{action}'. Use: list, new, switch, close"
    except Exception as e:
        return _handle_error(e)


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
        return _handle_error(e)


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
            return "Error: Provide either 'selector' or 'seconds'."
    except Exception as e:
        return _handle_error(e, f"Waiting for '{selector}'" if selector else "")


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
        return _handle_error(e)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    """Entry point for console_scripts and direct execution."""
    mcp.run()


if __name__ == "__main__":
    main()
