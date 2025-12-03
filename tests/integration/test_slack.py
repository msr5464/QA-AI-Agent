#!/usr/bin/env python3
"""
Test Slack integration with sample data.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.parsers.models import TestSummary
from src.agent.analyzer import FailureClassification
from src.reporters.slack_reporter import SlackReporter


def test_slack_message_format():
    """Test Slack message formatting (without actually sending)"""
    print("=" * 60)
    print("Test 1: Slack Message Format")
    print("=" * 60)
    
    # Create sample data
    summary = TestSummary(
        total=100,
        passed=75,
        failed=25,
        skipped=0,
        errors=0,
        duration_seconds=3600.0
    )
    
    classifications = [
        FailureClassification(
            test_name="TestCheckout.testPaymentProcessing",
            classification="PRODUCT_BUG",
            confidence="HIGH",
            root_cause="API returns 500 error when processing payment",
            recommended_action="Fix payment API endpoint"
        ),
        FailureClassification(
            test_name="TestLogin.testInvalidCredentials",
            classification="AUTOMATION_ISSUE",
            confidence="MEDIUM",
            root_cause="Element not found - login button locator needs update",
            recommended_action="Update element locator in LoginPage"
        ),
        FailureClassification(
            test_name="TestSearch.testProductSearch",
            classification="PRODUCT_BUG",
            confidence="HIGH",
            root_cause="Search returns incorrect results for category filter",
            recommended_action="Review search algorithm"
        )
    ]
    
    recurring = [
        {
            'test_name': 'TestLogin.testInvalidCredentials',
            'occurrences': 5,
            'is_flaky': False
        },
        {
            'test_name': 'TestUI.testButtonClick',
            'occurrences': 4,
            'is_flaky': True
        }
    ]
    
    # Create reporter
    reporter = SlackReporter()
    
    # Build message (don't send)
    message = reporter._build_slack_message(
        summary, classifications, "Regression-AccountOpening-Tests-420",
        recurring, "IMPROVING"
    )
    
    print("\n✅ Slack message formatted successfully")
    print(f"\nMessage structure:")
    print(f"  - Blocks: {len(message['blocks'])}")
    print(f"  - Fallback text: {message['text']}")
    
    # Display formatted message preview
    print(f"\n📱 Message Preview:")
    print(f"  Header: 🤖 AI QA Agent - Regression-AccountOpening-Tests-420")
    print(f"  Status: ⚠️ Good | Pass Rate: 75.0% 📈")
    print(f"  Total: 100 | Passed: 75 | Failed: 25")
    print(f"  Product Bugs: 2 (8%)")
    print(f"  Automation Issues: 1 (4%)")
    print(f"  Recurring Failures: 2")
    
    print("\n✅ Test 1 PASSED\n")
    return True


def test_send_to_slack():
    """Test sending to Slack (requires Bot Token)"""
    print("=" * 60)
    print("Test 2: Send to Slack")
    print("=" * 60)
    
    reporter = SlackReporter()
    
    if not reporter.bot_token or not reporter.channel_id:
        print("\n⚠️  SLACK_BOT_TOKEN or SLACK_CHANNEL not configured in .env")
        print("   To test sending, add your config to config/.env:")
        print("   SLACK_BOT_TOKEN=xoxb-...")
        print("   SLACK_CHANNEL=C...")
        print("\n✅ Test 2 SKIPPED (no token configured)\n")
        return True
    
    # Create sample data
    summary = TestSummary(
        total=73,
        passed=51,
        failed=22,
        skipped=0,
        errors=0,
        duration_seconds=5552.0
    )
    
    classifications = [
        FailureClassification(
            test_name="Automation.Access.AccountOpening.api.dash.TestDashAmlApis.testDoAmlSearchForBusiness",
            classification="PRODUCT_BUG",
            confidence="HIGH",
            root_cause="API returning wrong data - JSON doesn't contain expected keys",
            recommended_action="Fix API response structure"
        ),
        FailureClassification(
            test_name="Automation.Access.AccountOpening.web.customer.TestGlobalSearchFlows.testSearchForUserData",
            classification="AUTOMATION_ISSUE",
            confidence="MEDIUM",
            root_cause="Element click intercepted due to overlapping elements",
            recommended_action="Add wait for element to be clickable"
        )
    ]
    
    # Send to Slack
    print("\n📤 Sending test summary to Slack...")
    success = reporter.send_summary(
        summary, classifications,
        report_name="Test - AI QA Agent",
        trend="IMPROVING"
    )
    
    if success:
        print("✅ Successfully sent to Slack!")
        print("   Check your Slack channel for the message")
    else:
        print("❌ Failed to send to Slack")
        print("   Check your token/channel and try again")
    
    print(f"\n{'✅' if success else '❌'} Test 2 {'PASSED' if success else 'FAILED'}\n")
    return success


def test_simple_message():
    """Test sending a simple message"""
    print("=" * 60)
    print("Test 3: Simple Message")
    print("=" * 60)
    
    reporter = SlackReporter()
    
    if not reporter.bot_token or not reporter.channel_id:
        print("\n⚠️  SLACK_BOT_TOKEN or SLACK_CHANNEL not configured")
        print("\n✅ Test 3 SKIPPED\n")
        return True
    
    print("\n📤 Sending simple test message...")
    success = reporter.send_simple_message(
        "🤖 AI QA Agent is now connected to Slack (via OAuth)! Test message from setup."
    )
    
    if success:
        print("✅ Simple message sent successfully!")
    else:
        print("❌ Failed to send simple message")
    
    print(f"\n{'✅' if success else '❌'} Test 3 {'PASSED' if success else 'FAILED'}\n")
    return success


def main():
    """Run all tests"""
    print("\n" + "=" * 60)
    print("📱 TESTING SLACK INTEGRATION")
    print("=" * 60 + "\n")
    
    results = []
    
    try:
        # Run tests
        results.append(("Message Format", test_slack_message_format()))
        results.append(("Send Summary", test_send_to_slack()))
        results.append(("Simple Message", test_simple_message()))
        
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
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
        print("\n🎉 ALL TESTS PASSED!\n")
        return 0
    else:
        print(f"\n⚠️  {total_tests - total_passed} test(s) failed.\n")
        return 1


if __name__ == '__main__':
    sys.exit(main())
