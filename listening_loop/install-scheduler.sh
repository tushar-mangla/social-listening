#!/usr/bin/env bash
# ==============================================================================
# Dynamic Launchd / Cron Setup for Social Listening Loop
# ==============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$HERE/.." && pwd)"
PYTHON_EXE="$PROJECT_ROOT/venv/bin/python"
BASH_EXE="$(which bash)"

if [[ ! -x "$PYTHON_EXE" ]]; then
  echo "Error: expected virtual-environment Python at $PYTHON_EXE" >&2
  echo "Create it with: python3 -m venv $PROJECT_ROOT/venv" >&2
  exit 1
fi

echo "=== Social Listening Scheduler Setup ==="
echo "Project Directory: $HERE"
echo "Python Executable: $PYTHON_EXE"
echo ""

if [[ "$OSTYPE" == "darwin"* ]]; then
  echo "Detected macOS. Installing launchd plists to ~/Library/LaunchAgents..."
  mkdir -p "$HOME/Library/LaunchAgents"

  mkdir -p "$PROJECT_ROOT/logs"

  # Digest plist (every 3h = 10800s)
  DIGEST_PLIST="$HOME/Library/LaunchAgents/com.social-listening.digest.plist"
  cat <<EOF > "$DIGEST_PLIST"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.social-listening.digest</string>
  <key>ProgramArguments</key><array>
    <string>$BASH_EXE</string>
    <string>$HERE/run.sh</string>
  </array>
  <key>StartInterval</key><integer>10800</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>$PROJECT_ROOT/logs/launchd.log</string>
  <key>StandardErrorPath</key><string>$PROJECT_ROOT/logs/launchd.log</string>
</dict>
</plist>
EOF

  launchctl unload "$DIGEST_PLIST" 2>/dev/null || true
  launchctl load "$DIGEST_PLIST"
  echo "✅ OpenCLI lead scheduler loaded successfully!"
  echo "Check logs with: tail -f $PROJECT_ROOT/logs/launchd.log"

else
  echo "Detected Linux / Unix. Add the following to your crontab (crontab -e):"
  echo ""
  echo "0 */3 * * * $BASH_EXE $HERE/run.sh >> $HERE/data/cron.log 2>&1"
  echo ""
fi
