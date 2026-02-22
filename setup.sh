#!/bin/bash
# Comet MCP Server - Setup Script
# Run this once to install dependencies

set -e

echo "=== Comet MCP Server Setup ==="
echo ""

# Check Python version
python3 --version 2>/dev/null || { echo "Error: Python 3 is required"; exit 1; }

# Create virtual environment
echo "1. Creating virtual environment..."
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
echo "2. Installing Python packages..."
pip install -r requirements.txt

# Install Playwright's Chromium
echo "3. Installing Playwright browser engine..."
playwright install chromium

echo ""
echo "=== Setup Complete ==="
echo ""
echo "Next steps:"
echo ""
echo "  1. Launch Comet with remote debugging enabled:"
echo ""
echo "     macOS:"
echo "       /Applications/Comet.app/Contents/MacOS/Comet --remote-debugging-port=9222"
echo ""
echo "     Windows:"
echo '       "C:\Program Files\Comet\Comet.exe" --remote-debugging-port=9222'
echo ""
echo "  2. Add this to your Claude Desktop config (see README.md)"
echo ""
echo "  3. Restart Claude Desktop"
echo ""
