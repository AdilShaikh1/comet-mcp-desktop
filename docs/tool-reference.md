# Tool Reference

Complete API documentation for all 11 Comet MCP tools.

---

## `comet_connect`

Connect to Comet via CDP. Auto-launches Comet if needed. **Call this before using any other tool.**

```
Parameters: none
```

**Returns:** Connection status message with open tab count and active page title.

**Example response:**
```
Connected to Comet at http://localhost:9222
Open tabs: 3
Active page: Example Domain
```

---

## `comet_search`

Search the web using Perplexity. Navigates to `perplexity.ai/search?q=QUERY` and extracts AI-generated results. Uses URL-based navigation — no CSS selectors needed.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | `string` | *required* | The search query (URL-encoded automatically) |
| `wait_seconds` | `int` | `10` | Seconds to wait for AI response generation (clamped to 0-120) |
| `mode` | `string` | `"search"` | Search mode: `search` or `research` |

**Notes:**
- The query is automatically URL-encoded via `urllib.parse.quote()`
- Empty queries are rejected with an error
- Invalid `mode` values return an error
- Results pass through the ContentFilter before being returned
- Perplexity answers typically take 5-15 seconds to generate

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

Manage tabs in the Comet browser.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `action` | `string` | `"list"` | Tab action: `list`, `new`, `switch`, or `close` |
| `tab_index` | `int` | `null` | Tab index for `switch` or `close` (0-based) |
| `url` | `string` | `null` | URL for `new` tab action |

**Actions:**

| Action | Required params | Description |
|--------|----------------|-------------|
| `list` | none | List all open tabs with index, title, and URL |
| `new` | `url` (optional) | Open a new tab, optionally navigating to a URL |
| `switch` | `tab_index` | Switch to the tab at the given index |
| `close` | `tab_index` | Close the tab at the given index |

**Notes:**
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
