#!/bin/bash
# Unified run script for the AI QA Agent.
# Usage examples:
#   ./scripts/run.sh
#     Runs Regression Growth tests with reports stored in
#     testdata/Regression-Growth-Tests-442 and disables Slack notifications.
#
#   ./scripts/run.sh --report-dir testdata/Regression-Smoke-Tests-420 --no-slack
#     Runs against a custom report directory while still silencing Slack.
#
#   ./scripts/run.sh --report-dir testdata/Regression-Load-Tests-420 --slack-channel qa-alerts
#     Runs with a custom report directory and posts to a specific Slack channel.

set -euo pipefail

# Default arguments when none are provided.
if [ "$#" -eq 0 ]; then
  set -- --report-dir testdata/Regression-Growth-Tests-442 --no-slack
fi

# Activate virtual environment and run the agent with the resolved args.
source venv/bin/activate

# Capture output and extract report path
OUTPUT=$(python3 src/main.py "$@" 2>&1)
EXIT_CODE=$?

# Display all output
echo "$OUTPUT"

# Extract and display report path if available
REPORT_PATH=$(echo "$OUTPUT" | grep "^REPORT_PATH=" | cut -d'=' -f2-)
REPORT_URL=$(echo "$OUTPUT" | grep "^REPORT_URL=" | cut -d'=' -f2-)

if [ -n "$REPORT_PATH" ]; then
    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📄 Generated Report:"
    echo "   Path: $REPORT_PATH"
    if [ -n "$REPORT_URL" ]; then
        echo "   URL:  $REPORT_URL"
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
fi

exit $EXIT_CODE

