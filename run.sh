#!/bin/bash
# Unified run script for the AI QA Agent.
# Usage examples:
#   ./run_analyser.sh
#     Runs Regression Growth tests with reports stored in
#     data/input/Regression-Growth-Tests-442 and disables Slack notifications.
#
#   ./run_analyser.sh --report-dir data/input/Smoke --no-slack
#     Runs against a custom report directory while still silencing Slack.
#
#   ./run_analyser.sh --report-dir data/input/Load --slack-channel qa-alerts
#     Runs with a custom report directory and posts to a specific Slack channel.

set -euo pipefail

# Default arguments when none are provided.
if [ "$#" -eq 0 ]; then
  set -- --report-dir data/input/Regression-Growth-Tests-442 --no-slack
fi

# Activate virtual environment and run the agent with the resolved args.
source venv/bin/activate
python3 src/main.py "$@"

