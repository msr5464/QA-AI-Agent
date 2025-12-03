"""
Test script for HTML parser.
Validates that we can extract complete execution logs from HTML reports.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent / 'src'))

from parsers.html_parser import HTMLReportParser
from parsers.report_aggregator import aggregate_test_results

def test_html_parser():
    """Test HTML parsing functionality"""
    
    print("=" * 60)
    print("Testing HTML Report Parser")
    print("=" * 60)
    
    # Test data directory
    report_dir = "data/input/Regression-AccountOpening-Tests-420"
    html_dir = f"{report_dir}/html"
    
    parser = HTMLReportParser()
    
    # Test 1: Parse overview.html
    print("\n1. Testing overview.html parsing...")
    overview_path = f"{html_dir}/overview.html"
    test_suites = parser.parse_overview(overview_path)
    
    print(f"   ✅ Found {len(test_suites)} test suites")
    for suite in test_suites[:3]:
        print(f"      - {suite['name']}: {suite['failed']} failed, {suite['passed']} passed")
    
    # Test 2: Parse a failed test suite
    print("\n2. Testing individual test result parsing...")
    failed_suite = next((s for s in test_suites if s['failed'] > 0), None)
    
    if failed_suite:
        results_file = f"{html_dir}/{failed_suite['results_file']}"
        print(f"   Parsing: {failed_suite['name']}")
        
        results = parser.parse_test_results(results_file)
        print(f"   ✅ Parsed {len(results)} test results")
        
        # Find a failed test
        failed_test = next((r for r in results if r.is_failure), None)
        
        if failed_test:
            print(f"\n3. Examining failed test: {failed_test.method_name}")
            print(f"   Status: {failed_test.status.value}")
            print(f"   Platform: {failed_test.platform}")
            print(f"   Error Type: {failed_test.error_type}")
            print(f"   Error Message: {failed_test.error_message[:100]}..." if failed_test.error_message else "   Error Message: None")
            
            if failed_test.execution_log:
                print(f"\n   📋 Execution Log Preview (first 500 chars):")
                print(f"   {'-' * 56}")
                log_preview = failed_test.execution_log[:500].replace('\n', '\n   ')
                print(f"   {log_preview}")
                print(f"   {'-' * 56}")
                print(f"   Total log length: {len(failed_test.execution_log)} characters")
                
                # Check for API details
                if 'POST' in failed_test.execution_log or 'GET' in failed_test.execution_log:
                    print(f"   ✅ Contains API call details")
                if 'Response Code' in failed_test.execution_log:
                    print(f"   ✅ Contains response codes")
                if 'Api Response' in failed_test.execution_log:
                    print(f"   ✅ Contains API responses")
            else:
                print(f"   ⚠️  No execution log found")
    
    # Test 3: Use report aggregator
    print(f"\n4. Testing report aggregator...")
    all_results = aggregate_test_results(report_dir)
    print(f"   ✅ Aggregated {len(all_results)} total test results")
    
    failures = [r for r in all_results if r.is_failure]
    print(f"   Found {len(failures)} failures")
    
    # Check how many have execution logs
    with_logs = sum(1 for f in failures if f.execution_log)
    print(f"   {with_logs}/{len(failures)} failures have execution logs")
    
    print("\n" + "=" * 60)
    print("✅ HTML Parser Test Complete!")
    print("=" * 60)

if __name__ == "__main__":
    test_html_parser()
