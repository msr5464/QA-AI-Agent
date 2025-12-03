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
python3 src/main.py "$@"

