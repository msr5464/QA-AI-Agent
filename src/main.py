"""
Main Orchestrator for the QA AI Agent.
Ties together Parser, Analyzer, Memory, and Reporters.
"""

import os
import sys
import logging
import argparse
import warnings
from pathlib import Path

# Suppress ALL warnings from urllib3 BEFORE importing anything
import urllib3
urllib3.disable_warnings(urllib3.exceptions.NotOpenSSLWarning)
warnings.filterwarnings("ignore", message=".*urllib3.*")
warnings.filterwarnings("ignore", message=".*OpenSSL.*")
warnings.filterwarnings("ignore", category=UserWarning, module="urllib3")

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import config to ensure environment variables are loaded
from src.settings import Config

from src.parsers.data_builder import (
    find_latest_report,
    get_full_report_data_from_db,
    get_execution_logs_from_html,
    get_test_durations_from_html
)
from src.agent.analyzer import TestAnalyzer
from src.agent.summary_generator import SummaryGenerator
from src.agent.memory import AgentMemory
from src.reporters.slack_reporter import SlackReporter
from src.reporters.report_generator import ReportGenerator

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format=Config.LOG_FORMAT,
    handlers=[
        logging.FileHandler(Config.LOG_FILE_NAME),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("Orchestrator")

def main():
    """Run the QA AI Agent workflow"""
    
    parser = argparse.ArgumentParser(description="QA AI Agent")
    parser.add_argument("--report-dir", help="Path to specific report directory")
    parser.add_argument("--no-slack", action="store_true", help="Disable Slack reporting")
    args = parser.parse_args()
    
    logger.info("🚀 Starting QA AI Agent...")
    
    # 1. Locate Report
    report_dir = args.report_dir
    if not report_dir:
        logger.info(f"Looking for reports in {Config.INPUT_DIR}...")
        report_dir = find_latest_report(Config.INPUT_DIR)
    
    if not report_dir:
        logger.error("❌ No reports found! Exiting.")
        return
        
    logger.info(f"📂 Processing report: {report_dir}")
    report_name = Path(report_dir).name
    
    # Extract buildTag from report name (folder name is the buildTag)
    build_tag = report_name
    
    # 2. Query Database for Test Results
    logger.info("💾 Querying database for test results...")
    memory = AgentMemory()
    
    try:
        db_results = memory.get_test_results_by_buildtag(report_name, build_tag)
        if not db_results:
            logger.error(f"❌ No test results found in database for buildTag: {build_tag}")
            logger.error("   Make sure the test results have been inserted into the database first.")
            return
        
        logger.info(f"📊 Found {len(db_results)} test results in database")
        
    except Exception as e:
        logger.error(f"Failed to query database: {e}")
        return
    
    # 3. Calculate Flaky Tests (using database)
    logger.info("🔍 Calculating flaky tests from database...")
    all_test_names_from_db = [row.get('testcaseName', '') for row in db_results if row.get('testcaseName')]
    current_failure_names = [
        row.get('testcaseName', '') for row in db_results 
        if row.get('testStatus', '').upper() in ['FAIL', 'FAILED', 'ERROR', 'ERRORED']
    ]
    
    recurring = memory.detect_recurring_failures(
        current_failure_names,
        days=Config.FLAKY_TESTS_LAST_RUNS,
        min_occurrences=Config.FLAKY_TESTS_MIN_FAILURES,
        report_name=report_name,
        all_test_names=all_test_names_from_db
    )
    
    trends = memory.get_trend_analysis(days=10, report_name=report_name)
    
    if recurring:
        logger.info(f"⚠️ Detected {len(recurring)} recurring failures")
    logger.info(f"📈 Trend: {trends['trend']} (Avg Pass Rate: {trends['average_pass_rate']:.1f}%)")
    
    # 4. Parse HTML for Execution Logs Only
    logger.info("📄 Extracting execution logs from HTML...")
    execution_logs, html_links = get_execution_logs_from_html(report_dir)
    durations = get_test_durations_from_html(report_dir)
    logger.info(f"📝 Extracted execution logs for {len(execution_logs)} tests")
    
    # 5. Merge DB Data + HTML Logs
    logger.info("🔄 Merging database results with HTML execution logs...")
    try:
        data = get_full_report_data_from_db(report_dir, db_results, execution_logs, durations, html_links)
        summary = data['summary']
        failures = [r for r in data['test_results'] if r.is_failure]
        
        logger.info(f"📊 Total tests: {summary.total}. Pass Rate: {summary.pass_rate:.1f}%")
        logger.info(f"❌ Found {len(failures)} failures")
        
    except Exception as e:
        logger.error(f"Failed to merge data: {e}")
        return

    # 3. AI Analysis
    classifications = []
    if failures:
        # Deduplicate failures by full_name before classification
        # A test might appear in multiple test suites
        seen_failures = {}
        deduplicated_failures = []
        for failure in failures:
            test_key = failure.full_name
            if test_key not in seen_failures:
                seen_failures[test_key] = failure
                deduplicated_failures.append(failure)
            else:
                # Prefer the one with execution_log or FAIL status
                existing = seen_failures[test_key]
                if failure.execution_log and not existing.execution_log:
                    deduplicated_failures.remove(existing)
                    deduplicated_failures.append(failure)
                    seen_failures[test_key] = failure
                    logger.debug(f"Replaced duplicate {test_key} with version that has execution_log")
                elif failure.status.value in ['FAIL', 'ERROR'] and existing.status.value not in ['FAIL', 'ERROR']:
                    deduplicated_failures.remove(existing)
                    deduplicated_failures.append(failure)
                    seen_failures[test_key] = failure
                    logger.debug(f"Replaced duplicate {test_key} with FAIL status")
        
        if len(failures) != len(deduplicated_failures):
            logger.info(f"⚠️ Deduplicated failures: {len(failures)} -> {len(deduplicated_failures)} (removed {len(failures) - len(deduplicated_failures)} duplicates)")
        
        logger.info("🤖 Starting AI Analysis...")
        analyzer = TestAnalyzer()
        classifications = analyzer.classify_multiple_failures(deduplicated_failures)
    else:
        logger.info("🎉 No failures to analyze!")

    # Filter recurring failures to only show those that match current test structure
    if recurring and data.get('test_results'):
        all_current_test_names = {t.full_name for t in data['test_results']}
        current_test_patterns = set()
        for t in data['test_results']:
            parts = t.full_name.split('.')
            if len(parts) >= 2:
                current_test_patterns.add('.'.join(parts[-2:]))  # ClassName.methodName
        
        filtered_recurring = []
        for r in recurring:
            test_name = r['test_name']
            parts = test_name.split('.')
            test_pattern = '.'.join(parts[-2:]) if len(parts) >= 2 else test_name
            
            if (r['in_current_run'] or 
                test_name in all_current_test_names or 
                test_pattern in current_test_patterns):
                filtered_recurring.append(r)
            else:
                logger.debug(f"Filtered out recurring failure (no match): {test_name}")
        
        recurring = filtered_recurring
        logger.info(f"After filtering: {len(recurring)} recurring failures match current tests")

    # 5. Extract API endpoints map BEFORE generating summary (same method as tables)
    logger.info("🔍 Extracting API endpoints map...")
    report_gen = ReportGenerator()
    # Create cache for consistent data access
    from src.utils import TestDataCache
    test_data_cache = TestDataCache(data['test_results'], data.get('html_links', {}))
    test_api_map = report_gen.extract_test_api_map(classifications, test_data_cache)
    logger.info(f"📊 Found API endpoints for {len(test_api_map)} tests")
    
    # 5.5. Calculate category breakdown for Executive Summary (same logic as report generator)
    from src.reporters.category_rules import CategoryRuleEngine
    rule_engine = CategoryRuleEngine()
    category_counts = {}
    category_failures = {}
    
    # Deduplicate classifications first (same as report generator)
    seen_tests = {}
    deduplicated_classifications = []
    for classification in classifications:
        test_name_normalized = classification.test_name.strip()
        if test_name_normalized not in seen_tests:
            seen_tests[test_name_normalized] = classification
            deduplicated_classifications.append(classification)
    
    for failure in deduplicated_classifications:
        category = rule_engine.classify(failure, test_data_cache)
        if category not in category_counts:
            category_counts[category] = 0
            category_failures[category] = []
        category_counts[category] += 1
        category_failures[category].append(failure)
    
    logger.info(f"📊 Category breakdown: {category_counts}")
    
    # 6. Generate Summary
    logger.info("📝 Generating Executive Summary...")
    generator = SummaryGenerator()
    ai_summary = generator.generate_executive_summary(
        summary=summary,
        classifications=deduplicated_classifications,
        report_name=report_name,
        category_counts=category_counts,
        category_failures=category_failures,
        recurring_failures=recurring,
        test_html_links=data.get('html_links', {}),
        test_results=data.get('test_results')
    )

    # 7. Generate HTML Report
    logger.info("🎨 Generating HTML Report...")
    html_content, _ = report_gen.generate_html_report(
        summary=summary,
        classifications=classifications,
        report_name=report_name,
        ai_summary=ai_summary,
        recurring_failures=recurring,
        trend=trends['trend'],
        report_dir=report_dir,
        test_results=data['test_results'],
        test_html_links=data.get('html_links', {})
    )
    
    # Save HTML report with dynamic name based on report_name
    # Sanitize report_name for filename (remove invalid characters)
    safe_report_name = "".join(c for c in report_name if c.isalnum() or c in ('-', '_', ' ')).strip().replace(' ', '-')
    html_report_path = Path(Config.OUTPUT_DIR) / f"AI-Analysis-Report_{safe_report_name}.html"
    saved_path = report_gen.save_report(html_content, str(html_report_path))
    logger.info(f"📄 HTML report saved to: {saved_path}")

    # 8. Send to Slack with report link
    if not args.no_slack:
        logger.info("📱 Sending to Slack...")
        slack = SlackReporter()
        # Create a link to the report (you may need to adjust this URL based on your hosting)
        report_url = f"file://{saved_path}"  # For local files, or use a web server URL
        if slack.send_summary(summary, classifications, report_name, recurring, trends['trend'], report_url):
            logger.info("✅ Slack notification sent")
        else:
            logger.warning("⚠️ Failed to send Slack notification")

    logger.info("🎉 QA AI Agent finished successfully!")

if __name__ == "__main__":
    main()
