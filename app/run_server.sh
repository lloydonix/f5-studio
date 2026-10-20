#!/bin/sh
# Starts the F5 Studio server on 127.0.0.1:$1 (default 8799). F5 Studio.app runs this on launch
# and stops it on quit.
PORT="${1:-8799}"
cd "$HOME/f5-tts/app" || exit 1
export HF_HUB_OFFLINE=1 PATH="/opt/homebrew/bin:$PATH"
exec "$HOME/f5-tts/.venv/bin/python" -m studio.server "$PORT"
