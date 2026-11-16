# Contributing

Thanks for your interest in contributing to comet-mcp-desktop!

## How to Contribute

1. **Open an issue first** - Describe the bug or feature you want to work on
2. **Discuss** - Wait for feedback before starting work
3. **Submit a PR** - Reference the issue in your PR

PRs without a related issue may be closed.

## Development

```bash
git clone https://github.com/AdilShaikh1/comet-mcp-desktop.git
cd comet-mcp-desktop
uv sync
```

## Testing

The suite has a static tier that needs no browser and a live tier that runs against Comet.

```bash
# Static tests only (25 tests, no browser)
uv run python test_comet.py

# Static and live tests (52 tests), against a Comet started with the flag
uv run python test_comet.py --with-browser

# Run one test
uv run python test_comet.py --with-browser --test tool_comet_search
```

The test suite doesn't start Comet. Start it with remote debugging before a live run:

```powershell
& "$env:LOCALAPPDATA\Perplexity\Comet\Application\comet.exe" --remote-debugging-port=9222
```

When the CDP port doesn't answer, the run records `cdp_connection` as failed and skips the rest of the live tier. The live tests use the Perplexity account Comet is signed in to, and they never submit a Finance screener query.

## Code Guidelines

- **Never hardcode Perplexity CSS selectors** - they break on every UI update
- **Use URL-based search** - `page.goto(f"https://www.perplexity.ai/search?q={quote(query, safe='')}")`
- **All tools must be async** with try/except error handling
- **Validate all parameters** - enum rejection, numeric clamping, max_length caps
- **Screenshots use raw CDP** - not Playwright's `page.screenshot()` (hangs on Comet)
- **Use `uv` exclusively** - never pip, conda, or bare python

## Adding Injection Patterns

Add patterns to `INJECTION_PATTERNS` in `content_filter.py`:
- Use `re.compile(r"(?i)...")` for case-insensitive regex
- Always include `\b` word boundaries to minimize false positives
- **Never delete a pattern** - tighten it instead if it causes false positives
