<h1 align="center">Comet MCP Desktop</h1>

<p align="center"><strong>Claude drives Perplexity's Comet browser through twelve&nbsp;MCP&nbsp;tools.</strong></p>

<p align="center">An MCP server for Claude Desktop and&nbsp;Claude&nbsp;Code.<br>It connects to Comet over the Chrome DevTools Protocol and lets Claude search Perplexity, open pages, read them, click, type and take screenshots.</p>

<p align="center"><a href="#what-it-does">What&nbsp;it&nbsp;does</a>&nbsp;&nbsp; &nbsp;&nbsp;<a href="#install">Install</a>&nbsp;&nbsp; &nbsp;&nbsp;<a href="#usage">Usage</a>&nbsp;&nbsp; &nbsp;&nbsp;<a href="#common-questions">Common&nbsp;questions</a>&nbsp;&nbsp; &nbsp;&nbsp;<a href="#tests">Tests</a>&nbsp;&nbsp; &nbsp;&nbsp;<a href="#license">License</a></p>

## What it does

The server talks to Claude over MCP stdio and to Comet over the Chrome DevTools Protocol (CDP), on port 9222 by default. Each tool acts in your own Comet window.

`comet_search` opens a new tab for each query and returns at once. Perplexity streams the answer in that tab. Claude reads it with `comet_read_page` about 15 to 20 seconds later, or 30 to 45 seconds later in research mode. The server keeps at most 5 search tabs and closes the oldest first.

The results of `comet_search`, `comet_search_finance`, `comet_navigate`, `comet_read_page` and `comet_evaluate` pass through a ContentFilter before Claude sees them. `comet_connect`, `comet_click`, `comet_screenshot` and `comet_tabs` check page titles against the filter's injection patterns and withhold a flagged title. They show URLs as they are. The filter strips hidden characters and HTML comments, scans for 39 prompt-injection patterns and starts the result with a header. The header names the source and its trust tier, or lists the patterns it found. [docs/security.md](docs/security.md) lists the patterns, the tiers and which tools are filtered.

| Tool | What it does |
| --- | --- |
| `comet_connect` | Connects to a running Comet over CDP. Call it first. |
| `comet_search` | Starts a Perplexity search in a new tab, in `search` or `research` mode. |
| `comet_search_finance` | Opens a Perplexity Finance page in the active tab (market, quote, screener, earnings or predictions). |
| `comet_navigate` | Opens a URL in the active tab and returns a text preview. |
| `comet_read_page` | Reads the page text, or only the part a CSS selector matches. |
| `comet_screenshot` | Takes a screenshot and returns it as a base64 PNG. |
| `comet_click` | Clicks an element by CSS selector or by `text=...`. |
| `comet_type` | Types into an input field. |
| `comet_tabs` | Lists, opens, switches or closes tabs. |
| `comet_evaluate` | Runs a JavaScript expression in the page. |
| `comet_wait` | Waits for a selector to appear or for a number of seconds. |
| `comet_security_scan` | Scans the page for hidden elements, HTML comments and injection patterns. |

[docs/tool-reference.md](docs/tool-reference.md) documents every parameter and default.

## When to reach for it

Reach for it when Claude needs a Perplexity answer, a page that only loads in a real browser, or market data from Perplexity Finance. Once the server is configured, Claude picks the tools when a request needs the web. You can also name a tool in the request, for example "use comet_search to look up the latest uv release".

The browsing tools work on any site. Use `comet_security_scan` on a page that looks suspicious before Claude acts on its content.

## Install

**Requirements.** The server needs Perplexity's [Comet](https://perplexity.ai/comet) browser on Windows or macOS, Python 3.10 or newer, and [uv](https://docs.astral.sh/uv/).

**Start Comet with remote debugging.** The server reaches Comet on the CDP port, so Comet must run with `--remote-debugging-port=9222`. Start Comet with one of these commands before you use the server. When Comet is already open without the flag, quit it fully first. The server never starts or closes Comet.

On Windows (PowerShell):

```powershell
& "$env:LOCALAPPDATA\Perplexity\Comet\Application\comet.exe" --remote-debugging-port=9222
```

On macOS:

```bash
/Applications/Comet.app/Contents/MacOS/Comet --remote-debugging-port=9222
```

**Claude Desktop.** Add the server to `claude_desktop_config.json`, then restart Claude Desktop. The file lives at `%APPDATA%\Claude\claude_desktop_config.json` on Windows and `~/Library/Application Support/Claude/claude_desktop_config.json` on macOS.

```json
{
  "mcpServers": {
    "comet": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/AdilShaikh1/comet-mcp-desktop@v0.2.0", "comet-mcp-desktop"]
    }
  }
}
```

**Claude Code.** Run:

```bash
claude mcp add comet -- uvx --from git+https://github.com/AdilShaikh1/comet-mcp-desktop@v0.2.0 comet-mcp-desktop
```

Both configs pin the `v0.2.0` release tag. On first run, uvx installs the server from that tag and resolves its dependencies.

**From source.** Clone the repo and run the server with uv:

```bash
git clone https://github.com/AdilShaikh1/comet-mcp-desktop.git
cd comet-mcp-desktop
uv sync
uv run comet-mcp-desktop
```

The server then waits for an MCP client on stdio. [docs/configuration.md](docs/configuration.md) shows a client config that points at a clone, and it lists the environment variables (`COMET_CDP_URL`, `COMET_TIMEOUT` and `COMET_MAX_CONTENT`).

## Usage

Ask Claude for something on the web. Claude calls `comet_connect` once, then the tools the request needs.

| You say | Claude calls |
| --- | --- |
| "Search Perplexity for the latest AI news" | `comet_search`, then `comet_read_page` once the answer has streamed in |
| "Open Hacker News and summarize the front page" | `comet_navigate`, then `comet_read_page` |
| "Click the first link and read the article" | `comet_click`, then `comet_read_page` |
| "Show me the NVDA quote on Perplexity Finance" | `comet_search_finance` with `mode="quote"` and `ticker="NVDA"`, then `comet_read_page(selector="main")` |
| "Take a screenshot of what you see" | `comet_screenshot` |
| "Is this page safe?" | `comet_security_scan` |

`comet_search_finance` has five modes. The `market`, `quote`, `earnings` and `predictions` pages are ready to read after about 3 to 5 seconds. The `screener` mode types a natural-language query into the Finance screener and submits it. The screener runs Perplexity's Computer feature, so each screener query uses your Perplexity account.

## Common questions

**Does it run on Linux?** No. Comet runs on Windows and macOS, and it has no Linux build.

**Does it need a paid Perplexity plan?** Not for searches and Finance pages, which were tested on a free account. The screener mode was not tested on one.

**What happens if Comet is already open without the flag?** `comet_connect` fails with a tool error that says the CDP URL didn't accept a connection and gives the command that starts Comet with the flag. Quit Comet fully, run that command and call `comet_connect` again. On a managed machine, the `RemoteDebuggingAllowed` policy can block remote debugging.

**The connection dropped mid-session. What now?** Call `comet_connect` again. It reconnects without restarting the server. The search tabs stay open in Comet, but the server stops tracking them.

**`comet_read_page` shows "Searching the web". Is it stuck?** The answer is still streaming. Wait a little longer and call `comet_read_page` again.

**How does it compare with a search API or a browser automation server?** It covers both jobs in one server. `comet_search` hands the query to Perplexity and Claude reads the answer as text. The browsing tools open, click, type and read pages in Comet, and the ContentFilter checks the text the reading tools return.

## It's working if

- `comet_connect` answers `Connected to Comet at http://localhost:9222`, followed by the open tab count and the active page.
- A `comet_search` followed by `comet_read_page` returns an answer.
- Text from a page starts with a `Source: <url> | Trust: <tier>` header, or with a security warning when the filter found an injection pattern.

## Tests

`uv run python test_comet.py` runs 27 static tests with no browser. They cover syntax, tool registration, parameter checks and the ContentFilter.

`uv run python test_comet.py --with-browser` adds the live tier, for 54 tests in total, against a Comet started with `--remote-debugging-port=9222`. When the CDP port doesn't answer, the run records `cdp_connection` as failed and skips the rest of the live tier. The live tests use the Perplexity account Comet is signed in to, and they never submit a Finance screener query.

`--test NAME` runs one test, for example `uv run python test_comet.py --test finance_validation`. Results land in `test_results/`, which git ignores.

## Repository layout

- `comet_mcp.py`: the server and its 12 tools
- `content_filter.py`: the ContentFilter and its injection patterns
- `test_comet.py`: the static and live tests
- `main.py`: a second entry point, `uv run python main.py`
- `docs/`: the tool reference, the security notes and the configuration guide
- `pyproject.toml` and `uv.lock`: the package config and the locked dependencies
- `requirements.txt`: the dependency list in requirements format
- `setup.sh`: runs `uv sync` and prints how to start Comet
- `CHANGELOG.md`: the release notes
- `CONTRIBUTING.md`: how to propose a change
- `README.md`, `LICENSE`, `.gitignore`, `.gitattributes` and `.python-version`: this page, the MIT license and the repo settings

## License

This repo is MIT licensed (see LICENSE). Issues are welcome. Please describe what you asked Claude, what the server returned and what you expected.
