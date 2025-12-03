"""
Slack reporter for posting test summaries to Slack channels.
Uses Thanos bot webhook for notifications.
"""

import os
import logging
from typing import List, Dict, Optional
from datetime import datetime
import requests
from ..parsers.models import TestSummary
from ..agent.analyzer import FailureClassification
from ..settings import Config

logger = logging.getLogger(__name__)


class SlackReporter:
    """Posts test summaries to Slack using Bot User OAuth Token"""
    
    def __init__(self):
        """Initialize Slack reporter with Bot Token and Channel"""
        self.bot_token = os.getenv('SLACK_BOT_TOKEN')
        self.channel_id = os.getenv('SLACK_CHANNEL')
        
        if not self.bot_token:
            logger.warning("SLACK_BOT_TOKEN not configured in .env")
        if not self.channel_id:
            logger.warning("SLACK_CHANNEL not configured in .env")
            
        if self.bot_token and self.channel_id:
            logger.info("✅ SlackReporter initialized with Bot Token")
    
    def send_summary(
        self,
        summary: TestSummary,
        classifications: List[FailureClassification],
        report_name: str = "Test Report",
        recurring_failures: Optional[List[Dict]] = None,
        trend: Optional[str] = None,
        report_url: Optional[str] = None
    ) -> bool:
        """
        Send test summary to Slack.
        
        Args:
            summary: TestSummary with overall statistics
            classifications: List of failure classifications
            report_name: Name of the report
            recurring_failures: Optional list of recurring failures
            trend: Optional trend indicator (IMPROVING, DECLINING, STABLE)
            
        Returns:
            True if sent successfully, False otherwise
        """
        if not self.bot_token or not self.channel_id:
            logger.error("Cannot send to Slack: SLACK_BOT_TOKEN or SLACK_CHANNEL not configured")
            return False
        
        # Build the Slack message
        message_payload = self._build_slack_message(
            summary, classifications, report_name, recurring_failures, trend
        )
        
        # Add channel to payload
        message_payload['channel'] = self.channel_id
        
        try:
            response = requests.post(
                'https://slack.com/api/chat.postMessage',
                json=message_payload,
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {self.bot_token}'
                },
                timeout=10
            )
            
            response_data = response.json()
            
            if response.status_code == 200 and response_data.get('ok'):
                logger.info("✅ Successfully sent summary to Slack")
                return True
            else:
                error_msg = response_data.get('error', 'Unknown error')
                logger.error(f"Failed to send to Slack: {error_msg}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending to Slack: {e}")
            return False
    
    def _build_slack_message(
        self,
        summary: TestSummary,
        classifications: List[FailureClassification],
        report_name: str,
        recurring_failures: Optional[List[Dict]],
        trend: Optional[str],
        report_url: Optional[str] = None
    ) -> Dict:
        """Build Slack message with blocks format"""
        
        # Separate bugs and issues
        product_bugs = [c for c in classifications if c.is_product_bug()]
        automation_issues = [c for c in classifications if c.is_automation_issue()]
        
        # Determine overall status emoji
        if summary.pass_rate >= 90:
            status_emoji = "✅"
            status_text = "Excellent"
        elif summary.pass_rate >= 75:
            status_emoji = "⚠️"
            status_text = "Good"
        elif summary.pass_rate >= 60:
            status_emoji = "🔶"
            status_text = "Fair"
        else:
            status_emoji = "🔴"
            status_text = "Poor"
        
        # Trend emoji
        trend_emoji = ""
        if trend == "IMPROVING":
            trend_emoji = "📈"
        elif trend == "DECLINING":
            trend_emoji = "📉"
        elif trend == "STABLE":
            trend_emoji = "➡️"
        
        # Build message blocks
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"🤖 QA AI Agent - {report_name}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Test Execution Summary* {status_emoji}\n"
                            f"Status: *{status_text}* | Pass Rate: *{summary.pass_rate:.1f}%* {trend_emoji}"
                }
            },
            {
                "type": "divider"
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*Total Tests:*\n{summary.total}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Passed:*\n{summary.passed}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Failed:*\n{summary.failed}"
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Duration:*\n{summary.duration_seconds/60:.1f} min"
                    }
                ]
            }
        ]
        
        # Add AI Analysis section
        blocks.append({
            "type": "divider"
        })
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"*🔍 AI Analysis*\n"
                        f"🐛 Potential Bugs: *{len(product_bugs)}* ({len(product_bugs)/summary.failed*100 if summary.failed > 0 else 0:.0f}%)\n"
                        f"🔧 Automation Issues: *{len(automation_issues)}* ({len(automation_issues)/summary.failed*100 if summary.failed > 0 else 0:.0f}%)"
            }
        })
        
        # Add Potential Bugs section (top 5)
        if product_bugs:
            bugs_text = "*🐛 Potential Bugs*\n"
            for i, bug in enumerate(product_bugs[:5], 1):
                # Shorten test name for readability
                test_name = bug.test_name.split('.')[-1]  # Get just the method name
                bugs_text += f"{i}. 🐛 `{test_name}` - {bug.root_cause[:80]}...\n"
            
            if len(product_bugs) > 5:
                bugs_text += f"\n_+{len(product_bugs) - 5} more issues..._"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": bugs_text
                }
            })
        
        # Add Automation Issues section (top 5)
        if automation_issues:
            issues_text = "*🔧 Automation Issues*\n"
            for i, issue in enumerate(automation_issues[:5], 1):
                test_name = issue.test_name.split('.')[-1]
                issues_text += f"{i}. `{test_name}` - {issue.root_cause[:80]}...\n"
            
            if len(automation_issues) > 5:
                issues_text += f"\n_+{len(automation_issues) - 5} more issues..._"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": issues_text
                }
            })
        
        # Add Recurring Failures section
        if recurring_failures and len(recurring_failures) > 0:
            blocks.append({
                "type": "divider"
            })
            
            recurring_text = "*⚠️ Flaky Tests* (3+ occurrences)\n"
            for failure in recurring_failures[:3]:  # Top 3
                test_name = failure['test_name'].split('.')[-1]
                recurring_text += f"• `{test_name}` - {failure['occurrences']}x"
                if failure['is_flaky']:
                    recurring_text += " 🔄 _FLAKY_"
                recurring_text += "\n"
            
            blocks.append({
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": recurring_text
                }
            })
        
        # Add footer
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"Generated by QA AI Agent | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                }
            ]
        })
        
        return {
            "blocks": blocks,
            "text": f"Test Report: {report_name} - Pass Rate: {summary.pass_rate:.1f}%"  # Fallback text
        }
