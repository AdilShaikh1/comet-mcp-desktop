<p align="center">
  <h1 align="center">Comet MCP Server</h1>
  <p align="center">
    <strong>Give Claude a browser that thinks.</strong>
  </p>
  <p align="center">
    An MCP server connecting Claude Desktop/Code to Perplexity's Comet browser via Chrome DevTools Protocol.
    <br />
    Search the web with AI, navigate pages, read content, click elements, and take screenshots.
  </p>
  <p align="center">
    <a href="#quick-start">Quick Start</a> &middot;
    <a href="#available-tools">Tools</a> &middot;
    <a href="docs/tool-reference.md">API Docs</a> &middot;
    <a href="docs/security.md">Security</a> &middot;
    <a href="docs/configuration.md">Configuration</a>
  </p>
</p>

<br />

> Rather than using static search APIs or overwhelming Claude's context with raw browser automation, Comet MCP **delegates browsing to Perplexity Comet**. Claude stays focused on your coding task while Comet handles navigation, dynamic content, and AI-powered research.

<br />

## How It Works

```
Claude Desktop/Code  ←── MCP (stdio) ──→  Comet MCP Server  ←── CDP (9222) ──→  Comet Browser
```

1. **Comet MCP Server** auto-launches Comet with remote debugging on port 9222
2. Connects to Comet via **Chrome DevTools Protocol** using Playwright
3. **Claude** communicates with the server over MCP stdio transport
4. Claude can search, navigate, read, click, type, evaluate JS, and screenshot — all in your Comet browser

<br />

## Quick Start

### 1. Configure Claude Desktop / Claude Code

**Claude Desktop** — add to your config file:

| Platform | Config path |
|----------|------------|
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |

```json
{
  "mcpServers": {
    "comet": {
      "command": "uvx",
      "args": ["comet-mcp-desktop"]
    }
  }
}
```

**Claude Code** — add to `~/.claude.json` or `.mcp.json` in your project root:

```json
{
  "mcpServers": {
    "comet": {
      "command": "uvx",
      "args": ["comet-mcp-desktop"]
    }
  }
}
```

> Requires [`uv`](https://docs.astral.sh/uv/). The MCP server and all dependencies install automatically on first run.

### 2. Install Comet Browser

Download and install [Perplexity Comet](https://perplexity.ai/comet).

**That's it.** The server auto-launches Comet with remote debugging when needed.

<details>
<summary><strong>Manual setup from source</strong></summary>

<br />

```bash
git clone https://github.com/AdilShaikh1/comet-mcp-desktop.git
cd comet-mcp-desktop
uv sync
uv run playwright install chromium
```

See [Configuration](docs/configuration.md) for full paths setup and environment variables.

</details>

<br />

## Available Tools

| Tool | Description |
|------|-------------|
| `comet_connect` | Connect to Comet via CDP (auto-launches if needed) |
| `comet_search` | Search via Perplexity — returns AI-generated results |
| `comet_navigate` | Navigate to any URL |
| `comet_read_page` | Extract page text, with optional CSS selector |
| `comet_screenshot` | Capture screenshot (base64 PNG) |
| `comet_click` | Click elements by CSS selector or text |
| `comet_type` | Type into input fields |
| `comet_tabs` | List, open, switch, or close tabs |
| `comet_evaluate` | Run JavaScript in the page context |
| `comet_wait` | Wait for an element or a fixed delay |
| `comet_security_scan` | Deep scan for hidden text and injection patterns |

> Full parameter documentation: **[Tool Reference](docs/tool-reference.md)**

<br />

## Example Usage

| You say | Claude does |
|---------|-----------|
| *"Search Perplexity for the latest AI news"* | `comet_search` — waits for Perplexity, returns AI-synthesized answer |
| *"Open Hacker News and summarize the front page"* | `comet_navigate` + `comet_read_page` |
| *"Click the first link and read the article"* | `comet_click` + `comet_read_page` |
| *"Take a screenshot of what you see"* | `comet_screenshot` — captures via raw CDP |
| *"Is this page safe?"* | `comet_security_scan` — checks for hidden text and injections |

<br />

## Web Content Trust Policy

All web content is sanitized through a `ContentFilter` before reaching Claude — defense-in-depth against prompt injection via web pages.

```
Comet Browser  ──→  raw text  ──→  ContentFilter.sanitize()  ──→  security header + cleaned text  ──→  Claude
```

| Trust Tier | Criteria |
|------------|----------|
| **HIGH** | `.gov`, `.edu`, arxiv, bbc, reuters, nih |
| **STANDARD** | Established companies, unknown clean domains |
| **LOW** | wordpress, medium, reddit, quora |
| **UNTRUSTED** | Injection patterns detected (auto-downgraded) |

The filter scans for **39 injection patterns** across **12 threat categories** including direct injection, authority spoofing, data exfiltration, delimiter injection, and more.

> Full details: **[Security Documentation](docs/security.md)**

<br />

## How This Compares

| Feature | Search APIs | Browser MCPs | **Comet MCP** |
|---------|------------|-------------|--------------|
| AI-powered search | Varies | No | **Perplexity AI** |
| Interactive browsing | No | Yes | **Yes** |
| Context window impact | Low | High | **Low** |
| Screenshots | No | Yes | **Yes** |
| Security filtering | No | No | **Yes** |
| Click/type/navigate | No | Yes | **Yes** |

> Comet MCP gives Claude access to **Perplexity's AI search** with full browser control, while keeping Claude's context window clean through multi-agent delegation.

<br />

## Testing

**45 tests** — 20 static + 25 end-to-end browser tests.

```bash
uv run python test_comet.py --with-browser
```

<details>
<summary><strong>Test tier breakdown</strong></summary>

| Tier | Tests | Coverage |
|------|-------|----------|
| **1a** Static Core | 11 | Syntax, imports, tool registration, async, error handling |
| **1b** Static Filter | 9 | Injection detection, false positives, trust classification |
| **2a** Live Browser | 17 | All 11 tools against a live Comet instance |
| **2b** Live Filter | 8 | E2E injection/hidden text detection, security scan |

</details>

<br />

## Troubleshooting

<details>
<summary><strong>"Could not connect to Comet"</strong></summary>

Comet is auto-launched, but if it fails:
- Check that Comet is installed
- Check port 9222 is free
- Set `COMET_PATH` env var for non-standard installs
- Verify: open `http://localhost:9222/json`

</details>

<details>
<summary><strong>Screenshot hangs</strong></summary>

Uses raw CDP `Page.captureScreenshot` to avoid Playwright font renderer hangs. Ensure you're on the latest version.

</details>

<details>
<summary><strong>Connection lost</strong></summary>

Call `comet_connect` to reconnect without restarting.

</details>

<details>
<summary><strong>Slow search results</strong></summary>

Perplexity answers take 5-15 seconds. Default `wait_seconds=10`. Increase to 15-20 for complex queries.

</details>

<br />

## Tech Stack

| Component | Technology |
|-----------|-----------|
| Runtime | Python 3.14+ with `uv` |
| Browser automation | Playwright (CDP) |
| MCP transport | `mcp[cli]` SDK (stdio) |
| Screenshots | Raw CDP `Page.captureScreenshot` |
| Content security | `ContentFilter` — 39 patterns, 12 categories |

<br />

## Documentation

| Document | Description |
|----------|-------------|
| **[Tool Reference](docs/tool-reference.md)** | Full API docs for all 11 tools with parameters, defaults, and examples |
| **[Security](docs/security.md)** | Web Content Trust Policy, threat categories, trust tiers, adding patterns |
| **[Configuration](docs/configuration.md)** | Environment variables, platform support, MCP config, parameter validation |
| **[Contributing](CONTRIBUTING.md)** | How to contribute, dev setup, code guidelines |

## License

[MIT](LICENSE)
