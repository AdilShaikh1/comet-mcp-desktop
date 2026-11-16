# Tool Reference

Complete API documentation for all 12 Comet MCP tools.

---

## `comet_connect`

Connect to Comet via CDP. Auto-launches Comet if needed. **Call this before using any other tool.**

```
Parameters: none
```

**Returns:** Connection status message with open tab count and active page title, followed by a short workflow guide (Search, Read, Tabs, Errors).

**Example response:**
```
Connected to Comet at http://localhost:9222
Open tabs: 3
Active page: Example Domain

## Comet Workflow Guide
**Search**: comet_search starts a search and returns immediately (new tab per query, max 5). ...
**Read**: Call comet_read_page after ~30-45s (research) or ~15-20s (search) to get results. ...
**Tabs**: Each search gets its own tab (tagged [search] in comet_tabs list). ...
**Errors**: 'connection lost' -> call comet_connect again. ...
```

**Notes:**
- Reconnecting forgets the tracked search tabs but leaves them open in Comet.

---

## `comet_search`

Start a Perplexity search in a new tab. Navigates to `perplexity.ai/search?q=QUERY` and returns at once with the tab index and URL. Uses URL-based navigation — no CSS selectors needed.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `string` | *required* | The search query (URL-encoded automatically) |
| `mode` | `string` | `"search"` | Search mode: `search` or `research` |

**Notes:**
- The query is automatically URL-encoded via `urllib.parse.quote()`
- Empty queries are rejected with an error
- Invalid `mode` values return an error
- It returns the query, mode, tab index and URL, not the answer. That short result passes through the ContentFilter, and the answer is filtered when `comet_read_page` reads it
- The answer streams in after `comet_search` returns. Call `comet_read_page` after about 15-20 s in search mode or 30-45 s in research mode
- Each search opens its own tab (tagged `[search]` in `comet_tabs`); at most 5 search tabs are kept and the oldest is closed first

---

## `comet_search_finance`

Open a Perplexity Finance page in the active tab. Like `comet_navigate`, it navigates the current tab (it does not open a new one) and returns at once with the mode label, final URL and page title. In `screener` mode it returns after typing the query.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | `string` | `"market"` | `market`, `quote`, `screener`, `earnings` or `predictions` |
| `ticker` | `string` | `null` | Symbol for `quote` mode, such as `NVDA`, `BTCUSD` or `^VIX` |
| `query` | `string` | `null` | Natural-language query for `screener` mode |

| Mode | Page | Wait before reading |
|------|------|---------------------|
| `market` | `/finance` dashboard: indices, sectors, movers, crypto, AI summary | ~3-5 s |
| `quote` | `/finance/<ticker>`: price, fundamentals, AI analysis | ~3-5 s |
| `screener` | `/finance/screener`: types the query and submits it | ~10-20 s |
| `earnings` | `/finance/earnings`: earnings calendar | ~3-5 s |
| `predictions` | `/finance/predictions`: Polymarket prediction markets | ~3-5 s |

**Returns:** A short status text, not the data. Call `comet_read_page(selector="main")` after the wait hint to read the page.

**Notes:**
- Invalid `mode`, a missing or invalid `ticker` in `quote` mode and a missing `query` in `screener` mode return an error before the browser is touched
- `screener` runs on Perplexity's Computer feature, so each query uses your Perplexity account
- If the screener input cannot be found, the result says so and points to `comet_type`
- The status result passes through the ContentFilter because the page title comes from the page

---

## `comet_navigate`

Navigate Comet to a specific URL.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | `string` | *required* | The URL to navigate to |
| `wait_for` | `string` | `"domcontentloaded"` | Wait condition: `load`, `domcontentloaded`, or `networkidle` |

**Notes:**
- Invalid `wait_for` values return an error
- Returns a text preview of the loaded page (filtered through ContentFilter)
- The preview is truncated to `COMET_MAX_CONTENT` characters

---

## `comet_read_page`

Read text content from the current page.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `selector` | `string` | `null` | Optional CSS selector to read specific content |
| `include_links` | `bool` | `true` | Whether to include href URLs from links |
| `max_length` | `int` | `50000` | Maximum characters to return (capped at `COMET_MAX_CONTENT`) |

**Notes:**
- Without a selector, extracts `document.body.innerText`
- With a selector, extracts text from matching elements only
- When `include_links` is true, appends a link reference section
- Content passes through the ContentFilter before being returned

---

## `comet_screenshot`

Take a screenshot of the current page. Returns base64-encoded PNG.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `full_page` | `bool` | `false` | Whether to capture the full scrollable page |

**Notes:**
- Uses raw CDP `Page.captureScreenshot` instead of Playwright's `page.screenshot()`
- This avoids a known issue where Playwright's font renderer hangs indefinitely over CDP on Comet
- Returns base64-encoded PNG data
- This tool does NOT pass through the ContentFilter (binary image data)

---

## `comet_click`

Click an element on the current page.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `selector` | `string` | *required* | CSS selector or `text=Something` for text matching |
| `wait_after` | `int` | `2` | Seconds to wait after clicking (clamped to 0-120) |

**Notes:**
- Supports standard CSS selectors: `#id`, `.class`, `button`, `a[href="/path"]`
- Supports Playwright text selectors: `text=Click me`
- Returns the page title after clicking
- Returns a descriptive error if the element is not found

---

## `comet_type`

Type text into an input field.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `selector` | `string` | *required* | CSS selector of the input field |
| `text` | `string` | *required* | Text to type |
| `press_enter` | `bool` | `false` | Whether to press Enter after typing |
| `clear_first` | `bool` | `true` | Whether to clear the field before typing |

**Notes:**
- When `clear_first` is true, the field is triple-clicked (select all) then filled
- `press_enter` is useful for submitting search forms

---

## `comet_tabs`

Manage tabs in the Comet browser. Tabs opened by `comet_search` are tagged `[search]` in the `list` output.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | `string` | `"list"` | Tab action: `list`, `new`, `switch`, or `close` |
| `tab_index` | `int` | `null` | Tab index for `switch` or `close` (0-based) |
| `url` | `string` | `null` | URL for `new` tab action |

**Actions:**

| Action | Required params | Description |
|--------|----------------|-------------|
| `list` | none | List all open tabs with index, title, and URL; search tabs carry a `[search]` tag |
| `new` | `url` (optional) | Open a new tab, optionally navigating to a URL |
| `switch` | `tab_index` | Switch to the tab at the given index |
| `close` | `tab_index` | Close the tab at the given index |

**Notes:**
- At most 5 search tabs are kept; the oldest is closed first when a sixth search starts
- Closing a search tab removes it from search tracking
- Invalid `action` values return an error
- Invalid or out-of-range `tab_index` returns a descriptive error
- Tab operations include race condition handling (tabs may close between listing and switching)

---

## `comet_evaluate`

Execute JavaScript in the page context.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `expression` | `string` | *required* | JavaScript expression to evaluate |

**Notes:**
- Runs in the context of the current page
- String results pass through the ContentFilter (may contain web content)
- Non-string results (numbers, objects) are returned as-is
- Syntax errors are caught and returned as descriptive error messages

**Examples:**
```javascript
// Simple expression
"2 + 2"  // Returns: "4"

// DOM query
"document.title"  // Returns: page title

// Complex evaluation
"document.querySelectorAll('a').length"  // Returns: link count
```

---

## `comet_wait`

Wait for a specific element or a fixed duration. At least one parameter must be provided.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `selector` | `string` | `null` | CSS selector to wait for |
| `seconds` | `int` | `null` | Fixed seconds to wait (clamped to 0-120) |

**Notes:**
- If both parameters are `null`, returns an error
- `comet_search` returns before the answer is ready, so wait with `comet_wait` or a fixed delay, then call `comet_read_page`
- If both are provided, waits for the selector (seconds is ignored)
- Selector wait uses Playwright's `wait_for_selector` with the configured timeout
- Fixed delay is clamped to `MAX_WAIT_SECONDS` (120) to prevent DoS

---

## `comet_security_scan`

Deep security scan of the current page. Use when a page seems suspicious.

```
Parameters: none
```

**What it checks:**
- **Visible text:** Injection patterns in page content
- **Hidden elements:** CSS `display:none`, `visibility:hidden`, `opacity:0`, off-screen positioning
- **HTML comments:** Content hidden in `<!-- -->` blocks
- **Overall assessment:** CLEAN, SUSPICIOUS, or HOSTILE

**Example response:**
```
Security Deep Scan
════════════════════════════════════════
URL: https://example.com
Trust tier: standard

Visible text analysis:
  Length: 1256 chars
  Injections found: 0

Hidden elements found: 0
HTML comments found: 0

Overall: CLEAN
════════════════════════════════════════
```
