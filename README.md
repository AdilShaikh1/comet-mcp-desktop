# Comet MCP Server

**Give Claude Code a browser that thinks.** An MCP server connecting Claude Desktop/Code to Perplexity's Comet browser via Chrome DevTools Protocol (CDP) — search the web with AI, navigate pages, read content, click elements, and take screenshots.

Rather than using static search APIs or overwhelming Claude's context with raw browser automation, Comet MCP delegates browsing to Perplexity Comet. Claude stays focused on your coding task while Comet handles navigation, dynamic content, and AI-powered research.

---

## How It Works

```
┌──────────────┐     MCP (stdio)         ┌──────────────┐     CDP (port 9222)     ┌──────────────┐
│              │ ◄─────────────────────  │              │ ◄──────────────────────► │              │
│ Claude       │                          │ Comet MCP    │   Chrome DevTools       │ Comet        │
│ Desktop/Code │ ─────────────────────► │ Server       │   Protocol              │ Browser      │
│              │                          │ (Python)     │ ──────────────────────► │ (Chromium)   │
└──────────────┘                          └──────────────┘                         └──────────────┘
```

1. **Comet** runs with remote debugging enabled (port 9222)
2. **Comet MCP Server** connects via CDP using Playwright
3. **Claude** communicates with the server over MCP stdio transport
4. Claude can search, navigate, read, click, type, evaluate JS, and screenshot in your Comet browser

---

## Quick Start

### 1. Install Dependencies

```bash
cd comet-mcp
uv sync
uv run playwright install chromium
```

> **Note**: This project uses [`uv`](https://docs.astral.sh/uv/) exclusively for Python package management.

### 2. Launch Comet with CDP

**Windows (PowerShell):**
```powershell
& "$env:LOCALAPPDATA\Perplexity\Comet\Application\comet.exe" --remote-debugging-port=9222
```

**macOS:**
```bash
/Applications/Comet.app/Contents/MacOS/Comet --remote-debugging-port=9222
```

Verify CDP is reachable by opening `http://localhost:9222/json` in a browser — you should see a JSON array of targets.

### 3. Configure Claude Desktop / Claude Code

**Claude Desktop** — add to `%APPDATA%\Claude\claude_desktop_config.json` (Windows) or `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "comet": {
      "command": "/FULL/PATH/TO/comet-mcp/.venv/Scripts/python.exe",
      "args": ["/FULL/PATH/TO/comet-mcp/comet_mcp.py"],
      "env": {
        "COMET_CDP_URL": "http://localhost:9222",
        "COMET_TIMEOUT": "30000",
        "COMET_MAX_CONTENT": "50000"
      }
    }
  }
}
```

**Claude Code** — add to `~/.claude.json` or `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "comet": {
      "command": "/FULL/PATH/TO/comet-mcp/.venv/Scripts/python.exe",
      "args": ["/FULL/PATH/TO/comet-mcp/comet_mcp.py"],
      "env": {
        "COMET_CDP_URL": "http://localhost:9222",
        "COMET_TIMEOUT": "30000",
        "COMET_MAX_CONTENT": "50000"
      }
    }
  }
}
```

> Replace `/FULL/PATH/TO/` with the actual path. On macOS/Linux use `.venv/bin/python` instead of `.venv/Scripts/python.exe`.

### 4. Use

1. Start Comet with the `--remote-debugging-port=9222` flag
2. Restart Claude Desktop (or reload MCP servers in Claude Code)
3. Ask Claude to search, browse, or research!

---

## Available Tools

| Tool | Description |
|------|-------------|
| `comet_connect` | Connect to Comet via CDP (auto-launches if needed) |
| `comet_search` | Search via Perplexity using URL-based navigation, returns AI-generated results |
| `comet_navigate` | Navigate to any URL with configurable wait conditions |
| `comet_read_page` | Extract page text via JS evaluation, with optional CSS selector |
| `comet_screenshot` | Capture screenshot via raw CDP `Page.captureScreenshot` (base64 PNG) |
| `comet_click` | Click elements by CSS selector or `text=...` matching |
| `comet_type` | Type into input fields with optional clear-first and Enter |
| `comet_tabs` | List, open, switch, or close browser tabs |
| `comet_evaluate` | Run arbitrary JavaScript in the page context |
| `comet_wait` | Wait for an element selector or a fixed delay |
| `comet_security_scan` | Deep scan for hidden text, CSS-invisible elements, and injection patterns |

---

## Web Content Trust Policy

All web content returned by this server passes through a server-side `ContentFilter` that implements defense-in-depth sanitization before content reaches Claude.

```
Comet Browser → raw text → ContentFilter.sanitize() → security header + cleaned text → Claude
```

**What gets filtered:** `comet_search`, `comet_read_page`, `comet_navigate`, `comet_evaluate` (string results)

**What does NOT get filtered:** `comet_screenshot` (binary image), `comet_connect`, `comet_click`, `comet_type`, `comet_tabs`, `comet_wait` (no web content)

### Trust Tiers

| Tier | Examples |
|------|----------|
| **HIGH** | `.gov`, `.edu`, arxiv, bbc, reuters, nih |
| **STANDARD** | Established companies, unknown but clean domains |
| **LOW** | wordpress, medium, reddit, quora (user-generated content) |
| **UNTRUSTED** | Any page with injection patterns detected (auto-downgrade) |

### Threat Detection

The filter scans for 40+ injection patterns across 12 threat categories: direct injection, indirect injection, authority spoofing, data exfiltration, social engineering, delimiter injection, encoding obfuscation, manufactured consent, moral inversion, secrecy instructions, context extraction, and hidden text.

---

## Example Usage

**"Search Perplexity for the latest AI news"**
> Claude uses `comet_search` with the query, waits for Perplexity to generate results, and returns the AI-synthesized answer.

**"Open Hacker News and summarize the front page"**
> Claude uses `comet_navigate` to go to `https://news.ycombinator.com`, then `comet_read_page` to extract content.

**"Click the first link and read the article"**
> Claude uses `comet_click` on the link, waits, then `comet_read_page` to extract the article text.

**"Take a screenshot of what you see"**
> Claude uses `comet_screenshot` to capture the rendered page via raw CDP.

**"Is this page safe?"**
> Claude uses `comet_security_scan` to check for hidden text, CSS-invisible elements, and injection attempts.

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMET_CDP_URL` | `http://localhost:9222` | CDP endpoint for Comet |
| `COMET_TIMEOUT` | `30000` | Default timeout in ms for page operations |
| `COMET_MAX_CONTENT` | `50000` | Max characters to extract from pages |
| `COMET_PATH` | auto-detected | Override Comet executable path |

---

## Testing

The test suite includes 45 tests: 20 static + 25 end-to-end browser tests.

```bash
# Full E2E suite (requires Comet running with CDP)
uv run python test_comet.py --with-browser

# Run a specific test
uv run python test_comet.py --with-browser --test tool_comet_search
```

### Test Tiers

- **Tier 1a — Static Core (11 tests):** Syntax, imports, server object, tool registration, async checks, helpers, error handling, URL-based search, Windows compat, entrypoint
- **Tier 1b — Static Filter (9 tests):** Content filter, injection detection, false positives, hidden content, trust classification, base64, sanitize pipeline, security scan tool
- **Tier 2a — Live Browser (17 tests):** All 11 tools tested against a live Comet instance
- **Tier 2b — Live Filter (8 tests):** End-to-end injection detection, hidden text detection, security scan, false alarm verification

---

## Troubleshooting

### "Could not connect to Comet"
- Ensure Comet is running with `--remote-debugging-port=9222`
- Check that nothing else is using port 9222
- Verify CDP: open `http://localhost:9222/json` — should return JSON

### Screenshot hangs
This server uses raw CDP `Page.captureScreenshot` instead of Playwright's `page.screenshot()` because Playwright's font renderer hangs indefinitely over CDP on Comet. If you see timeout issues, ensure you're on the latest version.

### Connection lost mid-session
Call the `comet_connect` tool to reconnect without restarting.

### Slow search results
Perplexity AI answers take 5-15 seconds to generate. The default `wait_seconds=10` works for most queries. For complex research, increase to 15-20.

---

## How This Compares

| Feature | Search APIs (Tavily, WebFetch) | Browser Automation (Puppeteer MCP) | Comet MCP |
|---------|-------------------------------|-----------------------------------|-----------|
| AI-powered search | Varies | No | **Perplexity AI** |
| Interactive browsing | No | Yes | **Yes** |
| Context window impact | Low | **High** (one-agent-do-all) | **Low** (delegated) |
| Screenshots | No | Yes | **Yes** |
| Security filtering | No | No | **Yes** (ContentFilter) |
| Click/type/navigate | No | Yes | **Yes** |

The key advantage: Comet MCP gives Claude access to **Perplexity's AI search** with full browser control, while keeping Claude's context window clean through multi-agent delegation.

---

## Tech Stack

- **Python 3.14+** with `uv` package manager
- **Playwright** for CDP browser automation
- **MCP SDK** (`mcp[cli]`) for Model Context Protocol transport
- **Pydantic** for data validation
- **Raw CDP** for screenshot capture (bypasses Playwright font renderer)

## License

MIT
