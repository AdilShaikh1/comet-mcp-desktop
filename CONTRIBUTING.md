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
uv run playwright install chromium
```

## Testing

All testing is end-to-end against a live Comet browser instance.

```bash
# Full suite (20 static + 25 browser = 45 tests)
uv run python test_comet.py --with-browser

# Run a specific test
uv run python test_comet.py --with-browser --test tool_comet_search
```

Comet is auto-launched by the test suite. If auto-launch fails, start it manually:

```powershell
& "$env:LOCALAPPDATA\Perplexity\Comet\Application\comet.exe" --remote-debugging-port=9222
```

## Code Guidelines

- **Never hardcode Perplexity CSS selectors** - they break on every UI update
- **Use URL-based search** - `page.goto(f"https://www.perplexity.ai/search?q={quote(query)}")`
- **All tools must be async** with try/except error handling
- **Validate all parameters** - enum rejection, numeric clamping, max_length caps
- **Screenshots use raw CDP** - not Playwright's `page.screenshot()` (hangs on Comet)
- **Use `uv` exclusively** - never pip, conda, or bare python

## Adding Injection Patterns

Add patterns to `INJECTION_PATTERNS` in `content_filter.py`:
- Use `re.compile(r"(?i)...")` for case-insensitive regex
- Always include `\b` word boundaries to minimize false positives
- **Never delete a pattern** - tighten it instead if it causes false positives
