# Configuration

## MCP Server Configuration

### Via uvx (recommended)

Add to your Claude Desktop or Claude Code config:

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

This automatically installs the server and all dependencies on first run.

### Via local development

If running from source, use full paths:

```json
{
  "mcpServers": {
    "comet": {
      "command": "/path/to/comet-mcp-desktop/.venv/Scripts/python.exe",
      "args": ["/path/to/comet-mcp-desktop/comet_mcp.py"],
      "env": {
        "COMET_CDP_URL": "http://localhost:9222",
        "COMET_TIMEOUT": "30000",
        "COMET_MAX_CONTENT": "50000"
      }
    }
  }
}
```

> On macOS/Linux use `.venv/bin/python` instead of `.venv/Scripts/python.exe`.

### Config file locations

| Client | Platform | Path |
|--------|----------|------|
| Claude Desktop | Windows | `%APPDATA%\Claude\claude_desktop_config.json` |
| Claude Desktop | macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Claude Code | Any | `~/.claude.json` or `.mcp.json` in project root |

## Environment Variables

All environment variables are optional. The server works with defaults out of the box.

| Variable | Default | Description |
|----------|---------|-------------|
| `COMET_CDP_URL` | `http://localhost:9222` | CDP endpoint URL. Change if Comet runs on a different port; auto-launch uses this URL's port (9222 if the URL has none). |
| `COMET_TIMEOUT` | `30000` | Operation timeout in milliseconds. Increase for slow connections. |
| `COMET_MAX_CONTENT` | `50000` | Maximum characters extracted from pages. Prevents oversized responses. |
| `COMET_PATH` | auto-detected | Full path to the Comet executable. Checked first, before the auto-detected paths. |

### Setting environment variables

**In MCP config (recommended):**
```json
{
  "mcpServers": {
    "comet": {
      "command": "uvx",
      "args": ["comet-mcp-desktop"],
      "env": {
        "COMET_TIMEOUT": "60000",
        "COMET_MAX_CONTENT": "100000"
      }
    }
  }
}
```

**System-wide (Windows PowerShell):**
```powershell
$env:COMET_PATH = "C:\Custom\Path\comet.exe"
```

**System-wide (macOS/Linux):**
```bash
export COMET_PATH="/custom/path/comet"
```

## Platform Support

| Platform | Auto-detect path | Notes |
|----------|-----------------|-------|
| **Windows** | `%LOCALAPPDATA%\Perplexity\Comet\Application\comet.exe`, `%LOCALAPPDATA%\Perplexity\Comet\comet.exe` (reported, unverified), `%PROGRAMFILES%\Perplexity\Comet\Application\comet.exe` | Fully supported. Probed in this order after `COMET_PATH`. |
| **macOS** | `/Applications/Comet.app/Contents/MacOS/Comet`, `/Applications/Perplexity Comet.app/Contents/MacOS/comet` (reported, unverified) | Supported. Probed in this order after `COMET_PATH`. |
| **Linux** | None | Comet has no Linux build. |

## Parameter Validation

The server validates all tool parameters to prevent misuse:

| Validation | Affected tools | Behavior |
|------------|---------------|----------|
| Enum rejection | `comet_search` (mode), `comet_navigate` (wait_for), `comet_tabs` (action) | Returns error for invalid values |
| Numeric clamping | `comet_click` (wait_after), `comet_wait` (seconds) | Clamped to `[0, 120]` |
| Max length cap | `comet_read_page` (max_length) | Capped at `COMET_MAX_CONTENT` |
| Empty rejection | `comet_search` (query) | Returns error for empty/whitespace queries |
| Finance inputs | `comet_search_finance` (mode, ticker, query) | Returns error for an unknown mode, a missing or malformed ticker (letters, digits, `.`, `-`, `^`, at most 20), or a missing screener query or one over 500 characters |
| Index bounds | `comet_tabs` (tab_index) | Returns error for negative or out-of-range indices |

## Comet Browser Setup

The MCP server launches Comet with `--remote-debugging-port=<port>` (the port of `COMET_CDP_URL`, default 9222) only when Comet is not running and `COMET_CDP_URL` points at this machine. It never closes or kills Comet. If Comet is already running without debugging, quit it fully and restart it with the flag. If auto-launch fails, start Comet manually:

**Windows (PowerShell):**
```powershell
& "$env:LOCALAPPDATA\Perplexity\Comet\Application\comet.exe" --remote-debugging-port=9222
```

**macOS:**
```bash
/Applications/Comet.app/Contents/MacOS/Comet --remote-debugging-port=9222
```

The `RemoteDebuggingAllowed` enterprise policy set to Disabled blocks remote debugging; unset or Enabled allows it.

**Verify CDP is running:**
Open `http://localhost:9222/json` in any browser. You should see a JSON array of browser targets.
