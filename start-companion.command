#!/usr/bin/env bash
# ===========================================================================
# Warashi — macOS launcher (double-clickable)
# ---------------------------------------------------------------------------
# Double-click this file in Finder to start your companion.
# The FIRST time, macOS Gatekeeper may block it: right-click the file ->
# "Open" -> "Open" in the dialog. After that, a double-click works.
#
# What it does:
#   1. Makes sure `uv` (the Python package manager) is installed.
#   2. Installs/updates dependencies with `uv sync`.
#   3. Opens your browser to the app.
#   4. Starts the server (run_server.py).
# This is also your DAILY launcher — just run it every time.
# ===========================================================================

set -e

# Always run from the folder this script lives in (the project root).
cd "$(dirname "$0")"

# If anything below fails, show why and keep the window open so you can read it
# (otherwise a double-clicked Terminal window just vanishes on error).
trap 'echo; echo "  Something went wrong — see the messages above."; echo "  If it mentions the network, check your internet and run this again (it resumes where it left off)."; echo; read -r -p "  Press Return to close this window."; exit 1' ERR

APP_URL="http://localhost:12393"

echo "============================================================"
echo "  Warashi — starting up"
echo "============================================================"
echo

# --- 1. Ensure uv is installed -------------------------------------------
if ! command -v uv >/dev/null 2>&1; then
  # uv may be installed but not on this shell's PATH yet.
  if [ -x "$HOME/.local/bin/uv" ]; then
    export PATH="$HOME/.local/bin:$PATH"
  elif [ -x "/opt/homebrew/bin/uv" ]; then
    export PATH="/opt/homebrew/bin:$PATH"
  elif [ -x "/usr/local/bin/uv" ]; then
    export PATH="/usr/local/bin:$PATH"
  fi
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "  'uv' is not installed. Installing it now (one-time)..."
  echo "  (uv is a fast Python package manager from Astral.)"
  echo
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
  else
    echo "  ERROR: 'curl' was not found, so uv can't be auto-installed."
    echo "  Please install uv manually, then run this script again:"
    echo "      https://docs.astral.sh/uv/getting-started/installation/"
    echo
    read -r -p "  Press Return to close this window."
    exit 1
  fi
  # Bring the freshly-installed uv onto PATH for this session.
  export PATH="$HOME/.local/bin:$PATH"
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "  ERROR: uv still isn't available after install."
  echo "  Close this window, open a new Terminal, and run this script again."
  echo "  Or install manually: https://docs.astral.sh/uv/getting-started/installation/"
  echo
  read -r -p "  Press Return to close this window."
  exit 1
fi

echo "  uv found: $(command -v uv)"
echo

# --- 2. Install / update dependencies ------------------------------------
# Provision the project's pinned Python (.python-version = 3.10). uv manages its
# own interpreters, so this works even if the system Python is 3.13+ (which would
# otherwise make 'uv sync' fail with 'no interpreter for >=3.10,<3.13').
echo "  Making sure the right Python (3.10) is available..."
uv python install 3.10 || true
echo
echo "  Installing dependencies (uv sync)..."
echo "  The FIRST run downloads about 2-3 GB and can take 10-40 minutes on a"
echo "  normal connection. Leave this window open; if it stops, just run this"
echo "  file again and it resumes from where it left off."
uv sync
echo "  Dependencies ready."
echo

# --- First run: create conf.yaml from the default template if it's missing ---
if [ ! -f conf.yaml ]; then
  cp config_templates/conf.warashi.default.yaml conf.yaml
  echo "  Created conf.yaml from the default template."
  echo
fi

# --- 3. Start the server (it opens the browser itself once it's READY) ---
# We do NOT open the browser here. run_server.py --open-browser waits until the
# server is actually listening before opening $APP_URL, so a slow first-run
# startup (speech-model download) never shows a "connection refused" page.
echo "============================================================"
echo "  Server starting. Leave THIS WINDOW OPEN while you chat."
echo "  First launch: a small speech model downloads automatically, so the"
echo "  browser may take a minute to open by itself — that is normal."
echo
echo "  If it does not open on its own, browse to $APP_URL manually."
echo
echo "  On first run a setup wizard appears in the browser — paste an"
echo "  API key (OpenAI / Claude / Gemini) OR pick a local Ollama model."
echo
echo "  To quit: close this window (or press Control-C)."
echo "============================================================"
echo
uv run run_server.py --open-browser
