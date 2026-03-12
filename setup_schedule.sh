#!/bin/bash
# Set up macOS launchd schedule for market data updates
# Runs at EST 9:30am, 12:30pm, 3:30pm, 6:30pm

PLIST_NAME="com.qlib.dashboard.update"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST_NAME}.plist"
PYTHON_BIN="/Users/Ed/qlib-env/bin/python"
SCRIPT="/Users/Ed/qlib/dashboard/scheduled_update.py"
LOG_DIR="/Users/Ed/qlib/dashboard/logs"

mkdir -p "$LOG_DIR"

cat > "$PLIST_PATH" << 'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.qlib.dashboard.update</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/Ed/qlib-env/bin/python</string>
        <string>/Users/Ed/qlib/dashboard/scheduled_update.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <!-- 9:30 AM EST = 14:30 UTC (or 13:30 during DST) -->
        <dict>
            <key>Hour</key>
            <integer>9</integer>
            <key>Minute</key>
            <integer>30</integer>
        </dict>
        <!-- 12:30 PM EST -->
        <dict>
            <key>Hour</key>
            <integer>12</integer>
            <key>Minute</key>
            <integer>30</integer>
        </dict>
        <!-- 3:30 PM EST -->
        <dict>
            <key>Hour</key>
            <integer>15</integer>
            <key>Minute</key>
            <integer>30</integer>
        </dict>
        <!-- 6:30 PM EST -->
        <dict>
            <key>Hour</key>
            <integer>18</integer>
            <key>Minute</key>
            <integer>30</integer>
        </dict>
    </array>
    <key>StandardOutPath</key>
    <string>/Users/Ed/qlib/dashboard/logs/update.log</string>
    <key>StandardErrorPath</key>
    <string>/Users/Ed/qlib/dashboard/logs/update_error.log</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>TZ</key>
        <string>America/New_York</string>
    </dict>
</dict>
</plist>
PLIST

echo "Launch agent created at: $PLIST_PATH"
echo ""
echo "To activate:"
echo "  launchctl load $PLIST_PATH"
echo ""
echo "To deactivate:"
echo "  launchctl unload $PLIST_PATH"
echo ""
echo "To test now:"
echo "  $PYTHON_BIN $SCRIPT"
echo ""
echo "Logs at: $LOG_DIR/"

# Load immediately
launchctl load "$PLIST_PATH" 2>/dev/null
echo "Schedule activated! Updates will run at 9:30am, 12:30pm, 3:30pm, 6:30pm EST."
