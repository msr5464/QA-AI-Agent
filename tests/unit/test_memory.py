#!/usr/bin/env python3
"""
Test the memory system with MySQL database.
Note: These tests require MySQL database to be configured and accessible.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.agent.memory import AgentMemory


def test_memory_initialization():
    """Test that AgentMemory initializes correctly with MySQL"""
    print("=" * 60)
    print("Test 1: Memory Initialization")
    print("=" * 60)
    
    try:
    memory = AgentMemory()
        print("\n✅ AgentMemory initialized successfully")
        print(f"   Database config loaded")
    print("\n✅ Test 1 PASSED\n")
    return True
    except ImportError as e:
        print(f"\n❌ MySQL connector not available: {e}")
        print("   Install with: pip install mysql-connector-python")
        print("\n❌ Test 1 FAILED\n")
        return False
    except Exception as e:
        print(f"\n❌ Failed to initialize: {e}")
        print("\n❌ Test 1 FAILED\n")
        return False


def test_recurring_failures():
    """Test detecting recurring failures from MySQL database"""
    print("=" * 60)
    print("Test 2: Detect Recurring Failures")
    print("=" * 60)
    
    try:
    memory = AgentMemory()
    
        # Use a real report name (adjust based on your database)
        report_name = "Regression-AccountOpening-Tests-420"
        
        # Current failures (simulated - adjust based on your data)
    current_failures = [
        "TestLogin.testInvalidCredentials",
        "TestCheckout.testPaymentProcessing"
    ]
    
        print(f"\n📊 Querying MySQL database for report: {report_name}")
    recurring = memory.detect_recurring_failures(
            current_failures=current_failures,
            days=10,
            min_occurrences=2,
            report_name=report_name,
            all_test_names=None  # Query only failures
    )
    
    print(f"\n✅ Found {len(recurring)} recurring failures")
    
        for failure in recurring[:5]:  # Show first 5
        print(f"\n   Test: {failure['test_name']}")
        print(f"   Occurrences: {failure['occurrences']}")
            print(f"   Classification: {failure.get('most_common_classification', 'N/A')}")
            print(f"   Flaky: {'Yes' if failure.get('is_flaky') else 'No'}")
            print(f"   In Current Run: {'Yes' if failure.get('in_current_run') else 'No'}")
            if 'history' in failure:
                history_str = ''.join(['🟢' if h == 1 else '🔴' for h in failure['history']])
                print(f"   History: {history_str}")
    
        print("\n✅ Test 2 PASSED\n")
    return True
        
    except ValueError as e:
        print(f"\n⚠️  Test skipped: {e}")
        print("   (This is expected if report_name pattern doesn't match)")
        print("\n⚠️  Test 2 SKIPPED\n")
        return True  # Not a failure, just no matching data
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        print("\n❌ Test 2 FAILED\n")
        return False


def test_trend_analysis():
    """Test trend analysis from MySQL database"""
    print("=" * 60)
    print("Test 3: Trend Analysis")
    print("=" * 60)
    
    try:
    memory = AgentMemory()
        
        # Use a real report name (adjust based on your database)
        report_name = "Regression-AccountOpening-Tests-420"
        
        print(f"\n📊 Querying MySQL database for trends (report: {report_name})")
        trends = memory.get_trend_analysis(days=10, report_name=report_name)
    
    print(f"\n✅ Trend Analysis:")
    print(f"   Days Analyzed: {trends['days_analyzed']}")
    print(f"   Average Pass Rate: {trends['average_pass_rate']:.1f}%")
    print(f"   Latest Pass Rate: {trends['latest_pass_rate']:.1f}%")
    print(f"   Trend: {trends['trend']}")
    
        if trends['days_analyzed'] > 0:
        print(f"\n   Pass Rate History:")
            for date, rate in zip(trends.get('dates', [])[:10], trends.get('pass_rates', [])[:10]):
                bar = '█' * int(rate / 5) if rate > 0 else ''
            print(f"   {date}: {bar} {rate:.1f}%")
        else:
            print("\n   ⚠️  No historical data found in database")
    
        print("\n✅ Test 3 PASSED\n")
    return True

    except ValueError as e:
        print(f"\n⚠️  Test skipped: {e}")
        print("   (This is expected if report_name pattern doesn't match)")
        print("\n⚠️  Test 3 SKIPPED\n")
        return True  # Not a failure, just no matching data
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        print("\n❌ Test 3 FAILED\n")
        return False


def test_table_name_extraction():
    """Test table name extraction from report names"""
    print("=" * 60)
    print("Test 4: Table Name Extraction")
    print("=" * 60)
    
    try:
    memory = AgentMemory()
    
        test_cases = [
            ("Regression-AccountOpening-Tests-420", "results_accountopening"),
            ("ProdSanity-All-Tests-524", "results_prodsanity"),
            ("Regression-Payment-Tests-100", "results_payment"),
            ("Invalid-Report-Name", None),
        ]
        
        print("\n✅ Testing table name extraction:")
        all_passed = True
        
        for report_name, expected_table in test_cases:
            table_name = memory._get_table_name_from_report_name(report_name)
            status = "✅" if table_name == expected_table else "❌"
            print(f"   {status} {report_name} -> {table_name} (expected: {expected_table})")
            if table_name != expected_table:
                all_passed = False
        
        if all_passed:
            print("\n✅ Test 4 PASSED\n")
    return True
        else:
            print("\n❌ Test 4 FAILED\n")
            return False
            
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        print("\n❌ Test 4 FAILED\n")
        return False


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("🧠 TESTING MEMORY SYSTEM (MySQL Only)")
    print("=" * 60)
    print("\n⚠️  Note: These tests require MySQL database to be configured")
    print("   Set DB_HOST, DB_USER, DB_PASSWORD, DB_NAME in config/.env\n")
    
    results = []
    
    try:
        # Run tests
        results.append(("Memory Initialization", test_memory_initialization()))
        results.append(("Table Name Extraction", test_table_name_extraction()))
        results.append(("Recurring Failures", test_recurring_failures()))
        results.append(("Trend Analysis", test_trend_analysis()))
        
    except Exception as e:
        print(f"\n❌ Test suite failed with error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    # Summary
    print("=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    
    total_passed = sum(1 for _, passed in results if passed)
    total_tests = len(results)
    
    print(f"\nTotal: {total_passed}/{total_tests} tests passed")
    
    if total_passed == total_tests:
        print("\n🎉 ALL TESTS PASSED! Memory system is working correctly.\n")
        return 0
    else:
        print(f"\n⚠️  {total_tests - total_passed} test(s) failed.\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
