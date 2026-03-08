#!/bin/bash
# Comet MCP Server - Setup Script
# Run this once to install dependencies

set -e

echo "=== Comet MCP Server Setup ==="
echo ""

# Check uv is installed
uv --version 2>/dev/null || { echo "Error: uv is required. Install: https://docs.astral.sh/uv/"; exit 1; }

# Install dependencies from pyproject.toml (uv manages the venv automatically)
echo "1. Installing Python packages..."
uv sync

# Install Playwright's Chromium
echo "2. Installing Playwright browser engine..."
uv run playwright install chromium

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo ""
echo "  1. Launch Comet with remote debugging enabled:"
echo ""
echo "     Windows (PowerShell):"
echo '       & "$env:LOCALAPPDATA\Perplexity\Comet\Application\comet.exe" --remote-debugging-port=9222'
echo ""
echo "     macOS:"
echo "       /Applications/Comet.app/Contents/MacOS/Comet --remote-debugging-port=9222"
echo ""
echo "  2. Add this to your Claude Desktop config (see README.md)"
echo ""
echo "  3. Restart Claude Desktop"
echo ""
