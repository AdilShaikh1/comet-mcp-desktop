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
| `COMET_CDP_URL` | `http://localhost:9222` | CDP endpoint URL. Change if Comet runs on a different port. |
| `COMET_TIMEOUT` | `30000` | Operation timeout in milliseconds. Increase for slow connections. |
| `COMET_MAX_CONTENT` | `50000` | Maximum characters extracted from pages. Prevents oversized responses. |
| `COMET_PATH` | auto-detected | Full path to the Comet executable. Only needed if auto-detection fails. |

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
| **Windows** | `%LOCALAPPDATA%\Perplexity\Comet\Application\comet.exe` | Fully supported. Standard Perplexity install path. |
| **macOS** | `/Applications/Comet.app/Contents/MacOS/Comet` | Supported. Standard Applications folder. |
| **Linux** | None | Set `COMET_PATH` manually to your Comet binary. |

## Parameter Validation

The server validates all tool parameters to prevent misuse:

| Validation | Affected tools | Behavior |
|------------|---------------|----------|
| Enum rejection | `comet_search` (mode), `comet_navigate` (wait_for), `comet_tabs` (action) | Returns error for invalid values |
| Numeric clamping | `comet_search` (wait_seconds), `comet_click` (wait_after), `comet_wait` (seconds) | Clamped to `[0, 120]` |
| Max length cap | `comet_read_page` (max_length) | Capped at `COMET_MAX_CONTENT` |
| Empty rejection | `comet_search` (query) | Returns error for empty/whitespace queries |
| Index bounds | `comet_tabs` (tab_index) | Returns error for negative or out-of-range indices |

## Comet Browser Setup

The MCP server auto-launches Comet with `--remote-debugging-port=9222` when you call `comet_connect`. If auto-launch fails, start Comet manually:

**Windows (PowerShell):**
```powershell
& "$env:LOCALAPPDATA\Perplexity\Comet\Application\comet.exe" --remote-debugging-port=9222
```

**macOS:**
```bash
/Applications/Comet.app/Contents/MacOS/Comet --remote-debugging-port=9222
```

**Verify CDP is running:**
Open `http://localhost:9222/json` in any browser. You should see a JSON array of browser targets.
