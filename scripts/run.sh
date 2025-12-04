#!/bin/bash
# Unified run script for the AI QA Agent.
# Usage examples:
#   ./scripts/run.sh
#     Runs with default input directory (testdata/Regression-Growth-Tests-442)
#     and output directory (reports).
#
#   ./scripts/run.sh --input-dir testdata/Regression-Smoke-Tests-420 --output-dir custom-reports
#     Runs against a custom input directory with a custom output directory.
#
#   ./scripts/run.sh --table-name results_custom_project
#     Runs with explicit database table name, overriding auto-detection.

set -euo pipefail

# Default arguments when none are provided.
if [ "$#" -eq 0 ]; then
  set -- --input-dir testdata/Regression-Growth-Tests-442 --output-dir reports
fi

# Activate virtual environment and run the agent with the resolved args.
source venv/bin/activate

# Capture output and extract report path
OUTPUT=$(python3 src/main.py "$@" 2>&1)
EXIT_CODE=$?

# Display all output
echo "$OUTPUT"
exit $EXIT_CODE

