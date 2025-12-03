"""
Summary generator for test results.
Creates executive summaries and detailed reports.
"""

import logging
import html as html_escape
import re
from typing import List, Dict, Optional
from langchain_ollama import OllamaLLM

from ..parsers.models import TestSummary
from .analyzer import FailureClassification
from ..utils import remove_duplicate_class_name, normalize_root_cause
from ..settings import Config
# Constants are now in Config class

logger = logging.getLogger(__name__)


class SummaryGenerator:
    """Generates executive summaries of test results"""
    
    
    def __init__(self):
        """Initialize the summary generator with Ollama LLM"""
        self.model = Config.OLLAMA_MODEL
        self.base_url = Config.OLLAMA_BASE_URL
        
        logger.info(f"Initializing SummaryGenerator with model: {self.model}")
        
        try:
            self.llm = OllamaLLM(
                model=self.model,
                base_url=self.base_url,
                temperature=0.5  # Slightly higher for more creative summaries
            )
            logger.info("✅ Ollama LLM initialized for summary generation")
        except Exception as e:
            logger.error(f"Failed to initialize Ollama: {e}")
            raise
    
    def generate_executive_summary(
        self,
        summary: TestSummary,
        classifications: List[FailureClassification],
        report_name: str = "Test Report",
        category_counts: Optional[Dict[str, int]] = None,
        category_failures: Optional[Dict[str, List[FailureClassification]]] = None,
        recurring_failures: Optional[List[Dict]] = None,
        test_html_links: Optional[Dict[str, str]] = None,
        test_results: Optional[List] = None
    ) -> str:
        """
        Generate an HTML-formatted executive summary of test results with insights.
        
        Args:
            summary: TestSummary with overall statistics
            classifications: List of failure classifications
            report_name: Name of the report
            category_counts: Dictionary mapping category names to failure counts
            category_failures: Dictionary mapping category names to failure lists
            recurring_failures: List of recurring/flaky test failures
            
        Returns:
            HTML-formatted executive summary string
        """
        logger.info("Generating executive summary...")
        
        # Generate HTML-formatted summary with insights
        html_summary = self._generate_html_executive_summary(
            summary,
            category_counts=category_counts,
            category_failures=category_failures,
            recurring_failures=recurring_failures,
            test_html_links=test_html_links,
            test_results=test_results
        )
        
        logger.info("✅ Executive summary generated")
        return html_summary
    
    def _identify_common_root_causes(self, category_failures: Dict[str, List[FailureClassification]]) -> Dict[str, Dict]:
        """
        Identify root causes that affect multiple tests.
        Groups failures by normalized root cause to find common issues.
        
        Args:
            category_failures: Dictionary mapping category to list of FailureClassification objects
            
        Returns:
            Dictionary mapping normalized root cause to:
            {
                'root_cause': original root cause text (from first occurrence),
                'tests': list of test names affected,
                'category': root cause category
            }
        """
        common_causes = {}
        
        # Iterate through all failures across all categories
        for category, failures in category_failures.items():
            for failure in failures:
                if not failure.root_cause:
                    continue
                
                # Normalize the root cause to group similar issues
                normalized_rc = normalize_root_cause(failure.root_cause)
                
                if not normalized_rc:
                    continue
                
                # Group by normalized root cause
                if normalized_rc not in common_causes:
                    common_causes[normalized_rc] = {
                        'root_cause': failure.root_cause,  # Keep original for display
                        'tests': [],
                        'category': failure.root_cause_category
                    }
                
                # Add test name if not already present
                if failure.test_name not in common_causes[normalized_rc]['tests']:
                    common_causes[normalized_rc]['tests'].append(failure.test_name)
        
        # Filter to only include root causes affecting 2+ tests
        return {rc: data for rc, data in common_causes.items() if len(data['tests']) >= 2}
    
    def _generate_html_executive_summary(
        self,
        summary: TestSummary,
        category_counts: Optional[Dict[str, int]] = None,
        category_failures: Optional[Dict[str, List[FailureClassification]]] = None,
        recurring_failures: Optional[List[Dict]] = None,
        test_html_links: Optional[Dict[str, str]] = None,
        test_results: Optional[List] = None
    ) -> str:
        """Generate HTML-formatted executive summary aligned with Root Cause Categories and Flaky Tests sections"""
        
        html = []
        
        # Category styles matching Root Cause Categories section (used across multiple sections)
        category_styles = {
            'ELEMENT_NOT_FOUND': {'icon': '🔍', 'label': 'Element Locator Issues', 'color': '#f97316'},
            'TIMEOUT': {'icon': '⏱️', 'label': 'Page Load Timeout Issues', 'color': '#facc15'},
            'ASSERTION_FAILURE': {'icon': '❌', 'label': 'Assertion Mismatch Issues', 'color': '#dc2626'},
            'ENVIRONMENT_ISSUE': {'icon': '🏗️', 'label': 'Environment Issues', 'color': '#8b5cf6'},
            'OTHER': {'icon': '❓', 'label': 'Miscellaneous Issues', 'color': '#475569'}
        }
        
        # Note: Test Execution Overview removed - Dashboard at top already shows this information
        
        # 1. Failure Breakdown by Category (aligned with Root Cause Categories section)
        if category_counts and category_failures:
            html.append('<div style="margin-bottom: 15px;">')
            html.append('<h3 style="color: #2c3e50; margin-bottom: 8px; font-size: 16px; border-bottom: 2px solid #6610f2; padding-bottom: 6px; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">🧩 Failure Breakdown by Category</h3>')
            html.append('<p style="margin-bottom: 8px; color: #666; font-size: 15px; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">Failures grouped by root cause type. <a href="#root-cause-categories" style="color: #6366f1; text-decoration: none;">View detailed breakdown →</a></p>')
            
            total_failures = sum(category_counts.values())
            if total_failures > 0:
                # Sort categories by count (descending)
                sorted_categories = sorted(category_counts.items(), key=lambda x: x[1], reverse=True)
                
                # Calculate dynamic chart size based on number of categories
                num_categories = len(sorted_categories)
                # Scale chart size based on number of categories to accommodate all items
                if num_categories <= 2:
                    chart_size = 100
                elif num_categories <= 3:
                    chart_size = 120
                elif num_categories <= 5:
                    chart_size = 140  # Increased for 4-5 categories
                elif num_categories <= 8:
                    chart_size = 160
                elif num_categories <= 12:
                    chart_size = 180
                else:
                    chart_size = 200
                
                # Calculate radii maintaining proportions
                center_x = chart_size / 2
                center_y = chart_size / 2
                outer_radius = chart_size / 2
                inner_radius = outer_radius * 0.75  # Maintain 75% ratio for donut thickness
                
                # Calculate font sizes proportionally
                center_font_size = int(chart_size * 0.167)  # ~20px for 120px chart
                center_label_font_size = int(chart_size * 0.083)  # ~10px for 120px chart
                
                # Create a donut chart visualization with category details
                html.append('<div style="background: #fff; padding: 12px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">')
                html.append('<div style="display: grid; grid-template-columns: auto 1fr; gap: 18px; align-items: center;">')
                
                # Left side: Full circle donut chart using SVG paths
                
                html.append(f'<div style="position: relative; width: {chart_size}px; height: {chart_size}px; flex-shrink: 0;">')
                html.append(f'<svg width="{chart_size}" height="{chart_size}" viewBox="0 0 {chart_size} {chart_size}">')
                
                # Calculate segments for full circle donut chart using path arcs
                import math
                chart_segments = []
                current_angle = -90  # Start from top (12 o'clock)
                
                for category_key, count in sorted_categories:  # Use all categories for full circle
                    percentage = (count / total_failures) * 100
                    style = category_styles.get(category_key, {
                        'icon': '❓',
                        'label': category_key.replace('_', ' ').title(),
                        'color': '#6c757d'
                    })
                    
                    # Calculate angle for this segment
                    angle = (percentage / 100) * 360
                    start_angle = current_angle
                    end_angle = current_angle + angle
                    
                    # Convert angles to radians
                    start_rad = math.radians(start_angle)
                    end_rad = math.radians(end_angle)
                    
                    # Calculate arc coordinates
                    x1 = center_x + outer_radius * math.cos(start_rad)
                    y1 = center_y + outer_radius * math.sin(start_rad)
                    x2 = center_x + outer_radius * math.cos(end_rad)
                    y2 = center_y + outer_radius * math.sin(end_rad)
                    
                    x3 = center_x + inner_radius * math.cos(end_rad)
                    y3 = center_y + inner_radius * math.sin(end_rad)
                    x4 = center_x + inner_radius * math.cos(start_rad)
                    y4 = center_y + inner_radius * math.sin(start_rad)
                    
                    # Large arc flag (1 if angle > 180, 0 otherwise)
                    large_arc = 1 if angle > 180 else 0
                    
                    # Create path for donut segment
                    path_d = f"M {x1} {y1} A {outer_radius} {outer_radius} 0 {large_arc} 1 {x2} {y2} L {x3} {y3} A {inner_radius} {inner_radius} 0 {large_arc} 0 {x4} {y4} Z"
                    
                    segment_id = f"donut-segment-{len(chart_segments)}"
                    chart_segments.append({
                        'category_key': category_key,
                        'count': count,
                        'percentage': percentage,
                        'style': style,
                        'path_d': path_d,
                        'segment_id': segment_id
                    })
                    
                    # Escape HTML for tooltip content
                    label_escaped = html_escape.escape(style['label'])
                    icon_escaped = html_escape.escape(style['icon'])
                    
                    html.append(f'''
                        <path
                            id="{segment_id}"
                            d="{path_d}"
                            fill="{style['color']}"
                            stroke="none"
                            style="cursor: pointer; transition: opacity 0.2s;"
                            onmouseover="showDonutTooltip(event, '{segment_id}', '{label_escaped}', '{icon_escaped}', {count}, {percentage:.1f}, '{style['color']}')"
                            onmouseout="hideDonutTooltip('{segment_id}')"
                            onmousemove="updateDonutTooltipPosition(event)"
                        />
                    ''')
                    
                    # Move to next segment
                    current_angle = end_angle
                
                html.append('</svg>')
                
                # Center text showing total (with dynamic font sizes)
                html.append(f'''
                    <div style="position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); text-align: center;">
                        <div style="font-size: {center_font_size}px; font-weight: 700; color: #111827;">{total_failures}</div>
                        <div style="font-size: {center_label_font_size}px; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px;">Total</div>
                    </div>
                ''')
                
                # Tooltip will be created dynamically in JavaScript
                html.append('</div>')
                
                # Right side: Legend with details
                html.append('<div style="display: flex; flex-direction: column; gap: 8px; min-width: 0;">')
                
                for segment in chart_segments:  # Show all categories in detail
                    category_key = segment['category_key']
                    count = segment['count']
                    percentage = segment['percentage']
                    style = segment['style']
                    
                    html.append(f'''
                        <div style="display: flex; align-items: center; gap: 10px; padding: 8px; border-radius: 6px; transition: background 0.2s;" onmouseover="this.style.background='#f9fafb'" onmouseout="this.style.background='transparent'">
                            <div style="display: flex; align-items: center; gap: 8px; flex: 1; min-width: 0;">
                                <div style="width: 14px; height: 14px; border-radius: 4px; background: {style['color']}; flex-shrink: 0;"></div>
                                <div style="flex: 1; min-width: 0;">
                                    <div style="display: flex; align-items: center; gap: 5px;">
                                        <span style="font-size: 13px;">{style['icon']}</span>
                                        <span style="font-size: 12px; color: #374151; font-weight: 500; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">{style['label']}</span>
                                    </div>
                                </div>
                            </div>
                            <div style="display: flex; align-items: baseline; gap: 6px; flex-shrink: 0;">
                                <span style="font-size: 14px; font-weight: 600; color: #111827;">{count}</span>
                                <span style="font-size: 11px; color: #6b7280;">({percentage:.1f}%)</span>
                            </div>
                        </div>
                    ''')
                
                html.append('</div>')
                html.append('</div>')
                html.append('</div>')
            
            html.append('</div>')
        
        # 2. Flaky Tests Summary (statistical overview)
        if recurring_failures:
            html.append('<div style="margin-bottom: 15px;">')
            html.append('<h3 style="color: #2c3e50; margin-bottom: 8px; font-size: 16px; border-bottom: 2px solid #6c757d; padding-bottom: 6px; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">⚠️ Flaky Tests</h3>')
            
            total_flaky = len(recurring_failures)
            html.append(f'<p style="margin-bottom: 8px; color: #666; font-size: 15px; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">{total_flaky} flaky test{"" if total_flaky == 1 else "s"} detected (failed {Config.FLAKY_TESTS_MIN_FAILURES}+ times in last {Config.FLAKY_TESTS_LAST_RUNS} runs). <a href="#flaky-tests" style="color: #6366f1; text-decoration: none;">View all →</a></p>')
            
            # Group by failure count (occurrences)
            failure_count_groups = {}
            for failure in recurring_failures:
                occurrences = failure.get('occurrences', 0)
                if occurrences not in failure_count_groups:
                    failure_count_groups[occurrences] = []
                failure_count_groups[occurrences].append(failure)
            
            # Show failure count breakdown (sorted by count descending)
            sorted_counts = sorted(failure_count_groups.items(), key=lambda x: x[0], reverse=True)
            
            for occurrences, tests in sorted_counts[:5]:  # Show top 5 failure count groups
                count = len(tests)
                percentage = (occurrences / Config.FLAKY_TESTS_LAST_RUNS) * 100
                
                # Determine severity color based on failure count
                if occurrences >= 9:
                    count_color = "#dc3545"  # Red - critical
                elif occurrences >= 7:
                    count_color = "#e67e22"  # Orange - high
                elif occurrences >= 5:
                    count_color = "#f39c12"  # Yellow - medium
                else:
                    count_color = "#3498db"  # Blue - low
                
                html.append(f'''
                    <div style="background: #fff; padding: 10px 12px; border-radius: 6px; margin-bottom: 5px; border-left: 3px solid {count_color}; box-shadow: 0 1px 2px rgba(0,0,0,0.05); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <span style="font-size: 12px; font-weight: 600; color: #111827; background: rgba(16, 185, 129, 0.08); padding: 2px 6px; border-radius: 3px; white-space: nowrap;">
                                {count} test{"" if count == 1 else "s"}
                            </span>
                            <span style="font-size: 12px; color: #374151; flex: 1;">
                                failed <strong style="color: {count_color};">{occurrences} out of {Config.FLAKY_TESTS_LAST_RUNS}</strong> times ({percentage:.0f}% failure rate)
                            </span>
                        </div>
                    </div>
                ''')
            
            html.append('</div>')
        
        # 3. Quick Wins (Common Root Causes Affecting Multiple Tests)
        if category_failures:
            common_root_causes = self._identify_common_root_causes(category_failures)
            if common_root_causes:
                html.append('<div style="margin-bottom: 15px;">')
                html.append('<h3 style="color: #2c3e50; margin-bottom: 8px; font-size: 16px; border-bottom: 2px solid #10b981; padding-bottom: 6px; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">⚡ Quick Wins</h3>')
                html.append('<p style="margin-bottom: 8px; color: #666; font-size: 15px; font-family: -apple-system, BlinkMacSystemFont, \'Segoe UI\', Roboto, Helvetica, Arial, sans-serif;">Fix once, resolve multiple test failures.</p>')
                
                # Sort by number of affected tests (descending)
                sorted_common_causes = sorted(common_root_causes.items(), key=lambda x: len(x[1]['tests']), reverse=True)
                
                for idx, (normalized_rc, data) in enumerate(sorted_common_causes[:5]):  # Show top 5 common root causes
                    affected_tests = data['tests']
                    num_tests = len(affected_tests)
                    root_cause_text = data['root_cause']  # Use the first occurrence's root cause for display
                    category = data['category']
                    
                    # CRITICAL: Extract correct API from execution logs for the first test in the group
                    # This ensures we show the correct API that actually failed, not the one from AI-generated root_cause
                    if test_results and affected_tests:
                        from ..utils import TestDataCache
                        from ..reporters.report_generator import ReportGenerator
                        test_data_cache = TestDataCache(test_results, test_html_links or {})
                        report_gen = ReportGenerator()
                        
                        # Get execution log for the first test
                        first_test_name = affected_tests[0]
                        execution_log = test_data_cache.get_combined_log(first_test_name)
                        
                        if execution_log:
                            # Extract correct API using the same logic as report generator
                            details_info = report_gen._extract_detailed_info(root_cause_text, execution_log=execution_log, test_name=first_test_name)
                            
                            if details_info.get('api_info'):
                                correct_api = details_info['api_info'][0]
                                # Replace API name in root_cause_text if it contains an API name pattern
                                # Pattern: "API Name: /dashboard/aml/lnrn-search" or "API Name: GetAmlSearchSuccessfulResponse"
                                api_pattern = r'(API Name|Endpoint|api name|api url|url)[:\s]+([^\s,<>\n]+)'
                                if re.search(api_pattern, root_cause_text, re.IGNORECASE):
                                    # Replace the API name with the correct one
                                    # Match the pattern and replace just the API part (group 2)
                                    root_cause_text = re.sub(
                                        api_pattern,
                                        lambda m: f"{m.group(1)}: {correct_api}",
                                        root_cause_text,
                                        count=1,
                                        flags=re.IGNORECASE
                                    )
                    
                    # Get category style
                    category_style = category_styles.get(category, {
                        'icon': '❓',
                        'label': category.replace('_', ' ').title(),
                        'color': '#475569'
                    })
                    
                    # Truncate root cause text if too long (shorter for cleaner display)
                    display_rc = root_cause_text[:150] + "..." if len(root_cause_text) > 150 else root_cause_text
                    
                    # Create a compact preview list of test names (first 2)
                    test_names_preview = []
                    for test_name in affected_tests[:2]:
                        from ..utils import extract_class_and_method
                        class_name, method_name = extract_class_and_method(test_name)
                        test_names_preview.append(f"{class_name}.{method_name}")
                    
                    # Generate collapsible section ID
                    details_id = f"quick-win-{idx}"
                    
                    # Build test names list with links and copy buttons
                    test_names_html = []
                    for test_name in affected_tests:
                        from ..utils import extract_class_and_method
                        class_name, method_name = extract_class_and_method(test_name)
                        display_name = f"{class_name}.{method_name}"
                        display_name_escaped = html_escape.escape(display_name)
                        test_name_js = html_escape.escape(test_name).replace("'", "\\'")
                        
                        # Get HTML link if available - try multiple name formats
                        html_link = None
                        if test_html_links:
                            # Try exact match first
                            html_link = test_html_links.get(test_name)
                            # Try with class.method format
                            if not html_link:
                                html_link = test_html_links.get(display_name)
                            # Try normalized versions (remove duplicate class names)
                            if not html_link:
                                normalized_test_name = remove_duplicate_class_name(test_name)
                                html_link = test_html_links.get(normalized_test_name)
                            # Try with full class path (package.class.method)
                            if not html_link:
                                # Extract full class name from test_name if it contains package info
                                if '::' in test_name or '.' in test_name:
                                    parts = test_name.split('::') if '::' in test_name else test_name.split('.')
                                    if len(parts) >= 2:
                                        # Try with just class.method
                                        simple_name = f"{parts[-2]}.{parts[-1]}"
                                        html_link = test_html_links.get(simple_name)
                            # Try partial matches (check if any key contains the test name or vice versa)
                            if not html_link:
                                for key, link in test_html_links.items():
                                    # Normalize both for comparison
                                    key_normalized = key.lower().replace(' ', '').replace('_', '')
                                    test_normalized = test_name.lower().replace(' ', '').replace('_', '')
                                    display_normalized = display_name.lower().replace(' ', '').replace('_', '')
                                    
                                    if (test_normalized in key_normalized or key_normalized in test_normalized or 
                                        display_normalized in key_normalized or key_normalized in display_normalized):
                                        html_link = link
                                        break
                        
                        html_link_escaped = html_escape.escape(html_link) if html_link else None
                        
                        # Build test name HTML with link and copy button
                        if html_link_escaped:
                            test_name_html = f'''
                                <div style="display: flex; align-items: center; gap: 6px; padding: 4px 6px; margin: 2px 0; background: #f9fafb; border-radius: 4px; font-size: 12px;">
                                    <a href="{html_link_escaped}" target="_blank" onclick="event.stopPropagation();" style="flex: 1; color: #6366f1; text-decoration: none; font-weight: 500; cursor: pointer;" onmouseover="this.style.textDecoration='underline'; this.style.color='#4f46e5';" onmouseout="this.style.textDecoration='none'; this.style.color='#6366f1';" title="Open test logs: {html_escape.escape(html_link)}">
                                        {display_name_escaped}
                                    </a>
                                    <button onclick="copyTestName('{test_name_js}', this, event)" style="background: none; border: none; color: #6b7280; cursor: pointer; padding: 2px 4px; display: flex; align-items: center;" title="Copy test name" class="quick-win-copy-btn">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                    </button>
                                </div>
                            '''
                        else:
                            test_name_html = f'''
                                <div style="display: flex; align-items: center; gap: 6px; padding: 4px 6px; margin: 2px 0; background: #f9fafb; border-radius: 4px; font-size: 12px;">
                                    <span style="flex: 1; color: #374151;">{display_name_escaped}</span>
                                    <button onclick="copyTestName('{test_name_js}', this, event)" style="background: none; border: none; color: #6b7280; cursor: pointer; padding: 2px 4px; display: flex; align-items: center;" title="Copy test name" class="quick-win-copy-btn">
                                        <svg xmlns="http://www.w3.org/2000/svg" width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg>
                                    </button>
                                </div>
                            '''
                        test_names_html.append(test_name_html)
                    
                    preview_text = ', '.join([html_escape.escape(name) for name in test_names_preview])
                    if num_tests > 2:
                        preview_text += f" +{num_tests - 2} more"
                    
                    html.append(f'''
                        <div style="background: #fff; padding: 8px 12px; border-radius: 6px; margin-bottom: 4px; border-left: 3px solid {category_style['color']}; box-shadow: 0 1px 2px rgba(0,0,0,0.05); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;">
                            <div style="display: flex; align-items: flex-start; gap: 8px;">
                                <div style="flex: 1; min-width: 0;">
                                    <div style="display: flex; align-items: center; gap: 6px; margin-bottom: 3px; flex-wrap: wrap;">
                                        <span style="font-size: 13px; font-weight: 600; color: #111827; background: rgba(16, 185, 129, 0.1); padding: 2px 6px; border-radius: 3px; white-space: nowrap;">
                                            {num_tests} test{"" if num_tests == 1 else "s"}
                                        </span>
                                        <span style="font-size: 13px; font-weight: 600; color: #374151; line-height: 1.4; flex: 1; min-width: 0;">
                                            {html_escape.escape(display_rc)}
                                        </span>
                                    </div>
                                    <div style="font-size: 11px; color: #9ca3af; margin-top: 1px; margin-bottom: 0; line-height: 1.2;">
                                        {preview_text}
                                    </div>
                                    <details id="{details_id}" style="margin: 0; padding: 0;">
                                        <summary style="font-size: 11px; color: #6366f1; cursor: pointer; user-select: none; list-style: none; display: inline-flex; align-items: center; gap: 3px; text-decoration: underline; text-decoration-color: rgba(99, 102, 241, 0.4); margin: 0; padding: 0; line-height: 1;" onmouseover="this.style.textDecorationColor='rgba(99, 102, 241, 0.7)'" onmouseout="this.style.textDecorationColor='rgba(99, 102, 241, 0.4)'">
                                            <span style="line-height: 1;">Show all tests</span>
                                            <svg id="{details_id}-icon" xmlns="http://www.w3.org/2000/svg" width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="transition: transform 0.2s; display: inline-block; vertical-align: middle; line-height: 1;">
                                                <polyline points="6 9 12 15 18 9"></polyline>
                                            </svg>
                                        </summary>
                                        <div style="margin-top: 3px; padding-top: 3px; border-top: 1px solid #e5e7eb; max-height: 200px; overflow-y: auto;">
                                            {''.join(test_names_html)}
                                        </div>
                                    </details>
                                    <script>
                                        (function() {{
                                            const details = document.getElementById('{details_id}');
                                            const icon = document.getElementById('{details_id}-icon');
                                            if (details && icon) {{
                                                details.addEventListener('toggle', function() {{
                                                    icon.style.transform = details.open ? 'rotate(180deg)' : 'rotate(0deg)';
                                                }});
                                            }}
                                        }})();
                                    </script>
                                    <style>
                                        .quick-win-copy-btn:hover {{
                                            color: #111827;
                                        }}
                                        .quick-win-copy-btn:active {{
                                            transform: scale(0.9);
                                        }}
                                    </style>
                                </div>
                            </div>
                        </div>
                    ''')
                
                html.append('</div>')
        
        return ''.join(html)
