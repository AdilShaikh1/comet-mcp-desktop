# Changelog

## Unreleased

- `comet_connect`, `comet_screenshot`, `comet_click` and `comet_tabs` check page titles against the filter's injection patterns and withhold a flagged title. URLs are shown as they are. (#8)

## 0.2.0 (2026-11-16)

The first tagged release. It ships 12 tools. The council tools were left out of this release.

- A set of fixes landed on main before the pull requests below. `comet_navigate` and `comet_read_page` filter the page title, `comet_evaluate` filters object and list results, queries with a slash are encoded, `comet_wait(seconds=0)` and `comet_screenshot(full_page=True)` work, and a strikethrough false positive in the injection patterns is gone. (e2818a4)
- The package runs on Python 3.10 or newer, shell and Python scripts keep LF line endings, and setup no longer downloads Playwright's Chromium. (#2)
- Shared helpers now handle errors and content filtering in the server, and the `mcp` dependency is pinned below 2. (#3)
- `comet_search` opens a new tab and returns at once, and `comet_read_page` reads the answer later. It keeps at most 5 search tabs, accepts Perplexity session redirects and no longer takes a wait parameter. (#4)
- The server never kills Comet. It starts Comet only when Comet isn't running and the CDP URL is local, it uses the port from `COMET_CDP_URL`, and its errors say why CDP didn't answer. (#5)
- `comet_search_finance` opens Perplexity Finance pages for market data, quotes, the screener, earnings and prediction markets. (#6)

0.1.0 was the earlier packaging work, and it was never released. (#1)
