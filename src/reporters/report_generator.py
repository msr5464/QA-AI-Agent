"""
HTML Report Generator for test reports.
Generates comprehensive HTML reports with test failures, AI analysis, and trends.
"""

import os
import logging
import re
import html as html_escape
from typing import List, Dict, Optional, Tuple
from datetime import datetime
from pathlib import Path

from ..parsers.models import TestSummary, TestResult
from ..agent.analyzer import FailureClassification
from ..utils import (
    TestNameNormalizer,
    TestDataCache,
    extract_api_endpoint,
    remove_duplicate_class_name,
    extract_class_and_method,
    ReportUrlBuilder,
    normalize_root_cause
)
from ..settings import Config
from .category_rules import CategoryRuleEngine
from .data_validator import validate_report_data, validate_post_report
from .html_styles import get_html_styles
from .html_scripts import get_html_scripts

logger = logging.getLogger(__name__)


class ReportGenerator:
    """Generates HTML test reports"""
    
    def extract_test_api_map(
        self,
        classifications: List[FailureClassification],
        test_data_cache: TestDataCache
    ) -> Dict[str, List[str]]:
        """
        Extract API endpoints for all classifications using the same method as tables.
        Returns a map: test_name -> list of API endpoints
        
        Args:
            classifications: List of failure classifications
            test_data_cache: TestDataCache instance for consistent data access
            
        Returns:
            Dictionary mapping test_name to list of API endpoints
        """
        test_api_map: Dict[str, List[str]] = {}
        
        for classification in classifications:
            test_name_normalized = classification.test_name.strip()
            if test_name_normalized not in test_api_map:
                # Get execution log from cache
                execution_log = test_data_cache.get_combined_log(test_name_normalized)
                
                # Extract API endpoints using the same method as tables
                search_text = classification.root_cause
                if execution_log:
                    search_text = classification.root_cause + "\n\n" + execution_log
                
                details_info = self._extract_detailed_info(search_text, execution_log=execution_log, test_name=test_name_normalized)
                if details_info.get('api_info'):
                    test_api_map[test_name_normalized] = details_info['api_info']
        
        return test_api_map
    
    def __init__(self):
        """Initialize report generator"""
        pass
    
    def generate_html_report(
        self,
        summary: TestSummary,
        classifications: List[FailureClassification],
        report_name: str,
        ai_summary: str = "",
        recurring_failures: Optional[List[Dict]] = None,
        trend: Optional[str] = None,
        report_dir: Optional[str] = None,
        test_results: Optional[List[TestResult]] = None,
        test_html_links: Optional[Dict[str, str]] = None
    ) -> tuple[str, Dict[str, List[str]]]:
        """
        Generate HTML report content.
        
        Args:
            summary: TestSummary object
            classifications: List of failure classifications
            report_name: Name of the report
            ai_summary: AI-generated executive summary text
            recurring_failures: List of recurring failures
            trend: Trend indicator
            report_dir: Path to report directory for HTML links
            test_results: List of test results for descriptions
            
        Returns:
            HTML content as string
        """
        html_content, test_api_map = self._generate_html(
            summary, classifications, report_name, ai_summary, recurring_failures, trend, report_dir, test_results, test_html_links
        )
        return html_content, test_api_map
    
    def save_report(self, html_content: str, output_path: str) -> str:
        """
        Save HTML report to file.
        
        Args:
            html_content: HTML content to save
            output_path: Path to save the report
            
        Returns:
            Absolute path to saved file
        """
        try:
            output_file = Path(output_path)
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(html_content)
            
            logger.debug(f"✅ Report saved to {output_file.absolute()}")
            return str(output_file.absolute())
        except Exception as e:
            logger.error(f"Failed to save report: {e}")
            raise
    
    def _find_test_html_link(self, class_name: str, method_name: str, report_dir: Optional[str], report_name: str, test_html_links: Optional[Dict[str, str]] = None) -> Optional[str]:
        """
        Find HTML link for a test in the report directory using actual method name.
        
        Args:
            class_name: Class name (e.g., "TestDashAmlApis")
            method_name: Actual method name (e.g., "testDoAmlSearchForBusiness")
            report_dir: Path to report directory
            report_name: Report name (e.g., "Regression-AccountOpening-Tests-424")
            
        Returns:
            HTML link URL or None if not found
        """
        if not report_dir:
            return None
        
        # Try to use cached HTML links first
        if test_html_links:
            # Try exact match with full class name
            full_name = f"{class_name}.{method_name}"
            if full_name in test_html_links:
                return test_html_links[full_name]
            
            # Try with cleaned class name
            cleaned_class = remove_duplicate_class_name(class_name)
            cleaned_full_name = f"{cleaned_class}.{method_name}"
            if cleaned_full_name in test_html_links:
                return test_html_links[cleaned_full_name]
            
            # Try matching by method name only
            method_lower = method_name.lower()
            for test_name, link in test_html_links.items():
                if test_name.split('.')[-1].lower() == method_lower:
                    return link
        
        # Fallback: parse HTML if cache miss (shouldn't happen often)
        try:
            from ..parsers.html_parser import HTMLReportParser
            
            report_path = Path(report_dir)
            html_dir = report_path / 'html'
            
            if not html_dir.exists():
                return None
            
            # Parse overview to get test suite files
            overview_path = html_dir / 'overview.html'
            if not overview_path.exists():
                return None
            
            parser = HTMLReportParser()
            test_suites = parser.parse_overview(str(overview_path))
            
            # Search through test suites to find the one containing this test
            # We need to check each suite file to see if it contains the test
            for suite in test_suites:
                results_file = html_dir / suite['results_file']
                if results_file.exists():
                    # Parse the suite file to check if it contains this test
                    try:
                        from ..parsers.html_parser import HTMLReportParser
                        suite_parser = HTMLReportParser()
                        suite_results = suite_parser.parse_test_results(str(results_file))
                        
                        # Check if this test is in this suite
                        test_found = False
                        for result in suite_results:
                            # Normalize class and method names for comparison
                            result_class = remove_duplicate_class_name(result.class_name)
                            result_method = result.method_name
                            
                            # Check if class and method match (handle both full and short class names)
                            class_matches = (class_name == result_class or 
                                           class_name.endswith('.' + result_class) or
                                           result_class.endswith('.' + class_name) or
                                           class_name.split('.')[-1] == result_class.split('.')[-1])
                            method_matches = (method_name == result_method)
                            
                            if class_matches and method_matches:
                                test_found = True
                                break
                        
                        if test_found:
                            suite_file = suite['results_file']
                            
                            if report_name:
                                html_link = self._build_dashboard_url(report_name, f"html/{suite_file}")
                                return html_link
                            
                            # Fallback: use relative path if report_name not available
                            return f"html/{suite_file}"
                    except Exception as e:
                        logger.debug(f"Error parsing suite file {results_file} to find test: {e}")
                        continue
            
            # Fallback: return overview if specific test not found
            if report_name:
                return self._build_dashboard_url(report_name, "html/overview.html")
            return "html/overview.html"
            
        except Exception as e:
            logger.debug(f"Could not find HTML link for {class_name}.{method_name}: {e}")
            return None
    
    def _parse_automation_group_and_branch(self, report_dir: Optional[str]) -> tuple[Optional[str], Optional[str]]:
        """
        Parse automation group and branch from overview.html header.
        Example: "regression cases on develop branch" -> ("regression", "develop")
        
        Returns:
            Tuple of (automation_group, automation_branch) or (None, None) if not found
        """
        if not report_dir:
            return None, None
        
        try:
            from pathlib import Path
            from bs4 import BeautifulSoup
            
            overview_path = Path(report_dir) / 'html' / 'overview.html'
            if not overview_path.exists():
                return None, None
            
            with open(overview_path, 'r', encoding='utf-8') as f:
                soup = BeautifulSoup(f.read(), 'lxml')
            
            # Find the header suite row that contains the text
            header_row = soup.find('th', class_='header suite')
            if not header_row:
                return None, None
            
            # Remove the suiteLinks div to get only the actual text
            suite_links_div = header_row.find('div', class_='suiteLinks')
            if suite_links_div:
                suite_links_div.decompose()  # Remove it from the tree
            
            # Get the text content (after removing suiteLinks div)
            header_text = header_row.get_text(strip=True)
            
            # Parse pattern: "{group} cases on {branch} branch"
            # Example: "regression cases on develop branch"
            import re
            pattern = r'(\w+)\s+cases\s+on\s+(\w+)\s+branch'
            match = re.search(pattern, header_text, re.IGNORECASE)
            
            if match:
                automation_group = match.group(1).lower()
                automation_branch = match.group(2).lower()
                return automation_group, automation_branch
            
            return None, None
        except Exception as e:
            logger.debug(f"Could not parse automation group and branch: {e}")
            return None, None
    
    def _get_test_info(self, test_name: str, test_results: Optional[List[TestResult]], report_dir: Optional[str] = None) -> Tuple[str, str, str]:
        """
        Get test class name, actual method name, and description from test results.
        Uses FULL qualified class name (e.g., Automation.Access.AccountOpening.api.dash.TestDashBusinessesApis).
        
        Args:
            test_name: Full test name from classification
            test_results: List of test results
            report_dir: Path to report directory to parse XML for method names
            
        Returns:
            Tuple of (full_class_name, method_name, description)
        """
        # Try to find matching test result using TestNameNormalizer
        if test_results:
            matching_test = TestNameNormalizer.find_matching_test(test_name, test_results)
            
            if matching_test:
                # Use FULL qualified class name, not just the short name
                class_name = matching_test.class_name  # Keep full package path
                # CRITICAL: Remove duplicate class name if present
                class_name = remove_duplicate_class_name(class_name)
                method_name = matching_test.method_name  # This is the actual method name from HTML parser
                
                # Get description - prioritize result.description (English description from HTML parser)
                # result.description contains the English description of what the test does
                # Examples: "Verify that admin can do Aml search for person"
                #           "Verify that AML is NOT triggered if update address of business"
                description = matching_test.description if matching_test.description else None
                
                # If we don't have a description, try to extract it from execution log
                # Pattern: "[21:33:48] Execution started for testcase - Verify that Compliance can approve high risk Kyb"
                if not description and matching_test.execution_log:
                    description = self._extract_description_from_log(matching_test.execution_log)
                
                # If we still don't have a description, check if method_name looks like a description
                # (has spaces, readable English) - in that case, it's actually the description
                if not description:
                    # Check if method_name is actually a description (has spaces, readable English)
                    if ' ' in method_name or len(method_name) > 50:
                        # This looks like a description, not a method name
                        description = method_name
                        # Try to get actual method name from XML
                        actual_method_name = self._get_actual_method_name(
                            matching_test.class_name, method_name, report_dir
                        )
                        if actual_method_name and actual_method_name != method_name:
                            method_name = actual_method_name
                    # IMPORTANT: Do NOT use method_name as description fallback
                    # If description is None, keep it as None - don't show method name as description
                    # description remains None if we don't have a real description
                
                return class_name, method_name, description
        
        # Fallback: extract from full name
        # If test_name already contains full qualified path, use it as-is
        # Otherwise, try to extract from the name
        if '.' in test_name and test_name.count('.') >= 2:
            # Looks like it might already be a full qualified name
            parts = test_name.split('.')
            # Last part is method name, everything before is class name
            class_name = '.'.join(parts[:-1])
            method_name = parts[-1]
            
            # CRITICAL: Remove duplicate class name if present
            # Example: "Automation.Access.AccountOpening.api.dash.TestDashBusinessesApis.TestDashBusinessesApis"
            # Should become: "Automation.Access.AccountOpening.api.dash.TestDashBusinessesApis"
            class_name = remove_duplicate_class_name(class_name)
            
            # IMPORTANT: Do NOT use method_name as description - if we don't have description, keep it None
            description = None
        else:
            class_name, method_name = extract_class_and_method(test_name)
            # Remove duplicates from class_name
            class_name = remove_duplicate_class_name(class_name)
            # IMPORTANT: Do NOT use method_name as description - if we don't have description, keep it None
            description = None
        return class_name, method_name, description
    
    def _extract_description_from_log(self, execution_log: str) -> Optional[str]:
        """
        Extract test case description from execution log.
        Looks for pattern: "Execution started for testcase - <description>"
        
        Example:
        Input: "[21:33:48] Execution started for testcase - Verify that Compliance can approve high risk Kyb"
        Output: "Verify that Compliance can approve high risk Kyb"
        
        Args:
            execution_log: Full execution log text
            
        Returns:
            Description string if found, None otherwise
        """
        if not execution_log:
            return None
        
        import re
        
        # Pattern: "Execution started for testcase - <description>"
        # May have timestamp prefix like "[21:33:48]"
        pattern = r'Execution started for testcase\s*-\s*(.+?)(?:\n|$)'
        match = re.search(pattern, execution_log, re.IGNORECASE | re.MULTILINE)
        
        if match:
            description = match.group(1).strip()
            # Clean up any trailing characters or newlines
            description = description.split('\n')[0].strip()
            if description:
                return description
        
        return None
    
    def _get_actual_method_name(self, class_name: str, description: str, report_dir: Optional[str]) -> Optional[str]:
        """
        Get method name from HTML description.
        XML parsing removed - using HTML data only.
        
        Args:
            class_name: Full class name
            description: Test description (from HTML)
            report_dir: Path to report directory (not used, kept for compatibility)
            
        Returns:
            Method name from description, or None
        """
        # HTML parser already provides method_name from description
        # No need to query XML files
        return None
    
    def _extract_one_liner_summary(self, root_cause: str, details_info: Optional[dict] = None) -> str:
        """
        Extract a one-liner summary from the root cause for quick understanding.
        Provides specific, detailed summaries instead of generic ones.
        
        Args:
            root_cause: Full root cause text
            details_info: Optional dictionary with extracted details (api_info, etc.)
                         If provided, uses corrected API endpoint from details_info instead of root_cause
            
        Returns:
            One-line summary string with specific details
        """
        root_cause_lower = root_cause.lower()
        
        # Extract API URL first (will be used for all API-related errors)
        # CRITICAL: Use API from details_info if available (corrected API), otherwise extract from root_cause
        api_url = None
        if details_info and details_info.get('api_info'):
            # Use the corrected API endpoint from details_info (e.g., /dashboard/businesses/{$uuid})
            api_url = details_info['api_info'][0]
            # Clean up if needed
            api_url = api_url.replace('http://', '').replace('https://', '')
            if len(api_url) > 60:
                api_url = api_url[:60] + "..."
        else:
            # Fallback: Extract from root_cause if details_info not available
            url_patterns = [
                r'(POST|GET|PUT|DELETE|PATCH)\s+([^\s,<>\n]+)',
                r'(API Name|Endpoint|api name|api url|url)[:\s]+([^\s,<>\n]+)',
                r'(https?://[^\s]+|/api/[^\s]+|/dashboard/[^\s]+)',
            ]
            
            for pattern in url_patterns:
                url_match = re.search(pattern, root_cause, re.IGNORECASE)
                if url_match:
                    if len(url_match.groups()) > 1:
                        api_url = url_match.group(2).strip()
                    else:
                        api_url = url_match.group(1).strip()
                    api_url = api_url.replace('http://', '').replace('https://', '')
                    if len(api_url) > 60:
                        api_url = api_url[:60] + "..."
                    break
        
        # Missing keys/fields issues - check this FIRST as it's more specific than generic API issues
        # Format: "API Error (missing key: <key_name>) - <api url>"
        # Handle multiple patterns:
        # 1. "Expected keys: [...] but Actual keys: [...]"
        # 2. "Expected has: [...] but Actual has: [...]"
        # 3. "Missing keys: [...]"
        # 4. "missing required keys: [...]"
        
        # Pattern: Expected keys vs Actual keys comparison
        # Handle quotes around brackets: '[...]' or [...]
        expected_actual_match = re.search(r"Expected\s+(?:keys|has)[:\s]+'?\[([^\]]+)\]'?.*?(?:but\s+)?Actual\s+(?:keys|has)[:\s]+'?\[([^\]]+)\]'?", root_cause, re.IGNORECASE | re.DOTALL)
        if expected_actual_match:
            expected_keys_str = expected_actual_match.group(1).strip()
            actual_keys_str = expected_actual_match.group(2).strip()
            
            # Parse keys from both lists
            expected_keys = [k.strip().strip("'\"") for k in expected_keys_str.split(',') if k.strip()]
            actual_keys = [k.strip().strip("'\"") for k in actual_keys_str.split(',') if k.strip()]
            
            # Find missing keys (in expected but not in actual)
            missing_keys = [k for k in expected_keys if k not in actual_keys]
            
            if missing_keys:
                # Extract API URL
                api_url = None
                url_patterns = [
                    r'(POST|GET|PUT|DELETE|PATCH)\s+([^\s,<>\n]+)',
                    r'(API Name|Endpoint|api name|api url|url)[:\s]+([^\s,<>\n]+)',
                    r'(https?://[^\s]+|/api/[^\s]+|/dashboard/[^\s]+)',
                ]
                
                for pattern in url_patterns:
                    url_match = re.search(pattern, root_cause, re.IGNORECASE)
                    if url_match:
                        if len(url_match.groups()) > 1:
                            api_url = url_match.group(2).strip()
                        else:
                            api_url = url_match.group(1).strip()
                        api_url = api_url.replace('http://', '').replace('https://', '')
                        if len(api_url) > 60:
                            api_url = api_url[:60] + "..."
                        break
                
                # Get first missing key
                first_missing_key = missing_keys[0]
                if len(first_missing_key) > 30:
                    first_missing_key = first_missing_key[:30]
                
                error_reason = f"missing key: {first_missing_key}"
                if api_url:
                    return f"API Error ({error_reason}) - {api_url}"
                else:
                    return f"API Error ({error_reason})"
        
        # Pattern: "Missing keys: [...]" at the end
        missing_keys_end_match = re.search(r'Missing\s+keys?[:\s]+\[([^\]]+)\]', root_cause, re.IGNORECASE)
        if missing_keys_end_match:
            missing_keys_str = missing_keys_end_match.group(1).strip()
            missing_keys = [k.strip().strip("'\"") for k in missing_keys_str.split(',') if k.strip()]
            
            if missing_keys:
                # Extract API URL
                api_url = None
                url_patterns = [
                    r'(POST|GET|PUT|DELETE|PATCH)\s+([^\s,<>\n]+)',
                    r'(API Name|Endpoint|api name|api url|url)[:\s]+([^\s,<>\n]+)',
                    r'(https?://[^\s]+|/api/[^\s]+|/dashboard/[^\s]+)',
                ]
                
                for pattern in url_patterns:
                    url_match = re.search(pattern, root_cause, re.IGNORECASE)
                    if url_match:
                        if len(url_match.groups()) > 1:
                            api_url = url_match.group(2).strip()
                        else:
                            api_url = url_match.group(1).strip()
                        api_url = api_url.replace('http://', '').replace('https://', '')
                        if len(api_url) > 60:
                            api_url = api_url[:60] + "..."
                        break
                
                # Get first missing key
                first_missing_key = missing_keys[0]
                if len(first_missing_key) > 30:
                    first_missing_key = first_missing_key[:30]
                
                error_reason = f"missing key: {first_missing_key}"
                if api_url:
                    return f"API Error ({error_reason}) - {api_url}"
                else:
                    return f"API Error ({error_reason})"
        
        # Original pattern: "missing required keys: [...]" or "missing key: ..."
        if "missing" in root_cause_lower and ("key" in root_cause_lower or "field" in root_cause_lower):
            # API URL already extracted above
            
            # Extract missing keys/fields - improved to handle arrays properly
            error_reason = None
            
            # Pattern 1: missing keys: [key1, key2] - extract from brackets
            missing_match = re.search(r'(missing|absent)[:\s]*(?:required\s+)?(?:keys?|fields?)[:\s]*\[([^\]]+)\]', root_cause, re.IGNORECASE)
            if missing_match:
                # Extract keys from array - split by comma
                keys_str = missing_match.group(2).strip()
                keys = [k.strip() for k in keys_str.split(',') if k.strip() and k.strip().lower() not in ['required', 'keys', 'key', 'fields', 'field']]
                if keys:
                    first_key = keys[0]
                    if len(first_key) > 20:
                        first_key = first_key[:20]
                    error_reason = f"missing key: {first_key}"
            
            # Pattern 2: missing key: keyname or missing keys: key1, key2 (without brackets)
            if not error_reason:
                missing_match = re.search(r'(missing|absent)[:\s]*(?:required\s+)?(?:keys?|fields?)[:\s]+([^\n,\[<]+)', root_cause, re.IGNORECASE)
                if missing_match:
                    keys_str = missing_match.group(2).strip()
                    # Remove trailing words like "keys", "fields", "required"
                    keys_str = re.sub(r'\s+(required|keys?|fields?)$', '', keys_str, flags=re.IGNORECASE)
                    # Split by comma if multiple keys
                    if ',' in keys_str:
                        keys = [k.strip() for k in keys_str.split(',') if k.strip() and k.strip().lower() not in ['required', 'keys', 'key', 'fields', 'field']]
                        if keys:
                            first_key = keys[0]
                            if len(first_key) > 20:
                                first_key = first_key[:20]
                            error_reason = f"missing key: {first_key}"
                    else:
                        key_name = keys_str.strip()
                        # Remove "required" if it's still there
                        key_name = re.sub(r'^\s*required\s+', '', key_name, flags=re.IGNORECASE)
                        if len(key_name) > 30:
                            key_name = key_name[:30]
                        if key_name and key_name.lower() not in ['required', 'keys', 'key', 'fields', 'field']:
                            error_reason = f"missing key: {key_name}"
            
            # Format: "API Error (missing key: <key>) - <api url>"
            if error_reason:
                if api_url:
                    return f"API Error ({error_reason}) - {api_url}"
                else:
                    return f"API Error ({error_reason})"
            
            # Try alternative pattern
            key_match = re.search(r'(missing|absent)[:\s]+([a-zA-Z_][a-zA-Z0-9_]*)(?:\s|,|$)', root_cause, re.IGNORECASE)
            if key_match:
                error_reason = f"missing key: {key_match.group(2)}"
                if api_url:
                    return f"API Error ({error_reason}) - {api_url}"
                else:
                    return f"API Error ({error_reason})"
        
        # API-related issues - standardized format: "API Error (<reason>) - <api url>"
        if "api" in root_cause_lower or "/api/" in root_cause or "http" in root_cause_lower or "/dashboard/" in root_cause_lower:
            # Use API URL from details_info if available (corrected API), otherwise extract from root_cause
            if not api_url:
                if details_info and details_info.get('api_info'):
                    api_url = details_info['api_info'][0]
                    api_url = api_url.replace('http://', '').replace('https://', '')
                    if len(api_url) > 60:
                        api_url = api_url[:60] + "..."
                else:
                    # Fallback: Extract API URL/endpoint from root_cause
                    url_patterns = [
                        r'(POST|GET|PUT|DELETE|PATCH)\s+([^\s,<>\n]+)',  # Method + URL
                        r'(API Name|Endpoint|api name|api url|url)[:\s]+([^\s,<>\n]+)',  # Explicit API name/endpoint
                        r'(https?://[^\s]+|/api/[^\s]+|/dashboard/[^\s]+)',  # Direct URL pattern
                    ]
                    
                    for pattern in url_patterns:
                        url_match = re.search(pattern, root_cause, re.IGNORECASE)
                        if url_match:
                            if len(url_match.groups()) > 1:
                                api_url = url_match.group(2).strip()
                            else:
                                api_url = url_match.group(1).strip()
                            
                            # Clean up URL (remove common prefixes, truncate if too long)
                            api_url = api_url.replace('http://', '').replace('https://', '')
                            if len(api_url) > 60:
                                api_url = api_url[:60] + "..."
                            break
                    
                    # If no URL found, try to extract from common patterns
                    if not api_url:
                        # Look for /api/ or /dashboard/ patterns
                        path_match = re.search(r'(/api/[^\s,<>\n]+|/dashboard/[^\s,<>\n]+)', root_cause)
                        if path_match:
                            api_url = path_match.group(1)
                            if len(api_url) > 60:
                                api_url = api_url[:60] + "..."
            
            # Determine the error reason
            error_reason = None
            
            # 1. Check for missing keys/fields (highest priority)
            # Pattern 1: missing keys: [key1, key2] or missing keys: key1, key2
            missing_keys_match = re.search(r'(missing|absent)[:\s]*(?:required\s+)?(?:keys?|fields?)[:\s]*\[([^\]]+)\]', root_cause, re.IGNORECASE)
            if missing_keys_match:
                # Extract keys from array
                keys_str = missing_keys_match.group(2).strip()
                keys = [k.strip() for k in keys_str.split(',') if k.strip()]
                if keys:
                    first_key = keys[0]
                    if len(first_key) > 20:
                        first_key = first_key[:20]
                    error_reason = f"missing key: {first_key}"
            else:
                # Pattern 2: missing key: keyname or missing keys: key1, key2 (without brackets)
                missing_keys_match = re.search(r'(missing|absent)[:\s]*(?:required\s+)?(?:keys?|fields?)[:\s]+([^\n,\[<]+)', root_cause, re.IGNORECASE)
                if missing_keys_match:
                    keys_str = missing_keys_match.group(2).strip()
                    # Remove trailing words like "keys", "fields"
                    keys_str = re.sub(r'\s+(keys?|fields?)$', '', keys_str, flags=re.IGNORECASE)
                    # Split by comma if multiple keys
                    if ',' in keys_str:
                        keys = [k.strip() for k in keys_str.split(',') if k.strip()]
                        if keys:
                            first_key = keys[0]
                            if len(first_key) > 20:
                                first_key = first_key[:20]
                            error_reason = f"missing key: {first_key}"
                    else:
                        key_name = keys_str.strip()
                        if len(key_name) > 30:
                            key_name = key_name[:30]
                        if key_name:
                            error_reason = f"missing key: {key_name}"
            
            # 2. Check for status code errors (if not 200)
            if not error_reason:
                status_match = re.search(r'\b(40[0-9]|50[0-9]|30[0-9])\b', root_cause)
                if status_match:
                    status_code = status_match.group(1)
                    # Only include if it's an error status (not 200)
                    if status_code != "200":
                        error_reason = f"status {status_code}"
            
            # 3. Check for key mismatch
            if not error_reason:
                mismatch_match = re.search(r'(key|field|value)[:\s]+([^\s,<>\n]+)[:\s]+(mismatch|does not match|expected|unexpected)', root_cause, re.IGNORECASE)
                if mismatch_match:
                    key_name = mismatch_match.group(2).strip()
                    if len(key_name) > 20:
                        key_name = key_name[:20]
                    error_reason = f"key mismatch: {key_name}"
            
            # 4. Check for other common API errors (one-word reasons)
            if not error_reason:
                # Timeout
                if "timeout" in root_cause_lower:
                    error_reason = "timeout"
                # Connection error
                elif "connection" in root_cause_lower or "connect" in root_cause_lower:
                    error_reason = "connection"
                # Unauthorized
                elif "unauthorized" in root_cause_lower or "401" in root_cause:
                    error_reason = "unauthorized"
                # Forbidden
                elif "forbidden" in root_cause_lower or "403" in root_cause:
                    error_reason = "forbidden"
                # Not found
                elif "not found" in root_cause_lower or "404" in root_cause:
                    error_reason = "not found"
                # Server error
                elif "server error" in root_cause_lower or "500" in root_cause:
                    error_reason = "server error"
                # Bad request
                elif "bad request" in root_cause_lower or "400" in root_cause:
                    error_reason = "bad request"
                # Validation error
                elif "validation" in root_cause_lower:
                    error_reason = "validation"
                # Generic error
                elif "error" in root_cause_lower or "failed" in root_cause_lower:
                    error_reason = "error"
            
            # Format: "API Error (<reason>) - <api url>"
            if error_reason and api_url:
                return f"API Error ({error_reason}) - {api_url}"
            elif error_reason:
                return f"API Error ({error_reason})"
            elif api_url:
                return f"API Error - {api_url}"
            else:
                return "API Error"
        
        # Element/Locator issues - extract specific locator
        elif "nosuchelementexception" in root_cause_lower or "element not found" in root_cause_lower or "locator" in root_cause_lower:
            # Try multiple patterns for locator
            locator_patterns = [
                r'(Locator|Selector|Element|id|name|class)[:\s=]+([#.a-zA-Z0-9_-]+)',
                r'([#.a-zA-Z0-9_-]+)\s+(not found|could not be found|was not found)',
                r'Unable to locate element[:\s]+([^\n,<]{0,50})'
            ]
            
            for pattern in locator_patterns:
                locator_match = re.search(pattern, root_cause, re.IGNORECASE)
                if locator_match:
                    locator = locator_match.group(2) if len(locator_match.groups()) > 1 else locator_match.group(1)
                    if locator and len(locator.strip()) > 0:
                        return f"Element not found: {locator.strip()[:60]}"
            
            # Extract exception message if available
            exception_msg = re.search(r'NoSuchElementException[:\s]+([^\n]{0,80})', root_cause, re.IGNORECASE)
            if exception_msg:
                return f"Element not found: {exception_msg.group(1).strip()[:60]}"
            
            return "Element not found in DOM"
        
        # Timeout issues - extract timeout duration if available
        elif "timeoutexception" in root_cause_lower or "timeout" in root_cause_lower:
            timeout_match = re.search(r'(\d+)\s*(second|sec|ms|millisecond)', root_cause, re.IGNORECASE)
            element_match = re.search(r'(element|locator|selector)[:\s]+([^\n,<]{0,40})', root_cause, re.IGNORECASE)
            
            parts = []
            if timeout_match:
                parts.append(f"Timeout after {timeout_match.group(1)} {timeout_match.group(2)}")
            else:
                parts.append("Timeout waiting")
            
            if element_match:
                element_name = element_match.group(2).strip()
                if element_name:
                    parts.append(f"for element: {element_name[:40]}")
            
            return " | ".join(parts) if parts else "Element did not appear within timeout period"
        
        # Stale element issues
        elif "staleelement" in root_cause_lower:
            return "Element became stale (DOM changed during test execution)"
        
        # CRITICAL: Check for specific exceptions BEFORE checking AssertionError
        # Many exceptions are wrapped in AssertionError, but the real issue is the underlying exception
        # Check for Selenium exceptions first (most common in UI tests)
        selenium_exceptions = [
            r'ElementClickInterceptedException[:\s]+([^\n]{0,150})',
            r'NoSuchElementException[:\s]+([^\n]{0,150})',
            r'TimeoutException[:\s]+([^\n]{0,150})',
            r'StaleElementReferenceException[:\s]+([^\n]{0,150})',
            r'ElementNotInteractableException[:\s]+([^\n]{0,150})',
            r'WebDriverException[:\s]+([^\n]{0,150})',
        ]
        
        for pattern in selenium_exceptions:
            match = re.search(pattern, root_cause, re.IGNORECASE)
            if match:
                exc_msg = match.group(1).strip()
                # Extract the key part of the message (usually the first sentence or up to 100 chars)
                if exc_msg:
                    # Try to extract the most relevant part
                    if "element click intercepted" in exc_msg.lower():
                        # Extract what element was intercepted
                        element_match = re.search(r'Element\s+<([^>]+)>', exc_msg, re.IGNORECASE)
                        if element_match:
                            element_info = element_match.group(1).strip()[:60]
                            return f"Element click intercepted: {element_info}"
                        return "Element click intercepted: Another element is covering the target element"
                    elif "not clickable" in exc_msg.lower():
                        point_match = re.search(r'not clickable at point\s+\(([^)]+)\)', exc_msg, re.IGNORECASE)
                        if point_match:
                            return f"Element not clickable at point {point_match.group(1)}"
                        return "Element not clickable: Another element is covering it"
                    elif "not found" in exc_msg.lower() or "nosuchelement" in exc_msg.lower():
                        return "Element not found in DOM"
                    elif "timeout" in exc_msg.lower():
                        return "Element timeout: Element did not appear within timeout period"
                    else:
                        # Return first meaningful part of exception message
                        sentences = exc_msg.split('.')
                        if sentences and len(sentences[0]) > 20:
                            return f"{pattern.split('[')[0].replace('Exception', '')}: {sentences[0].strip()[:80]}"
                        return f"{pattern.split('[')[0].replace('Exception', '')}: {exc_msg[:80]}"
        
        # Check for other specific exceptions (not Selenium)
        other_exceptions = [
            r'(\w+Exception)[:\s]+([^\n]{0,150})',
        ]
        # Only check if we haven't found a Selenium exception and if it's NOT AssertionError
        if "assertionerror" not in root_cause_lower[:200].lower():
            for pattern in other_exceptions:
                match = re.search(pattern, root_cause, re.IGNORECASE)
                if match:
                    exc_type = match.group(1)
                    exc_msg = match.group(2).strip() if len(match.groups()) > 1 else ""
                    # Skip AssertionError - we'll handle it separately
                    if exc_type != "AssertionError" and exc_type.endswith("Exception"):
                        if exc_msg:
                            sentences = exc_msg.split('.')
                            if sentences and len(sentences[0]) > 20:
                                return f"{exc_type}: {sentences[0].strip()[:80]}"
                            return f"{exc_type}: {exc_msg[:80]}"
                        return f"{exc_type} occurred"
        
        # Assertion failures - extract expected vs actual if available
        # Only treat as assertion failure if no specific exception was found above
        elif "assertionerror" in root_cause_lower or "assert" in root_cause_lower:
            # Try to extract expected/actual values
            expected_match = re.search(r'expected[:\s<>=]+([^\n,<]{0,40})', root_cause, re.IGNORECASE)
            actual_match = re.search(r'actual[:\s<>=]+([^\n,<]{0,40})', root_cause, re.IGNORECASE)
            
            if expected_match and actual_match:
                expected = expected_match.group(1).strip()[:30]
                actual = actual_match.group(1).strip()[:30]
                return f"Assertion failed: Expected '{expected}' but got '{actual}'"
            elif expected_match:
                return f"Assertion failed: Expected '{expected_match.group(1).strip()[:40]}'"
            else:
                # Extract the assertion message
                assert_msg = re.search(r'AssertionError[:\s]+([^\n]{0,80})', root_cause, re.IGNORECASE)
                if assert_msg:
                    return f"Assertion failed: {assert_msg.group(1).strip()[:70]}"
                return "Assertion failed - Expected value did not match actual value"
        
        # Connection/Network issues
        elif "connection" in root_cause_lower or "network" in root_cause_lower or "connection refused" in root_cause_lower:
            conn_match = re.search(r'(connection|connect|network)[\s]+(refused|timeout|failed|error)[:\s]+([^\n]{0,50})', root_cause, re.IGNORECASE)
            if conn_match:
                return f"Connection {conn_match.group(2)}: {conn_match.group(3).strip()[:50]}"
            return "Network or connection issue"
        
        # Missing key/data issues
        elif "missing" in root_cause_lower or "key" in root_cause_lower:
            key_match = re.search(r'(missing|key|field)[:\s]+([^\n,<]{0,50})', root_cause, re.IGNORECASE)
            if key_match:
                key_name = key_match.group(2).strip()
                if key_name:
                    return f"Missing required field/key: {key_name[:50]}"
            return "Missing required data or field"
        
        # Generic exception - extract exception type and message
        elif "exception" in root_cause_lower:
            exception_match = re.search(r'\b(\w+Exception)[:\s]+([^\n]{0,80})', root_cause)
            if exception_match:
                exc_type = exception_match.group(1)
                exc_msg = exception_match.group(2).strip()
                if exc_msg and len(exc_msg) > 10:
                    return f"{exc_type}: {exc_msg[:70]}"
                return f"{exc_type} occurred"
            return "Exception occurred during test execution"
        
        # If root cause is short and clear, use it as summary
        if len(root_cause) <= 120 and root_cause.count('.') < 3:
            return root_cause
        
        # Otherwise, extract first meaningful sentence
        sentences = root_cause.split('.')
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20 and len(sentence) <= 120:
                return sentence
        
        # Last resort: first 120 characters
        summary = root_cause[:120].strip()
        if summary.endswith(','):
            summary = summary[:-1]
        return summary + "..."
    
    def _extract_detailed_info(self, root_cause: str, execution_log: Optional[str] = None, test_name: Optional[str] = None) -> dict:
        """
        Extract structured information from root cause text.
        For API endpoints, only extracts the API that was executed just before the assertion failure.
        
        Args:
            root_cause: Root cause text
            execution_log: Optional full execution log to search for assertion failure point
            
        Returns:
            Dictionary with extracted details: api_info, status_codes, missing_keys, 
            expected_vs_actual, exceptions, locators, error_messages, stack_trace, etc.
        """
        details = {
            'api_info': [],
            'page_url': None,  # For UI tests - Page URL if no API found
            'status_codes': [],
            'missing_keys': [],
            'expected_vs_actual': None,
            'exceptions': [],
            'locators': [],
            'error_messages': [],
            'stack_trace': [],
            'assertion_details': None,
            'request_info': {},
            'response_info': {},
            'timeout_info': None
        }
        
        # Extract API endpoint that was executed just before the assertion failure
        # NEW APPROACH: Start from TOP, find FIRST failure, then backtrack to find API
        # Use execution_log if available, otherwise use root_cause
        log_text = execution_log if execution_log else root_cause
        lines = log_text.split('\n')
        
        # Find the FIRST assertion failure line (starting from top)
        # CRITICAL: ALWAYS skip summary lines like "The following asserts failed" - these are summaries, NOT individual failures
        # Summary lines can contain failure text patterns, so we MUST skip them completely before checking patterns
        failure_line_idx = -1
        
        # Search from TOP to find the FIRST individual failure (NOT summary lines)
        # IMPORTANT: We MUST stop at the FIRST failure we find, not continue searching
        for i in range(len(lines)):
            line = lines[i]
            
            # CRITICAL: Skip summary lines FIRST - before checking ANY failure patterns
            # Summary lines can contain failure text, so we must skip them first
            # Pattern 1: "[21:35:11] The following asserts failed:"
            # Pattern 2: "java.lang.AssertionError: The following asserts failed:"
            # Pattern 3: Any line containing "The following asserts failed" anywhere (case-insensitive)
            # Also check for partial matches like "The following asserts failed: Actual JSON..." (truncated)
            line_lower = line.lower()
            if "the following asserts failed" in line_lower:
                # This is a summary line - skip it completely, do NOT treat as failure
                # Continue to next line without checking patterns
                continue
            
            # Now check for actual individual failure patterns (only on non-summary lines)
            # Patterns include:
            # - "Expected 'X' was :-'Y'. But actual is 'Z'" (most specific - assertion mismatch)
            # - "Actual JSON doesn't contain all expected keys"
            # - "Missing keys" (with or without brackets, with or without dash)
            # - "Missing required" 
            # - "assertion failed"
            # - "AssertionError"
            # - Any line containing "Missing keys:" followed by a list
            
            # CRITICAL: Check for the most specific pattern first - "Expected ... But actual is"
            # This pattern indicates a clear assertion failure with expected vs actual values
            if re.search(r"Expected\s+['\"].*?['\"]\s+was\s*[:-].*?But\s+actual\s+is", line, re.IGNORECASE):
                if "the following asserts failed" not in line_lower:
                    failure_line_idx = i
                    break  # Found specific failure pattern, stop searching completely
            
            # Check other failure patterns
            failure_patterns = [
                r"Expected\s+['\"].*?['\"]\s+was\s*[:-]",  # "Expected 'X' was :-'Y'"
                r"But\s+actual\s+is",  # "But actual is" (standalone)
                r"Actual JSON doesn't contain all expected keys",
                r"Missing\s+keys?\s*[:-]",  # "Missing keys:" or "Missing keys -" pattern
                r"Missing\s+keys?\s*\[",  # "Missing keys: [...]" pattern
                r"Missing\s+required",  # "Missing required" pattern
                r"assertion failed",
                r"AssertionError"
            ]
            
            # Check each pattern - if found, mark as failure and STOP searching immediately
            pattern_matched = False
            for pattern in failure_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    # Double-check: ensure this is NOT a summary line (should already be skipped above, but extra safety)
                    # Use case-insensitive check to catch all variations
                    if "the following asserts failed" not in line_lower:
                        failure_line_idx = i
                        pattern_matched = True
                        break  # Found failure, stop checking patterns
            
            # CRITICAL: If we found a failure, STOP searching immediately - don't continue to find more failures
            if pattern_matched:
                break  # Found first individual failure (not summary), stop searching completely
        
        # If we found a failure point, look backwards for the API endpoint
        api_found_from_log = False  # Track if we found API from execution_log
        if failure_line_idx >= 0:
            # Look backwards from failure point to find the API executed just before the failure
            # Strategy: Check BOTH patterns simultaneously on each line and pick whichever is found FIRST (closest to failure)
            # This ensures we get the API that was executed immediately before the failure, not a different API
            
            api_endpoint = None
            api_found_at_idx = -1
            
            # Search backwards from failure point (up to 200 lines back to catch APIs that happened earlier)
            # CRITICAL: Only search lines BEFORE the failure point, and skip ALL summary lines
            # Strategy: Stop at the FIRST API found (Option 1 or Option 2, whichever comes first when backtracking)
            # This ensures we get the API that was executed immediately before the failure
            api_endpoint = None
            api_found_at_idx = -1
            
            for i in range(failure_line_idx - 1, max(-1, failure_line_idx - 200), -1):
                if i < 0:
                    break
                
                # CRITICAL SAFETY CHECK: Ensure we're ONLY looking at lines BEFORE the failure
                if i >= failure_line_idx:
                    logger.warning(f"Unexpected: API search found line {i} >= failure_line_idx {failure_line_idx}, skipping")
                    continue
                    
                line = lines[i]
                
                # CRITICAL: Skip summary lines when searching backwards
                # Summary lines are NOT actual failures and should NEVER be used for API extraction
                line_lower_backtrack = line.lower()
                if "the following asserts failed" in line_lower_backtrack:
                    # Skip this summary line completely, continue to next line
                    continue
                
                # Check BOTH patterns on the same line - prefer "Response time for" pattern (Option 1)
                # Pattern 1: "Response time for /dashboard/..." (preferred when available)
                # Example: "[21:34:29] Response time for /dashboard/businesses/{$businessUuid} is 5s"
                response_time_match = re.search(r'Response\s+time\s+for\s+([^\s\n]+)', line, re.IGNORECASE)
                if not response_time_match:
                    # Try alternative pattern in case format is slightly different
                    response_time_match = re.search(r'Response\s+time\s+for\s+(/[^\s\n]+)', line, re.IGNORECASE)
                
                # Pattern 2: "Executing Api = GET/POST/PUT/DELETE https://..." (Option 2 - fallback)
                # Example: "[21:34:24] Executing Api = GET https://qa-1-api.qa.example.com/dashboard/businesses/996be438..."
                executing_match = re.search(r'Executing\s+Api\s*=\s*(GET|POST|PUT|DELETE|PATCH)\s+([^\s\n]+)', line, re.IGNORECASE)
                
                # Prefer Option 1 (Response time) if both are found on the same line
                if response_time_match:
                    # Found Option 1 - extract and stop immediately (this is the closest API)
                    potential_api = response_time_match.group(1).strip()
                    # Clean up the endpoint (replace UUIDs and IDs with placeholders)
                    # Note: If the log already contains placeholders like {$businessUuid}, preserve them as-is
                    if not re.search(r'\{[^}]+\}', potential_api):  # Only replace if no placeholders exist
                        # Replace UUIDs (36-character hex strings with dashes)
                        potential_api = re.sub(r'/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?=/|$)', '/{$uuid}', potential_api, flags=re.IGNORECASE)
                        # Replace any remaining UUID-like patterns
                        potential_api = re.sub(r'/[a-f0-9-]{36}(?=/|$)', '/{$uuid}', potential_api, flags=re.IGNORECASE)
                        # Replace numeric IDs
                        potential_api = re.sub(r'/\d+(?=/|$)', '/{$id}', potential_api)
                    # If placeholders already exist (like {$businessUuid}), keep them as-is - don't normalize
                    api_endpoint = potential_api
                    api_found_at_idx = i
                    break  # Found first API (Option 1), stop searching
                elif executing_match:
                    # Found Option 2 - extract path and stop immediately (this is the closest API)
                    method = executing_match.group(1).strip()
                    url = executing_match.group(2).strip()
                    # Extract just the path from the URL
                    path_match = re.search(r'(https?://[^/]+)?(/[^\s\n?]+)', url)
                    if path_match:
                        potential_api = path_match.group(2).strip()
                        # Clean up the endpoint (remove query params and replace UUIDs/IDs)
                        potential_api = re.sub(r'\?.*$', '', potential_api)  # Remove query params
                        # Replace UUIDs (36-character hex strings with dashes)
                        potential_api = re.sub(r'/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?=/|$)', '/{$uuid}', potential_api, flags=re.IGNORECASE)
                        # Replace any remaining UUID-like patterns
                        potential_api = re.sub(r'/[a-f0-9-]{36}(?=/|$)', '/{$uuid}', potential_api, flags=re.IGNORECASE)
                        # Replace numeric IDs
                        potential_api = re.sub(r'/\d+(?=/|$)', '/{$id}', potential_api)
                        api_endpoint = potential_api
                        api_found_at_idx = i
                        break  # Found first API (Option 2), stop searching
            
            if api_endpoint:
                # CRITICAL SAFETY CHECK: Ensure the API we found is BEFORE the failure point
                # This should always be true since we search backwards, but verify to prevent bugs
                if api_found_at_idx >= failure_line_idx:
                    logger.warning(f"BUG DETECTED: Found API at line {api_found_at_idx} >= failure_line_idx {failure_line_idx}. Skipping this API.")
                    api_endpoint = None
                else:
                    details['api_info'].append(api_endpoint)
                    # Mark that we found API from execution_log so we skip fallback
                    api_found_from_log = True
        
        # Check for Page URL (UI tests) - always extract if available
        # Extract Page URL from logs using pattern: "[00:18:17] Page URL:- https://app.example.com/..."
        # This is important for ELEMENT_NOT_FOUND and TIMEOUT categories which should show Page URL, not API
        if execution_log:
            page_url_pattern = r'Page URL[:\s-]+([^\s\n]+)'
            page_url_match = re.search(page_url_pattern, execution_log, re.IGNORECASE)
            if page_url_match:
                details['page_url'] = page_url_match.group(1).strip()
        
        # Fallback: If no failure point found or no API found, extract from root_cause text (for backward compatibility)
        # CRITICAL: Only use fallback if we didn't find an API from execution_log AND no page_url found
        # This ensures we use the correct API from logs, not incorrect ones from root_cause
        # If api_found_from_log is True, we found an API from logs, so skip fallback completely
        if not details['api_info'] and not api_found_from_log and not details['page_url']:
            api_patterns = [
                r'\b(POST|GET|PUT|DELETE|PATCH)\s+([^\s,<>\n]+)',
                r'(API Name|Endpoint|api name|api url|url)[:\s]+([^\s,<>\n]+)',
                r'(https?://[^\s]+|/api/[^\s]+|/dashboard/[^\s]+)',
            ]
            for pattern in api_patterns:
                matches = re.finditer(pattern, root_cause, re.IGNORECASE)
                for match in matches:
                    if len(match.groups()) > 1:
                        api = match.group(2).strip()
                    else:
                        api = match.group(1).strip()
                    # Skip if this looks like a partial match (e.g., just "/dashboard/auth" without full path)
                    # Prefer longer, more specific paths
                    if api and api not in details['api_info']:
                        # Only add if it's a full path (contains at least 2 segments) or is a full URL
                        if '/' in api and (api.count('/') >= 2 or api.startswith('http')):
                            details['api_info'].append(api)
                            break  # Only take the first one as fallback
        
        # Extract HTTP status codes
        status_matches = re.finditer(r'\b(40[0-9]|50[0-9]|20[0-9]|30[0-9])\b', root_cause)
        for match in status_matches:
            status = match.group(1)
            if status not in details['status_codes']:
                details['status_codes'].append(status)
        
        # Extract missing keys (Expected vs Actual) - Try multiple patterns
        # First, try to find both Expected and Actual in root_cause
        search_text_for_keys = root_cause
        if execution_log:
            # Also search in execution_log for Expected/Actual patterns
            search_text_for_keys = root_cause + "\n" + execution_log
        
        expected_actual_match = re.search(r"Expected\s+(?:keys|has)[:\s]+'?\[([^\]]+)\]'?.*?(?:but\s+)?Actual\s+(?:keys|has)[:\s]+'?\[([^\]]+)\]'?", search_text_for_keys, re.IGNORECASE | re.DOTALL)
        if expected_actual_match:
            expected_keys_str = expected_actual_match.group(1).strip()
            actual_keys_str = expected_actual_match.group(2).strip()
            expected_keys = [k.strip().strip("'\"") for k in expected_keys_str.split(',') if k.strip()]
            actual_keys = [k.strip().strip("'\"") for k in actual_keys_str.split(',') if k.strip()]
            missing_keys = [k for k in expected_keys if k not in actual_keys]
            if missing_keys:
                details['expected_vs_actual'] = {
                    'expected': expected_keys,
                    'actual': actual_keys,
                    'missing': missing_keys
                }
        
        # Extract "Missing keys: [...]" pattern - Try to find Expected keys elsewhere
        missing_keys_match = re.search(r'Missing\s+keys?[:\s]+\[([^\]]+)\]', root_cause, re.IGNORECASE)
        if missing_keys_match:
            missing_keys_str = missing_keys_match.group(1).strip()
            missing_keys = [k.strip().strip("'\"") for k in missing_keys_str.split(',') if k.strip()]
            details['missing_keys'].extend(missing_keys)
            
            # If we have missing keys but no expected_vs_actual, try to find Expected keys from other patterns
            # Search in both root_cause and execution_log
            if missing_keys and not details['expected_vs_actual']:
                # Try to find Expected keys pattern separately
                expected_only_match = re.search(r"Expected\s+(?:keys|has|should have|must have)[:\s]+'?\[([^\]]+)\]'?", search_text_for_keys, re.IGNORECASE)
                # Try to find Actual keys pattern separately
                actual_only_match = re.search(r"Actual\s+(?:keys|has|contains)[:\s]+'?\[([^\]]+)\]'?", search_text_for_keys, re.IGNORECASE)
                
                if expected_only_match and actual_only_match:
                    expected_keys_str = expected_only_match.group(1).strip()
                    actual_keys_str = actual_only_match.group(1).strip()
                    expected_keys = [k.strip().strip("'\"") for k in expected_keys_str.split(',') if k.strip()]
                    actual_keys = [k.strip().strip("'\"") for k in actual_keys_str.split(',') if k.strip()]
                    # Recalculate missing keys from both lists
                    calculated_missing = [k for k in expected_keys if k not in actual_keys]
                    if calculated_missing:
                        details['expected_vs_actual'] = {
                            'expected': expected_keys,
                            'actual': actual_keys,
                            'missing': calculated_missing
                        }
                elif expected_only_match:
                    # We have Expected keys but no Actual - use missing_keys as the difference
                    expected_keys_str = expected_only_match.group(1).strip()
                    expected_keys = [k.strip().strip("'\"") for k in expected_keys_str.split(',') if k.strip()]
                    # Actual keys = Expected - Missing
                    actual_keys = [k for k in expected_keys if k not in missing_keys]
                    if expected_keys and actual_keys:
                        details['expected_vs_actual'] = {
                            'expected': expected_keys,
                            'actual': actual_keys,
                            'missing': missing_keys
                        }
                elif actual_only_match:
                    # We have Actual keys but no Expected - use missing_keys to infer Expected
                    actual_keys_str = actual_only_match.group(1).strip()
                    actual_keys = [k.strip().strip("'\"") for k in actual_keys_str.split(',') if k.strip()]
                    # Expected keys = Actual + Missing
                    expected_keys = actual_keys + missing_keys
                    if expected_keys and actual_keys:
                        details['expected_vs_actual'] = {
                            'expected': expected_keys,
                            'actual': actual_keys,
                            'missing': missing_keys
                        }
        
        # Also check for patterns like "Expected has: [...] but Actual has: [...]" (without "keys")
        # Search in both root_cause and execution_log
        if not details['expected_vs_actual']:
            expected_actual_match2 = re.search(r"Expected\s+has[:\s]+'?\[([^\]]+)\]'?.*?(?:but\s+)?Actual\s+has[:\s]+'?\[([^\]]+)\]'?", search_text_for_keys, re.IGNORECASE | re.DOTALL)
            if expected_actual_match2:
                expected_keys_str = expected_actual_match2.group(1).strip()
                actual_keys_str = expected_actual_match2.group(2).strip()
                expected_keys = [k.strip().strip("'\"") for k in expected_keys_str.split(',') if k.strip()]
                actual_keys = [k.strip().strip("'\"") for k in actual_keys_str.split(',') if k.strip()]
                missing_keys = [k for k in expected_keys if k not in actual_keys]
                if missing_keys:
                    details['expected_vs_actual'] = {
                        'expected': expected_keys,
                        'actual': actual_keys,
                        'missing': missing_keys
                    }
        
        # Extract error messages
        error_patterns = [
            r'(Error|Exception|Failed)[:\s]+([^\n]{0,200})',
            r'(error|exception|failed)[:\s]+([^\n]{0,200})',
        ]
        for pattern in error_patterns:
            matches = re.finditer(pattern, root_cause, re.IGNORECASE)
            for match in matches:
                error_msg = match.group(2).strip()
                if error_msg and len(error_msg) > 10 and error_msg not in details['error_messages']:
                    details['error_messages'].append(error_msg[:300])
        
        # Extract locators (only valid ones)
        locator_patterns = [
            r'(Locator|Selector|Element)[:\s=]+([#.a-zA-Z0-9_/-]+)',
            r'([#.a-zA-Z0-9_/-]+)\s+(not found|could not be found|was not found)',
        ]
        for pattern in locator_patterns:
            matches = re.finditer(pattern, root_cause, re.IGNORECASE)
            for match in matches:
                locator = match.group(2) if len(match.groups()) > 1 else match.group(1)
                # Only add if it looks like a valid locator
                if locator and locator not in details['locators']:
                    if locator.startswith(('#', '.', '/', '//')) or '=' in locator:
                        details['locators'].append(locator)
        
        # Extract exceptions
        exception_matches = re.finditer(r'\b(\w+Exception)[:\s]+([^\n]{0,200})', root_cause)
        for match in exception_matches:
            exc_type = match.group(1)
            exc_msg = match.group(2).strip() if len(match.groups()) > 1 else ""
            if exc_type not in [e['type'] for e in details['exceptions']]:
                details['exceptions'].append({'type': exc_type, 'message': exc_msg[:300]})
        
        # Extract assertion details (Expected vs Actual values)
        assertion_match = re.search(r"(?:Expected|Expected value|Expected:)\s*'?([^']+)'?\s*(?:was|but got|but actual is|but Actual:)\s*'?([^']+)'?", root_cause, re.IGNORECASE | re.DOTALL)
        if assertion_match:
            details['assertion_details'] = {
                'expected': assertion_match.group(1).strip(),
                'actual': assertion_match.group(2).strip()
            }
        
        # Extract Request Info
        request_url_match = re.search(r'(?:Request URL|URL)[:\s]+(https?://[^\s\n]+)', root_cause, re.IGNORECASE)
        request_method_match = re.search(r'(?:Request Method|Method)[:\s]+(POST|GET|PUT|DELETE|PATCH)', root_cause, re.IGNORECASE)
        request_body_match = re.search(r'(?:Request Body|Body)[:\s]+(\{.*?\})', root_cause, re.IGNORECASE | re.DOTALL)
        if request_url_match:
            details['request_info']['url'] = request_url_match.group(1).strip()
        if request_method_match:
            details['request_info']['method'] = request_method_match.group(1).strip()
        if request_body_match:
            details['request_info']['body'] = request_body_match.group(1).strip()
        
        # Extract Response Info
        response_body_match = re.search(r'(?:Response Body|Body)[:\s]+(\{.*?\})', root_cause, re.IGNORECASE | re.DOTALL)
        response_status_match = re.search(r'(?:Response Status|Status)[:\s]+(\d{3})', root_cause, re.IGNORECASE)
        response_headers_match = re.search(r'(?:Response Headers|Headers)[:\s]+(\{.*?\})', root_cause, re.IGNORECASE | re.DOTALL)
        if response_body_match:
            details['response_info']['body'] = response_body_match.group(1).strip()
        if response_status_match:
            details['response_info']['status'] = response_status_match.group(1).strip()
        if response_headers_match:
            details['response_info']['headers'] = response_headers_match.group(1).strip()
        
        # Extract timeout information
        timeout_match = re.search(r'timeout[:\s]+(\d+)\s*(second|sec|ms|millisecond|minute)', root_cause, re.IGNORECASE)
        if timeout_match:
            details['timeout_info'] = {
                'duration': timeout_match.group(1),
                'unit': timeout_match.group(2)
            }
        
        # Extract stack trace (look for "at" patterns)
        stack_trace_lines = []
        lines = root_cause.split('\n')
        in_stack_trace = False
        for line in lines:
            if re.search(r'\s+at\s+[\w.]+\([^)]+\)', line) or 'Exception' in line:
                in_stack_trace = True
            if in_stack_trace:
                if line.strip() and (re.search(r'\s+at\s+', line) or 'Exception' in line or 'Caused by' in line):
                    stack_trace_lines.append(line.strip()[:200])
                    if len(stack_trace_lines) >= 5:
                        break
        
        if stack_trace_lines:
            details['stack_trace'] = stack_trace_lines
        
        return details
    
    def _format_root_cause_and_action(self, root_cause: str, action: str, execution_log: Optional[str] = None, test_results: Optional[List] = None, test_name: Optional[str] = None) -> str:
        """
        Format root cause and action with comprehensive details and clear actions.
        Shows structured information with clear sections including Key Comparison table.
        
        Args:
            root_cause: Root cause text
            action: Recommended action text
            execution_log: Optional full execution log to search for Expected/Actual keys
            
        Returns:
            Formatted HTML string
        """
        # Combine root_cause, execution_log, and other error sources for comprehensive extraction
        # CRITICAL: Check execution_log, stack_trace, and error_message for exceptions FIRST
        # Exceptions may be in stack_trace or error_message, not just execution_log
        search_text = root_cause
        
        # Also check test_results for additional error information (stack_trace, error_message)
        # These often contain the actual exception details, especially from CSV parser
        additional_error_text = ""
        if test_results:
            # Try to find matching test result to get stack_trace and error_message
            # Extract test name from root_cause if possible
            test_name_match = re.search(r"test\s+'?([^']+)'?|Test:\s+([^\n]+)|'([^']+)'", root_cause, re.IGNORECASE)
            if test_name_match:
                potential_test_name = test_name_match.group(1) or test_name_match.group(2) or test_name_match.group(3)
                # Find matching test result - try multiple matching strategies
                for result in test_results:
                    # Match by method name, class name, or full name
                    if (potential_test_name in result.full_name or 
                        result.full_name in potential_test_name or
                        potential_test_name in result.method_name or
                        potential_test_name in result.class_name):
                        if result.stack_trace:
                            additional_error_text += "\n\n" + result.stack_trace
                        if result.error_message:
                            additional_error_text += "\n\n" + result.error_message
                        break
        
        if execution_log and execution_log not in root_cause:
            search_text = root_cause + "\n\n" + execution_log
        
        if additional_error_text:
            search_text = search_text + additional_error_text
        
        # Extract structured details FIRST to get the corrected API endpoint
        # Pass execution_log separately so API extraction can find the failure point in full logs
        # Also pass test_name to help identify TestDashAmlApis tests that fail due to dashboard/businesses
        # Use test_name parameter if provided, otherwise try to extract from test_results
        test_name_for_extraction = test_name  # Use parameter first
        if not test_name_for_extraction and test_results:
            # Try to extract test name from root_cause or use first matching test result
            test_name_match = re.search(r"test\s+'?([^']+)'?|Test:\s+([^\n]+)|'([^']+)'", root_cause, re.IGNORECASE)
            if test_name_match:
                potential_test_name = test_name_match.group(1) or test_name_match.group(2) or test_name_match.group(3)
                for result in test_results:
                    if potential_test_name in result.full_name or result.full_name in potential_test_name:
                        test_name_for_extraction = result.full_name
                        break
        
        details_info = self._extract_detailed_info(search_text, execution_log=execution_log, test_name=test_name_for_extraction)
        
        # Extract one-liner summary - use combined text to catch exceptions in all sources
        # CRITICAL: Pass details_info so summary can use the corrected API endpoint instead of root_cause
        summary = html_escape.escape(self._extract_one_liner_summary(search_text, details_info=details_info))
        
        # ENHANCEMENT: Try to enhance expected_vs_actual if we have missing_keys and API info but no comparison yet
        # Search in both root_cause and execution_log for Expected/Actual patterns
        search_text_for_enhancement = search_text
        if execution_log:
            search_text_for_enhancement = search_text + "\n" + execution_log
            
        if details_info['missing_keys'] and not details_info['expected_vs_actual'] and details_info['api_info']:
            # Try to extract Expected and Actual keys separately from search_text (including execution_log)
            expected_patterns = [
                r"Expected\s+(?:keys|has|should have|must have)[:\s]+'?\[([^\]]+)\]'?",
                r"Expected[:\s]+'?\[([^\]]+)\]'?",
                r"Expected\s+keys[:\s]+'?\[([^\]]+)\]'?",
            ]
            expected_keys = []
            for pattern in expected_patterns:
                match = re.search(pattern, search_text_for_enhancement, re.IGNORECASE)
                if match:
                    expected_keys_str = match.group(1).strip()
                    expected_keys = [k.strip().strip("'\"") for k in expected_keys_str.split(',') if k.strip()]
                    if expected_keys:
                        break
            
            actual_patterns = [
                r"Actual\s+(?:keys|has|contains)[:\s]+'?\[([^\]]+)\]'?",
                r"Actual[:\s]+'?\[([^\]]+)\]'?",
                r"Actual\s+keys[:\s]+'?\[([^\]]+)\]'?",
            ]
            actual_keys = []
            for pattern in actual_patterns:
                match = re.search(pattern, search_text_for_enhancement, re.IGNORECASE)
                if match:
                    actual_keys_str = match.group(1).strip()
                    actual_keys = [k.strip().strip("'\"") for k in actual_keys_str.split(',') if k.strip()]
                    if actual_keys:
                        break
            
            # If we found both, create expected_vs_actual
            if expected_keys and actual_keys:
                calculated_missing = [k for k in expected_keys if k not in actual_keys]
                details_info['expected_vs_actual'] = {
                    'expected': expected_keys,
                    'actual': actual_keys,
                    'missing': calculated_missing if calculated_missing else details_info['missing_keys']
                }
            elif expected_keys:
                actual_keys = [k for k in expected_keys if k not in details_info['missing_keys']]
                if actual_keys:
                    details_info['expected_vs_actual'] = {
                        'expected': expected_keys,
                        'actual': actual_keys,
                        'missing': details_info['missing_keys']
                    }
            elif actual_keys:
                expected_keys = actual_keys + details_info['missing_keys']
                details_info['expected_vs_actual'] = {
                    'expected': expected_keys,
                    'actual': actual_keys,
                    'missing': details_info['missing_keys']
                }
        
        # Build Details section with structured information
        details_sections = []
        
        # API Information or Page URL (for UI tests)
        # CRITICAL: For ELEMENT_NOT_FOUND and TIMEOUT categories, NEVER show API, only Page URL
        # Note: category is not available in this function, so we check page_url first
        # If page_url exists, it means it's likely a UI test (ELEMENT_NOT_FOUND/TIMEOUT)
        if details_info.get('page_url'):
            # UI test - show Page URL instead of API Endpoint
            page_url_escaped = html_escape.escape(details_info['page_url'])
            details_sections.append(f"<div style='margin-bottom: 8px;'><b>Page:</b> <code style='background: #e3f2fd; padding: 2px 6px; border-radius: 3px;'>{page_url_escaped}</code></div>")
        elif details_info['api_info']:
            # Only show API if no page_url (not ELEMENT_NOT_FOUND/TIMEOUT)
            api_list = ', '.join([html_escape.escape(api) for api in details_info['api_info'][:5]])
            if len(details_info['api_info']) > 5:
                api_list += f" <span style='color: #6c757d;'>(+{len(details_info['api_info']) - 5} more)</span>"
            details_sections.append(f"<div style='margin-bottom: 8px;'><b>API Endpoint(s):</b> <code style='background: #e3f2fd; padding: 2px 6px; border-radius: 3px;'>{api_list}</code></div>")
        
        # Missing Keys (Expected vs Actual) - Enhanced with comparison table
        if details_info['expected_vs_actual']:
            exp_act = details_info['expected_vs_actual']
            missing_list = ', '.join([html_escape.escape(k) for k in exp_act['missing'][:15]])
            if len(exp_act['missing']) > 15:
                missing_list += f" <span style='color: #6c757d;'>(+{len(exp_act['missing']) - 15} more)</span>"
            
            # Create a comparison table
            comparison_html = f"""
                <div style='margin-bottom: 12px;'>
                    <b>Key Comparison:</b>
                    <table style='width: 100%; border-collapse: collapse; margin-top: 6px; font-size: 11px;'>
                        <tr style='background: #f8f9fa;'>
                            <th style='padding: 6px; text-align: left; border: 1px solid #dee2e6;'>Expected Keys ({len(exp_act['expected'])})</th>
                            <th style='padding: 6px; text-align: left; border: 1px solid #dee2e6;'>Actual Keys ({len(exp_act['actual'])})</th>
                            <th style='padding: 6px; text-align: left; border: 1px solid #dee2e6; color: #dc3545;'>Missing Keys ({len(exp_act['missing'])})</th>
                        </tr>
                        <tr>
                            <td style='padding: 6px; border: 1px solid #dee2e6; vertical-align: top;'>
                                <div style='max-height: 75px; overflow-y: auto;'>
                                    {', '.join([f"<code style='background: #e3f2fd; padding: 1px 4px; border-radius: 2px;'>{html_escape.escape(k)}</code>" for k in exp_act['expected'][:20]])}
                                    {f"<span style='color: #6c757d;'> (+{len(exp_act['expected']) - 20} more)</span>" if len(exp_act['expected']) > 20 else ""}
                                </div>
                            </td>
                            <td style='padding: 6px; border: 1px solid #dee2e6; vertical-align: top;'>
                                <div style='max-height: 75px; overflow-y: auto;'>
                                    {', '.join([f"<code style='background: #d4edda; padding: 1px 4px; border-radius: 2px;'>{html_escape.escape(k)}</code>" for k in exp_act['actual'][:20]])}
                                    {f"<span style='color: #6c757d;'> (+{len(exp_act['actual']) - 20} more)</span>" if len(exp_act['actual']) > 20 else ""}
                                </div>
                            </td>
                            <td style='padding: 6px; border: 1px solid #dee2e6; vertical-align: top; background: #fff3cd;'>
                                <div style='max-height: 75px; overflow-y: auto;'>
                                    {', '.join([f"<code style='background: #f8d7da; padding: 1px 4px; border-radius: 2px; color: #721c24;'>{html_escape.escape(k)}</code>" for k in exp_act['missing'][:20]])}
                                    {f"<span style='color: #6c757d;'> (+{len(exp_act['missing']) - 20} more)</span>" if len(exp_act['missing']) > 20 else ""}
                                </div>
                            </td>
                        </tr>
                    </table>
                </div>
            """
            details_sections.append(comparison_html)
        
        # Missing Keys (simple pattern) - Only show if we don't have comparison table
        if details_info['missing_keys'] and not details_info['expected_vs_actual']:
            missing_list = ', '.join([html_escape.escape(k) for k in details_info['missing_keys'][:15]])
            if len(details_info['missing_keys']) > 15:
                missing_list += f" <span style='color: #6c757d;'>(+{len(details_info['missing_keys']) - 15} more)</span>"
            details_sections.append(f"<div style='margin-bottom: 8px;'><b>Missing Keys:</b> {missing_list}</div>")
        
        # Assertion Mismatch
        if details_info['assertion_details']:
            assertion_html = f"""
                <div style='margin-bottom: 8px;'>
                    <b>Assertion Mismatch:</b><br/>
                    <span style='color: #dc3545;'>Expected: '{html_escape.escape(details_info['assertion_details']['expected'])}'</span><br/>
                    <span style='color: #ffc107;'>Actual: '{html_escape.escape(details_info['assertion_details']['actual'])}'</span>
                </div>
            """
            details_sections.append(assertion_html)
        
        # Request Information
        if details_info['request_info']:
            req_info_html = "<b>Request Info:</b><ul style='margin: 0; padding-left: 20px;'>"
            if details_info['request_info'].get('method'):
                req_info_html += f"<li>Method: <code style='background: #e3f2fd; padding: 1px 4px; border-radius: 2px;'>{html_escape.escape(details_info['request_info']['method'])}</code></li>"
            if details_info['request_info'].get('url'):
                req_info_html += f"<li>URL: <code style='background: #e3f2fd; padding: 1px 4px; border-radius: 2px;'>{html_escape.escape(details_info['request_info']['url'])}</code></li>"
            if details_info['request_info'].get('body'):
                req_info_html += f"<li>Body: <pre style='background: #f8f9fa; padding: 5px; border-radius: 3px; max-height: 100px; overflow-y: auto; font-size: 11px;'>{html_escape.escape(details_info['request_info']['body'])}</pre></li>"
            req_info_html += "</ul>"
            details_sections.append(f"<div style='margin-bottom: 8px;'>{req_info_html}</div>")
        
        # Response Information
        if details_info['response_info']:
            res_info_html = "<b>Response Info:</b><ul style='margin: 0; padding-left: 20px;'>"
            if details_info['response_info'].get('status'):
                res_info_html += f"<li>Status: <b style='color: #dc3545;'>{html_escape.escape(details_info['response_info']['status'])}</b></li>"
            if details_info['response_info'].get('body'):
                res_info_html += f"<li>Body: <pre style='background: #f8f9fa; padding: 5px; border-radius: 3px; max-height: 100px; overflow-y: auto; font-size: 11px;'>{html_escape.escape(details_info['response_info']['body'])}</pre></li>"
            if details_info['response_info'].get('headers'):
                res_info_html += f"<li>Headers: <pre style='background: #f8f9fa; padding: 5px; border-radius: 3px; max-height: 100px; overflow-y: auto; font-size: 11px;'>{html_escape.escape(details_info['response_info']['headers'])}</pre></li>"
            res_info_html += "</ul>"
            details_sections.append(f"<div style='margin-bottom: 8px;'>{res_info_html}</div>")
        
        # Exceptions
        if details_info['exceptions']:
            exc_list = []
            for exc in details_info['exceptions'][:3]:
                exc_html = f"<b>{html_escape.escape(exc['type'])}</b>"
                if exc['message']:
                    exc_html += f": {html_escape.escape(exc['message'][:150])}"
                exc_list.append(exc_html)
            if len(details_info['exceptions']) > 3:
                exc_list.append(f"<span style='color: #6c757d;'>(+{len(details_info['exceptions']) - 3} more exceptions)</span>")
            details_sections.append(f"<div style='margin-bottom: 8px;'><b>Exception(s):</b> {' | '.join(exc_list)}</div>")
        
        # Locators (only valid ones)
        if details_info['locators']:
            locator_list = ', '.join([f"<code style='background: #fff3cd; padding: 2px 6px; border-radius: 3px;'>{html_escape.escape(loc)}</code>" for loc in details_info['locators'][:5]])
            if len(details_info['locators']) > 5:
                locator_list += f" <span style='color: #6c757d;'>(+{len(details_info['locators']) - 5} more)</span>"
            details_sections.append(f"<div style='margin-bottom: 8px;'><b>Element Locator(s):</b> {locator_list}</div>")
        
        # Timeout Information
        if details_info['timeout_info']:
            timeout_html = f"<b>Timeout:</b> {html_escape.escape(details_info['timeout_info']['duration'])} {html_escape.escape(details_info['timeout_info']['unit'])}s"
            details_sections.append(f"<div style='margin-bottom: 8px;'>{timeout_html}</div>")
        
        # Stack Trace
        if details_info['stack_trace']:
            stack_trace_html = "<div style='margin-bottom: 8px;'><b>Stack Trace (Top 5 lines):</b><pre style='background: #f8f9fa; padding: 5px; border-radius: 3px; max-height: 150px; overflow-y: auto; font-size: 11px; color: #dc3545; border-left: 3px solid #dc3545;'><code>"
            stack_trace_html += html_escape.escape('\n'.join(details_info['stack_trace']))
            stack_trace_html += "</code></pre></div>"
            details_sections.append(stack_trace_html)
        
        # Error Messages
        if details_info['error_messages']:
            error_list_html = "<div style='margin-bottom: 8px;'><b>Error Message(s):</b><ul style='margin: 0; padding-left: 20px;'>"
            for err in details_info['error_messages'][:3]:
                error_list_html += f"<li><span style='color: #dc3545;'>{html_escape.escape(err)}</span></li>"
            if len(details_info['error_messages']) > 3:
                error_list_html += f"<li><span style='color: #6c757d;'>(+{len(details_info['error_messages']) - 3} more)</span></li>"
            error_list_html += "</ul></div>"
            details_sections.append(error_list_html)
        
        # Full Root Cause Text (if no structured info extracted, or as additional context)
        # Skip "Complete Error Details" if Key Comparison table is shown (to avoid duplication)
        has_key_comparison = bool(details_info['expected_vs_actual'])
        
        # Remove "API Name: ..." from root_cause text since API is already shown separately and may be incorrect
        cleaned_root_cause = root_cause
        # Pattern: "API Name: /dashboard/..." or "API Name: GetAmlSearchSuccessfulResponse"
        api_name_pattern = r'(API Name|Endpoint|api name|api url|url)[:\s]+([^\s,<>\n]+)'
        cleaned_root_cause = re.sub(api_name_pattern, '', cleaned_root_cause, flags=re.IGNORECASE)
        # Clean up any double commas or spaces left after removal
        cleaned_root_cause = re.sub(r',\s*,', ',', cleaned_root_cause)  # Remove double commas
        cleaned_root_cause = re.sub(r'\s+', ' ', cleaned_root_cause)  # Normalize whitespace
        cleaned_root_cause = cleaned_root_cause.strip()
        # Remove leading comma or space if present
        cleaned_root_cause = re.sub(r'^[,\s]+', '', cleaned_root_cause)
        
        if not details_sections or len(details_sections) < 3:
            escaped_rc = html_escape.escape(cleaned_root_cause)
            escaped_rc = re.sub(r'\b(POST|GET|PUT|DELETE|PATCH)\s+([^\s<>]+)', r'<b>\1 \2</b>', escaped_rc, flags=re.IGNORECASE)
            escaped_rc = re.sub(r'\b(\d{3})\s+(status|code|response|error)', r'<b>\1</b> \2', escaped_rc, flags=re.IGNORECASE)
            escaped_rc = re.sub(r'\b(\w+Exception)', r'<b>\1</b>', escaped_rc)
            escaped_rc = re.sub(r'\b(40[0-9]|50[0-9]|20[0-9])\b', r'<b>\1</b>', escaped_rc)
            details_sections.append(f"<div style='margin-top: 12px; padding-top: 12px; border-top: 1px solid #e9ecef;'><b>Full Error Details:</b><div style='margin-top: 6px; color: #495057; line-height: 1.6; font-size: 12px; white-space: pre-wrap;'>{escaped_rc}</div></div>")
        elif not has_key_comparison:
            # Only show "Complete Error Details" if Key Comparison table is NOT present
            escaped_rc = html_escape.escape(cleaned_root_cause)
            escaped_rc = re.sub(r'\b(POST|GET|PUT|DELETE|PATCH)\s+([^\s<>]+)', r'<b>\1 \2</b>', escaped_rc, flags=re.IGNORECASE)
            escaped_rc = re.sub(r'\b(\d{3})\s+(status|code|response|error)', r'<b>\1</b> \2', escaped_rc, flags=re.IGNORECASE)
            escaped_rc = re.sub(r'\b(\w+Exception)', r'<b>\1</b>', escaped_rc)
            escaped_rc = re.sub(r'\b(40[0-9]|50[0-9]|20[0-9])\b', r'<b>\1</b>', escaped_rc)
            details_sections.append(f"<div style='margin-top: 12px; padding-top: 12px; border-top: 1px solid #e9ecef;'><b>Complete Error Details:</b><div style='margin-top: 6px; color: #495057; line-height: 1.6; font-size: 12px; white-space: pre-wrap; max-height: 300px; overflow-y: auto;'>{escaped_rc}</div></div>")
        
        # Format Action section - keep it simple and consistent
        escaped_action = html_escape.escape(action)
        formatted_action = escaped_action
        
        # Build final HTML
        details_html = ''.join(details_sections) if details_sections else f"<div style='color: #495057; line-height: 1.6; font-size: 12px; white-space: pre-wrap;'>{html_escape.escape(root_cause)}</div>"
        
        return f"""
            <div style="margin-bottom: 12px;">
                <div style="font-weight: 600; color: #2c3e50; margin-bottom: 6px; font-size: 14px;">Summary:</div>
                <div style="color: #495057; line-height: 1.5; font-weight: 500; background: #f8f9fa; padding: 8px; border-radius: 4px; border-left: 3px solid #3498db;">{summary}</div>
            </div>
            <div style="margin-bottom: 12px;">
                <div style="font-weight: 600; color: #2c3e50; margin-bottom: 8px; font-size: 13px;">Details:</div>
                <div style="color: #495057; line-height: 1.6; font-size: 12px; padding: 10px; background: #f8f9fa; border-radius: 4px;">
                    {details_html}
                </div>
            </div>
            <div style="margin-top: 12px; padding-top: 12px; border-top: 2px solid #28a745;">
                <div style="font-weight: 600; color: #28a745; margin-bottom: 8px; font-size: 13px;">Recommended Action:</div>
                <div style="color: #155724; line-height: 1.6; font-size: 12px; padding: 10px; background: #d4edda; border-radius: 4px; border-left: 3px solid #28a745;">
                    {formatted_action}
                </div>
            </div>
        """
    
    def _format_condensed_details(self, root_cause: str, action: str, execution_log: Optional[str] = None, category: Optional[str] = None) -> str:
        """
        Format condensed version of root cause and action (reduced content for popup).
        
        Args:
            root_cause: Root cause text
            action: Recommended action text
            execution_log: Optional execution log
            
        Returns:
            Condensed HTML string
        """
        # CRITICAL: Extract category-appropriate root cause from execution logs
        # This ensures root cause text matches the category (e.g., don't show "page not loading" for ASSERTION_FAILURE)
        if execution_log:
            # For TIMEOUT category: extract page load timeout message
            if category == 'TIMEOUT':
                # Extract page load timeout pattern: "'DashReviewPage' NOT loaded even after :- 40.071 seconds."
                # Try to find the full line containing the timeout message
                # IMPORTANT: Order matters - check patterns with duration FIRST, then fallback to without duration
                # Pattern examples:
                #   "'DashReviewPage' NOT loaded even after :- 40.071 seconds."
                #   '"DashReviewPage" NOT loaded even after :- 40.071 seconds.'
                timeout_patterns = [
                # Pattern 1: With quotes and duration - "'DashReviewPage' NOT loaded even after :- 40.071 seconds"
                # Match: ' or " followed by PageName followed by ' or ", then NOT loaded even after, then :- or :, then duration
                r"['\"]([^'\"]+Page[^'\"]*)['\"]\s+(?:NOT|not)\s+loaded\s+even\s+after\s*:?\s*-?\s*(\d+\.?\d*)\s*seconds?",
                # Pattern 2: Without quotes but with duration - "DashReviewPage NOT loaded even after :- 40.071 seconds"
                r"(\w+Page\w*)\s+(?:NOT|not)\s+loaded\s+even\s+after\s*:?\s*-?\s*(\d+\.?\d*)\s*seconds?",
                # Pattern 3: With quotes but no duration (fallback)
                r"['\"]([^'\"]+Page[^'\"]*)['\"]\s+(?:NOT|not)\s+loaded\s+even\s+after",
            ]
            
                extracted_timeout_message = None
                for pattern in timeout_patterns:
                    match = re.search(pattern, execution_log, re.IGNORECASE)
                    if match:
                        page_name = match.group(1)
                        # Check if we captured duration (group 2 exists and is not empty)
                        if len(match.groups()) >= 2 and match.group(2):
                            duration = match.group(2).strip()
                            # Remove any trailing dots or extra characters, keep only digits and decimal point
                            duration = re.sub(r'[^\d.]', '', duration)
                            if duration:
                                extracted_timeout_message = f"'{page_name}' NOT loaded even after :- {duration} seconds"
                            else:
                                extracted_timeout_message = f"'{page_name}' NOT loaded even after waiting"
                        else:
                            extracted_timeout_message = f"'{page_name}' NOT loaded even after waiting"
                        break
                
                # If we found the timeout message, use it instead of AI-generated root_cause
                if extracted_timeout_message:
                    root_cause = extracted_timeout_message
            
            # For ELEMENT_NOT_FOUND category: extract element-related exception messages
            elif category == 'ELEMENT_NOT_FOUND':
                # Extract element-related exceptions from logs
                element_exception_patterns = [
                    r"(NoSuchElementException[^\n]*)",
                    r"(StaleElementReferenceException[^\n]*)",
                    r"(ElementClickInterceptedException[^\n]*)",
                    r"(NullPointerException[^\n]*WebElement[^\n]*)",
                    r"(IndexOutOfBoundsException[^\n]*length\s+0[^\n]*)",
                    r"(IllegalArgumentException[^\n]*)",
                ]
                
                extracted_element_message = None
                for pattern in element_exception_patterns:
                    match = re.search(pattern, execution_log, re.IGNORECASE)
                    if match:
                        extracted_element_message = match.group(1).strip()
                        # Truncate if too long
                        if len(extracted_element_message) > 200:
                            extracted_element_message = extracted_element_message[:200] + "..."
                        break
                
                # If we found element exception, use it; otherwise keep AI-generated root_cause
                if extracted_element_message:
                    root_cause = extracted_element_message
            
            # For ASSERTION_FAILURE category: remove page load timeout messages, keep only assertion-related text
            elif category == 'ASSERTION_FAILURE':
                # Remove page load timeout patterns from root_cause
                root_cause = re.sub(
                    r"['\"]([^'\"]+Page[^'\"]*)['\"]\s+(?:NOT|not)\s+loaded\s+even\s+after[^\n]*",
                    '',
                    root_cause,
                    flags=re.IGNORECASE
                )
                # Also check execution_log and remove timeout messages
                execution_log_cleaned = re.sub(
                    r"['\"]([^'\"]+Page[^'\"]*)['\"]\s+(?:NOT|not)\s+loaded\s+even\s+after[^\n]*",
                    '',
                    execution_log,
                    flags=re.IGNORECASE
                )
                # Extract assertion failure patterns
                # Try to get the full assertion message, including the "Actual JSON doesn't contain all expected keys" part
                assertion_patterns = [
                    r"(Actual JSON doesn't contain all expected keys[^\n]+Expected has:[^\n]+but Actual has:[^\n]*)",  # Full missing keys pattern
                    r"(Actual JSON doesn't contain all expected keys[^\n]+Expected has:[^\n]*)",  # Partial missing keys pattern
                    r"(Expected\s+[^\n]+But\s+actual[^\n]*)",  # Expected vs Actual pattern
                    r"(Missing Key[^\n]+)",  # Missing Key pattern
                    r"(Classes of actual and expected[^\n]+Expected is:[^\n]+but Actual is:[^\n]*)",  # Class mismatch pattern
                    r"(The following asserts failed[^\n]+)",  # Multiple asserts failed
                ]
                
                extracted_assertion_message = None
                for pattern in assertion_patterns:
                    match = re.search(pattern, execution_log_cleaned, re.IGNORECASE | re.DOTALL)
                    if match:
                        extracted_assertion_message = match.group(1).strip()
                        # Clean up extra whitespace
                        extracted_assertion_message = re.sub(r'\s+', ' ', extracted_assertion_message)
                        # Truncate if too long (but keep important parts)
                        if len(extracted_assertion_message) > 250:
                            # Try to keep the key part if it's a missing keys message
                            if "Expected has:" in extracted_assertion_message:
                                parts = extracted_assertion_message.split("Expected has:")
                                if len(parts) > 1:
                                    extracted_assertion_message = "Actual JSON doesn't contain all expected keys. Expected has:" + parts[1][:200] + "..."
                            else:
                                extracted_assertion_message = extracted_assertion_message[:250] + "..."
                        break
                
                # If we found assertion message, use it; otherwise use cleaned root_cause
                if extracted_assertion_message:
                    root_cause = extracted_assertion_message
                else:
                    # Clean up root_cause - remove any remaining timeout references
                    root_cause = re.sub(r'\s+', ' ', root_cause).strip()
            
            # For ENVIRONMENT_ISSUE category: extract environment-related messages
            elif category == 'ENVIRONMENT_ISSUE':
                # Extract environment-related exceptions
                env_exception_patterns = [
                    r"(Connection refused[^\n]*)",
                    r"(Service unavailable[^\n]*)",
                    r"(503[^\n]*)",
                    r"(502 Bad Gateway[^\n]*)",
                    r"(Network timeout[^\n]*)",
                    r"(DNS error[^\n]*)",
                ]
                
                extracted_env_message = None
                for pattern in env_exception_patterns:
                    match = re.search(pattern, execution_log, re.IGNORECASE)
                    if match:
                        extracted_env_message = match.group(1).strip()
                        # Truncate if too long
                        if len(extracted_env_message) > 200:
                            extracted_env_message = extracted_env_message[:200] + "..."
                        break
                
                # If we found environment message, use it; otherwise keep AI-generated root_cause
                if extracted_env_message:
                    root_cause = extracted_env_message
        
        # Remove "API Name: ..." from root_cause text since API is already shown separately and may be incorrect
        cleaned_root_cause = root_cause
        # Pattern: "API Name: /dashboard/..." or "API Name: GetAmlSearchSuccessfulResponse"
        api_name_pattern = r'(API Name|Endpoint|api name|api url|url)[:\s]+([^\s,<>\n]+)'
        cleaned_root_cause = re.sub(api_name_pattern, '', cleaned_root_cause, flags=re.IGNORECASE)
        # Clean up any double commas or spaces left after removal
        cleaned_root_cause = re.sub(r',\s*,', ',', cleaned_root_cause)  # Remove double commas
        cleaned_root_cause = re.sub(r'\s+', ' ', cleaned_root_cause)  # Normalize whitespace
        cleaned_root_cause = cleaned_root_cause.strip()
        # Remove leading comma or space if present
        cleaned_root_cause = re.sub(r'^[,\s]+', '', cleaned_root_cause)
        
        # Extract key information only
        root_cause_escaped = html_escape.escape(cleaned_root_cause[:300] + ("..." if len(cleaned_root_cause) > 300 else ""))
        action_escaped = html_escape.escape(action[:200] + ("..." if len(action) > 200 else ""))
        
        # CRITICAL: For ELEMENT_NOT_FOUND and TIMEOUT categories, NEVER show API, only Page URL
        # For other categories, show API if available, otherwise Page URL
        page_or_api_info = ""
        if execution_log:
            # Use _extract_detailed_info to get the correct API/Page URL from execution_log
            details_info = self._extract_detailed_info(root_cause, execution_log=execution_log)
            
            # For ELEMENT_NOT_FOUND and TIMEOUT, only show Page URL, never API
            if category in ['ELEMENT_NOT_FOUND', 'TIMEOUT']:
                if details_info.get('page_url'):
                    # UI test - show Page URL
                    page_url = details_info['page_url']
                    page_or_api_info = f'<div style="margin-bottom: 8px;"><b>Page:</b> <code style="background: #e3f2fd; padding: 2px 6px; border-radius: 3px;">{html_escape.escape(page_url)}</code></div>'
                # If no page_url found, try extracting from logs directly
                elif execution_log:
                    page_url_pattern = r'Page URL[:\s-]+([^\s\n]+)'
                    page_url_match = re.search(page_url_pattern, execution_log, re.IGNORECASE)
                    if page_url_match:
                        page_url = page_url_match.group(1).strip()
                        page_or_api_info = f'<div style="margin-bottom: 8px;"><b>Page:</b> <code style="background: #e3f2fd; padding: 2px 6px; border-radius: 3px;">{html_escape.escape(page_url)}</code></div>'
            else:
                # For other categories, show API if available, otherwise Page URL
                if details_info['api_info']:
                    # Use the first API endpoint found from execution_log (most accurate)
                    api = details_info['api_info'][0]
                    page_or_api_info = f'<div style="margin-bottom: 8px;"><b>API:</b> <code style="background: #e3f2fd; padding: 2px 6px; border-radius: 3px;">{html_escape.escape(api)}</code></div>'
                elif details_info.get('page_url'):
                    # UI test - show Page URL
                    page_url = details_info['page_url']
                    page_or_api_info = f'<div style="margin-bottom: 8px;"><b>Page:</b> <code style="background: #e3f2fd; padding: 2px 6px; border-radius: 3px;">{html_escape.escape(page_url)}</code></div>'
        
        # Fallback: If no API/Page URL found from execution_log, try extracting from root_cause (only for non-ELEMENT_NOT_FOUND/TIMEOUT)
        if not page_or_api_info and category not in ['ELEMENT_NOT_FOUND', 'TIMEOUT']:
            api_patterns = [
                r'(API Name|Endpoint|api name|api url|url)[:\s]+([^\s,<>\n]+)',  # "API Name: /dashboard/..." or "API Name: GetAmlSearchSuccessfulResponse"
                r'\b(POST|GET|PUT|DELETE|PATCH)\s+([^\s,<>\n]+)',  # "GET /dashboard/..."
                r'(https?://[^\s]+|/api/[^\s]+|/dashboard/[^\s]+)',  # Direct URL/path
            ]
            
            api_found = None
            for pattern in api_patterns:
                match = re.search(pattern, root_cause, re.IGNORECASE)
                if match:
                    if len(match.groups()) > 1:
                        api_found = match.group(2).strip()
                    else:
                        api_found = match.group(1).strip()
                    # Only use if it looks like a valid API endpoint (contains / or is a response name)
                    if api_found and ('/' in api_found or 'Response' in api_found or api_found.startswith('Get') or api_found.startswith('Post')):
                        # Normalize API
                        api_found = re.sub(r'/[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}(?=/|$)', '/{$uuid}', api_found, flags=re.IGNORECASE)
                        api_found = re.sub(r'/\d+(?=/|$)', '/{$id}', api_found)
                        break
            
            if api_found:
                page_or_api_info = f'<div style="margin-bottom: 8px;"><b>API:</b> <code style="background: #e3f2fd; padding: 2px 6px; border-radius: 3px;">{html_escape.escape(api_found)}</code></div>'
        
        # Extract exception type if present
        exception_info = ""
        exception_match = re.search(r'(\w+Exception)(?::|$|\s)', root_cause, re.IGNORECASE)
        if exception_match:
            exception_type = exception_match.group(1)
            exception_info = f'<div style="margin-bottom: 8px;"><b>Exception:</b> <span style="color: #dc3545;">{html_escape.escape(exception_type)}</span></div>'
        
        html_output = f"""
            <div style="font-size: 12px; line-height: 1.6;">
                {page_or_api_info}
                {exception_info}
                <div style="margin-bottom: 8px;"><b>Root Cause:</b><br/>{root_cause_escaped}</div>
                {f'<div style="margin-bottom: 8px;"><b>Recommended Action:</b><br/><span style="color: #28a745;">{action_escaped}</span></div>' if action else ''}
            </div>
        """
        return html_output
    
    def _generate_html(
        self,
        summary: TestSummary,
        classifications: List[FailureClassification],
        report_name: str,
        ai_summary: str,
        recurring_failures: Optional[List[Dict]],
        trend: Optional[str],
        report_dir: Optional[str] = None,
        test_results: Optional[List[TestResult]] = None,
        test_html_links: Optional[Dict[str, str]] = None
    ) -> str:
        """Generate modern HTML report content"""
        
        # Initialize TestDataCache for efficient data access
        # This eliminates redundant execution log fetching
        test_data_cache = TestDataCache(test_results, test_html_links)
        
        # Initialize CategoryRuleEngine for clean category classification
        rule_engine = CategoryRuleEngine()
        
        # Parse automation group and branch from HTML report
        automation_group, automation_branch = self._parse_automation_group_and_branch(report_dir)
        
        # Data Preparation - Deduplicate classifications by test_name
        # A test might appear multiple times if it's in multiple test suites
        # Use a dictionary to track by normalized test name
        seen_tests = {}
        deduplicated_classifications = []
        duplicate_count = 0
        
        # First, count occurrences of each test
        test_counts = {}
        for classification in classifications:
            test_name_normalized = classification.test_name.strip()
            test_counts[test_name_normalized] = test_counts.get(test_name_normalized, 0) + 1
        
        # Log tests that appear multiple times
        for test_name, count in test_counts.items():
            if count > 1:
                logger.warning(f"⚠️ Test '{test_name}' appears {count} times in classifications!")
        
        # Now deduplicate
        for classification in classifications:
            test_name = classification.test_name
            # Normalize test name (remove any whitespace differences, case-insensitive comparison)
            test_name_normalized = test_name.strip()
            
            # Keep the first occurrence, or replace if we find a better one (higher confidence)
            if test_name_normalized not in seen_tests:
                seen_tests[test_name_normalized] = classification
                deduplicated_classifications.append(classification)
            else:
                # Duplicate found
                duplicate_count += 1
                existing = seen_tests[test_name_normalized]
                confidence_order = {'HIGH': 3, 'MEDIUM': 2, 'LOW': 1}
                existing_conf = confidence_order.get(existing.confidence, 0)
                new_conf = confidence_order.get(classification.confidence, 0)
                
                if new_conf > existing_conf:
                    # Replace with higher confidence one
                    index = deduplicated_classifications.index(existing)
                    deduplicated_classifications[index] = classification
                    seen_tests[test_name_normalized] = classification
                    logger.warning(f"⚠️ Duplicate '{test_name_normalized}' - Replaced with higher confidence ({classification.confidence} > {existing.confidence})")
                else:
                    logger.warning(f"⚠️ Duplicate '{test_name_normalized}' - Skipping (keeping existing with {existing.confidence} confidence)")
        
        if duplicate_count > 0:
            logger.warning(f"⚠️ Found {duplicate_count} duplicate classifications. Deduplicated: {len(classifications)} -> {len(deduplicated_classifications)}")
        
        # Validate data consistency after deduplication
        validation_stats = validate_report_data(
            test_results or [],
            deduplicated_classifications,
            test_data_cache,
            test_html_links
        )
        
        # Use deduplicated classifications
        product_bugs = [c for c in deduplicated_classifications if c.is_product_bug()]
        automation_issues = [c for c in deduplicated_classifications if c.is_automation_issue()]
        
        # Build test_api_map: Extract API endpoints for all classifications using the same method as tables
        # This map will be used in the summary generator to show accurate API endpoint counts
        test_api_map = self.extract_test_api_map(deduplicated_classifications, test_data_cache)
        
        # Colors
        c_success = "#28a745"
        c_warning = "#ffc107"
        c_danger = "#dc3545"
        c_info = "#17a2b8"
        c_text = "#333333"
        c_light = "#f8f9fa"
        
        # Status & Trend
        pass_rate = summary.pass_rate
        if pass_rate >= 90:
            status_color = c_success
            status_text = "EXCELLENT"
        elif pass_rate >= 75:
            status_color = c_warning
            status_text = "GOOD"
        else:
            status_color = c_danger
            status_text = "NEEDS ATTENTION"
            
        # Trend indicator - only show if there's a meaningful trend
        trend_html = ""
        if trend == "IMPROVING":
            trend_html = '<div style="font-size: 11px; color: #666; margin-top: 2px;">↗️ Improving</div>'
        elif trend == "DECLINING":
            trend_html = '<div style="font-size: 11px; color: #666; margin-top: 2px;">↘️ Declining</div>'
        elif trend == "STABLE":
            trend_html = '<div style="font-size: 11px; color: #666; margin-top: 2px;">➡️ Stable</div>'
        # For NO_DATA or INSUFFICIENT_DATA, don't show trend

        # Get CSS styles and JavaScript from separate modules
        css_styles = get_html_styles(c_success, c_warning, c_danger, c_info, c_text, c_light)
        
        # Extract project and job name for correct links
        project_name_from_path, job_name_from_path = ReportUrlBuilder.extract_project_job_from_path(report_dir)
        
        # Resolve project/job for URLs and JS (job must come from path/input, no config fallback)
        project_name_for_js = project_name_from_path if project_name_from_path else ReportUrlBuilder.extract_project_name(report_name)
        job_name_for_url = job_name_from_path  # None if not derivable
        js_scripts = get_html_scripts(Config.DASHBOARD_BASE_URL, project_name_for_js, job_name_for_url)
        
        # Build HTML - use f-string for most content, but concatenate JavaScript separately
        html = f"""<!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
            <style>
{css_styles}
            </style>
        </head>
        <body>
            <div class="container">
                <!-- Header -->
                <div class="header">
                    <img src="https://raw.githubusercontent.com/msr5464/Basic-Automation-Framework/refs/heads/master/ThanosLogo.png" alt="Thanos Logo" class="header-logo">
                    <h1 class="report-title">AI-Generated Automation Report</h1>
                    <div class="report-meta" style="display: flex; align-items: center; justify-content: center; gap: 8px;">
                        <strong>{report_name}</strong>
                        {'<a href="' + ReportUrlBuilder.build_dashboard_url(Config.DASHBOARD_BASE_URL, report_name, "html/index.html", project_name_from_path, job_name_for_url) + '" target="_blank" style="color: #ffffff; opacity: 0.9; text-decoration: none; display: inline-flex; align-items: center; line-height: 1;"><svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1-2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg></a>' if report_name else ''}
                    </div>
                    {'<div class="report-meta" style="margin-top: 4px; font-size: 12px;">Group: ' + str(automation_group) + ' • Branch: ' + str(automation_branch) + '</div>' if automation_group and automation_branch else ''}
                </div>
                
                <!-- Key Metrics -->
                <div class="dashboard">
                    <div class="card success">
                        <div class="metric-label">Pass Rate</div>
                        <div class="metric-value" style="color: {status_color}">{pass_rate:.1f}%</div>
                        <div class="metric-detail" style="font-weight: 600;">{status_text}</div>
                        {trend_html}
                    </div>
                    <div class="card danger">
                        <div class="metric-label">Failures</div>
                        <div class="metric-value">{summary.failed}</div>
                        <div class="metric-detail">{len(product_bugs)} Potential Bugs, {len(automation_issues)} Automation Issues</div>
                    </div>
                    <div class="card">
                        <div class="metric-label">Total Tests</div>
                        <div class="metric-value">{summary.total}</div>
                        <div class="metric-detail">{summary.passed} Passed</div>
                    </div>
                </div>
                
                <!-- Executive Summary -->
        """
        
        # Root Cause Category Summary
        # Group failures by category
        category_counts = {}
        category_failures = {}
        
        for failure in deduplicated_classifications:
            # Use rule engine to classify failure into category
            category = rule_engine.classify(failure, test_data_cache)
            
            if category not in category_counts:
                category_counts[category] = 0
                category_failures[category] = []
            category_counts[category] += 1
            category_failures[category].append(failure)
        
        # Add Executive Summary section if available
        if ai_summary:
            # ai_summary is already HTML-formatted, so don't escape it
            html += f"""
                <div class="section">
                    <h2 class="section-title" style="border-color: #3498db">📊 Executive Summary</h2>
                    <p class="root-cause-subtitle">High-level overview of test execution results, failure patterns, and actionable insights derived from AI analysis of the test failures.</p>
                    <div class="exec-summary">
                        {ai_summary}
                    </div>
                </div>
            """
        
        html += """
                <!-- Root Cause Categories -->
        """
            
        # Only show if we have categories
        total_failures = 0
        if category_counts:
            # Helpers and styling metadata for the grid
            def truncate_text(text: str, limit: int = 180) -> str:
                if not text:
                    return ""
                text = text.strip()
                return text if len(text) <= limit else text[:limit - 1] + "…"
            
            categories_order = ['ELEMENT_NOT_FOUND', 'TIMEOUT', 'ASSERTION_FAILURE', 'ENVIRONMENT_ISSUE', 'OTHER']
            sorted_categories = sorted(
                category_counts.keys(),
                key=lambda x: (-category_counts[x], categories_order.index(x) if x in categories_order else 99)
            )
            total_failures = max(1, sum(category_counts.values()))
            
            category_styles = {
                'ELEMENT_NOT_FOUND': {
                    'color': '#f97316',
                    'icon': '🔍',
                    'label': 'Element Locator Issues',
                    'gradient': 'linear-gradient(135deg, #fff7ed, #ffe7d0)',
                    'hint': 'Likely locator drift or DOM change',
                    'tag': 'UI Locator',
                    'pill_bg': 'rgba(249, 115, 22, 0.15)',
                    'pill_color': '#c2410c'
                },
                'TIMEOUT': {
                    'color': '#facc15',
                    'icon': '⏱️',
                    'label': 'Page Load Issues',
                    'gradient': 'linear-gradient(135deg, #fffbea, #fef3c7)',
                    'hint': 'Review waits & backend latency',
                    'tag': 'Stability',
                    'pill_bg': 'rgba(250, 204, 21, 0.18)',
                    'pill_color': '#a16207'
                },
                'ASSERTION_FAILURE': {
                    'color': '#dc2626',
                    'icon': '❌',
                    'label': 'Assertion Failures',
                    'gradient': 'linear-gradient(135deg, #fee2e2, #fecaca)',
                    'hint': 'Product regression suspected',
                    'tag': 'Potential Bug',
                    'pill_bg': 'rgba(220, 38, 38, 0.15)',
                    'pill_color': '#991b1b'
                },
                'ENVIRONMENT_ISSUE': {
                    'color': '#8b5cf6',
                    'icon': '🏗️',
                    'label': 'Environment Issues',
                    'gradient': 'linear-gradient(135deg, #ede9fe, #ddd6fe)',
                    'hint': 'Infrastructure, network, or data setup issues',
                    'tag': 'Environment',
                    'pill_bg': 'rgba(139, 92, 246, 0.18)',
                    'pill_color': '#5b21b6'
                },
                'OTHER': {
                    'color': '#475569',
                    'icon': '❓',
                    'label': 'Miscellaneous Issues',
                    'gradient': 'linear-gradient(135deg, #f1f5f9, #e2e8f0)',
                    'hint': 'Needs manual triage',
                    'tag': 'Review',
                    'pill_bg': 'rgba(71, 85, 105, 0.18)',
                    'pill_color': '#1e293b'
                }
            }
            
            # Add anchor for navigation
            html += f"""
                <div class="section" id="root-cause-categories">
                    <h2 class="section-title" style="border-color: #6610f2">🧩 Failures by Root Cause Category</h2>
                    <p class="root-cause-subtitle">Breakdown of {sum(category_counts.values())} analyzed failures grouped by the AI-assigned root cause type. Click on any test to view details or expand "View details" for root cause and recommended actions.</p>
                    <div class="section-content root-cause-categories-container">
            """
            
            # Determine layout based on number of categories
            num_categories = len(sorted_categories)
            use_two_row_layout = num_categories > 4
            
            if use_two_row_layout:
                # First row with 2 columns
                html += '<div class="root-cause-grid-first-row">'
            else:
                # Use original grid layout for 4 or fewer categories
                html += '<div class="root-cause-grid">'
            
            for idx, category in enumerate(sorted_categories):
                # Check if we need to switch to second row (after first 2 items)
                if use_two_row_layout and idx == 2:
                    html += '</div>'  # Close first row
                    html += '<div class="root-cause-grid-second-row">'  # Open second row
                failures = category_failures.get(category, [])
                # CRITICAL: Use actual count from failures list, not category_counts
                # category_counts may be incorrect due to deduplication or other issues
                count = len(failures)
                percentage = (count / total_failures) * 100 if total_failures > 0 else 0
                
                # Debug logging to verify counts
                if category in ['ELEMENT_NOT_FOUND', 'TIMEOUT']:
                    logger.debug(f"Category {category}: count={count}, len(failures)={len(failures)}, category_counts={category_counts.get(category, 0)}")
                style = category_styles.get(
                    category,
                    {
                        'color': '#6c757d',
                        'icon': '❓',
                        'label': category.replace('_', ' ').title(),
                        'gradient': 'linear-gradient(135deg, #f1f5f9, #e2e8f0)',
                        'hint': 'Mixed signals – review details',
                        'tag': 'Review',
                        'pill_bg': 'rgba(108, 117, 125, 0.18)',
                        'pill_color': '#343a40'
                    }
                )
                
                # failures is already set above
                
                def build_display_context(failure_entry: FailureClassification):
                    """Build display context using cached test data for accurate link matching."""
                    # Get data from cache (always available since cache is built from test_results)
                    cached_data = test_data_cache.get_all_data(failure_entry.test_name)
                    
                    # Use actual method_name and class_name from cached test result
                    class_name = remove_duplicate_class_name(cached_data.get('class_name', '')) if cached_data else ''
                    method_name = cached_data.get('method_name', '') if cached_data else 'unknown'
                    html_link = cached_data.get('html_link') if cached_data else None
                    
                    # If no HTML link from cache, try to find it
                    if not html_link:
                        html_link = self._find_test_html_link(class_name, method_name, report_dir, report_name, test_html_links)
                    
                    class_segment = class_name.split('.')[-1] if class_name else 'Test'
                    method_segment = method_name or 'unknown'
                    display_name = f"{class_segment}.{method_segment}"
                    
                    return display_name, html_link
                
                # Build chips pointing to the underlying tests (show first 5, expandable for more)
                test_chip_elements = []
                all_display_entries = [(build_display_context(f_entry), f_entry) for f_entry in failures]
                
                # Generate chip HTML with expandable details for a single test entry
                def generate_chip_html(display_name, html_link, failure_entry):
                    display_name_escaped = html_escape.escape(display_name)
                    title_attr = html_escape.escape(display_name)
                    # Extract just the testcase name (method name) - everything after the last dot
                    testcase_name = display_name.split('.')[-1] if '.' in display_name else display_name
                    # Escape for JavaScript string
                    testcase_name_js = testcase_name.replace("'", "\\'").replace('"', '\\"')
                    
                    # Get root cause and action for expandable details
                    root_cause = (failure_entry.root_cause or "").strip()
                    recommended_action = (failure_entry.recommended_action or "").strip()
                    
                    # Create condensed version of root cause and action (reduced content)
                    execution_log = test_data_cache.get_combined_log(failure_entry.test_name) or ""
                    condensed_content = self._format_condensed_details(
                        root_cause, recommended_action, execution_log, category=category
                    )
                    
                    # Create unique ID for this test's details
                    test_id = f"test-{category}-{hash(failure_entry.test_name) % 100000}"
                    
                    # Create unique ID for this test's details (before building details_html)
                    details_id = f"details-{category}-{hash(failure_entry.test_name) % 100000}"
                    
                    # Build expandable details section
                    details_html = ""
                    expand_icon_html = ""
                    if root_cause or recommended_action:
                        expand_icon_html = '<span class="test-expand-icon">▶</span>'
                        details_html = f"""
                            <details class="test-details-expandable" id="{details_id}">
                                <summary class="test-details-summary"></summary>
                                <div class="test-details-content">
                                    <button class="test-details-close" onclick="closeTestDetailsExpandable('{details_id}')" title="Close">
                                        <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
                                            <line x1="18" y1="6" x2="6" y2="18"></line>
                                            <line x1="6" y1="6" x2="18" y2="18"></line>
                                        </svg>
                                    </button>
                                    {condensed_content}
                                </div>
                            </details>
                        """
                    
                    if html_link:
                        html_link_escaped = html_escape.escape(html_link)
                        chip_html = (
                            f'<div class="test-chip-with-details">'
                            f'<span class="root-cause-chip-container" title="{title_attr}" onclick="toggleTestDetails(\'{details_id}\')" style="cursor: pointer;">'
                            f'{expand_icon_html}'
                            f'<span class="root-cause-chip">{display_name_escaped}</span>'
                            f'<a href="{html_link_escaped}" class="root-cause-link-btn" target="_blank" title="Open full logs for this class" onclick="event.stopPropagation()"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg></a>'
                            f'<button class="root-cause-copy-btn" onclick="copyTestName(\'{testcase_name_js}\', this, event)" title="Copy testcase name"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></button>'
                            f'</span>'
                            f'{details_html}'
                            f'</div>'
                        )
                    else:
                        chip_html = (
                            f'<div class="test-chip-with-details">'
                            f'<span class="root-cause-chip-container muted" title="{title_attr}" onclick="toggleTestDetails(\'{details_id}\')" style="cursor: pointer;">'
                            f'{expand_icon_html}'
                            f'<span class="root-cause-chip muted">{display_name_escaped}</span>'
                            f'<button class="root-cause-copy-btn" onclick="copyTestName(\'{testcase_name_js}\', this, event)" title="Copy testcase name"><svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"></rect><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path></svg></button>'
                            f'</span>'
                            f'{details_html}'
                            f'</div>'
                        )
                    
                    return chip_html
                
                # Show first 5 tests, rest in expandable section
                max_visible = 5
                visible_tests = all_display_entries[:max_visible]
                hidden_tests = all_display_entries[max_visible:]
                
                # Generate HTML for visible tests (with expandable details)
                visible_chips = ''.join(
                    generate_chip_html(display_name, html_link, failure_entry) 
                    for (display_name, html_link), failure_entry in visible_tests
                )
                
                # Generate HTML for hidden tests (if any)
                hidden_chips_html = ""
                if hidden_tests:
                    hidden_chips = ''.join(
                        generate_chip_html(display_name, html_link, failure_entry) 
                        for (display_name, html_link), failure_entry in hidden_tests
                    )
                    hidden_chips_html = f"""
                        <details class="root-cause-expand-more">
                            <summary class="root-cause-expand-summary">+{len(hidden_tests)} more test{'s' if len(hidden_tests) > 1 else ''}</summary>
                            <div class="root-cause-expanded-tests">
                                {hidden_chips}
                            </div>
                        </details>
                    """
                
                tests_html = (visible_chips + hidden_chips_html) if visible_chips else '<span class="root-cause-chip muted">No linked tests</span>'
                
                # Highlight representative root cause signals instead of a single line
                root_cause_note_html = "No detailed root causes captured for this category."
                if failures:
                    # Special handling for TIMEOUT category: extract element patterns and page names with counts
                    if category == 'TIMEOUT':
                        element_patterns = {}  # Store element patterns like "CardCreationPage:search card holder name text box"
                        page_counts = {}  # Store page load patterns like "DashReviewPage"
                        css_selector_patterns = {}  # Store CSS selector patterns separately
                        unmatched_count = 0
                        
                        for failure_entry in failures:
                            rc_text = (failure_entry.root_cause or "").strip()
                            matched = False
                            
                            # Get execution log from cache
                            exec_log = test_data_cache.get_combined_log(failure_entry.test_name)
                            
                            # Combine root_cause and execution_log for searching
                            search_text = f"{rc_text} {exec_log}"
                            
                            if search_text.strip():
                                # Priority 1: Extract element visibility timeout patterns
                                # Pattern: "Element 'CardCreationPage:search card holder name text box' is NOT visible even after waiting for 40 seconds"
                                element_match = re.search(
                                    r"Element\s+['\"]([^'\"]+)['\"]\s+is\s+(?:NOT|not)\s+visible(?:\s+and\s+clickable)?\s+even\s+after\s+waiting\s+for\s+\d+\s+seconds",
                                    search_text,
                                    re.IGNORECASE
                                )
                                if element_match:
                                    element_pattern = element_match.group(1).strip()
                                    element_patterns[element_pattern] = element_patterns.get(element_pattern, 0) + 1
                                    matched = True
                                else:
                                    # Priority 2: Extract page load timeout patterns
                                    # Pattern: "'DashReviewPage' NOT loaded even after :- 40.071 seconds."
                                    page_match = re.search(r"['\"]([^'\"]+Page[^'\"]*)['\"]\s+(?:NOT|not)\s+loaded\s+even\s+after", search_text, re.IGNORECASE)
                                    if page_match:
                                        page_name = page_match.group(1)
                                        page_counts[page_name] = page_counts.get(page_name, 0) + 1
                                        matched = True
                                    else:
                                        # Priority 3: Try alternative pattern: PageName NOT loaded even after (without quotes)
                                        alt_match = re.search(r"(\w+Page\w*)\s+(?:NOT|not)\s+loaded\s+even\s+after", search_text, re.IGNORECASE)
                                        if alt_match:
                                            page_name = alt_match.group(1)
                                            page_counts[page_name] = page_counts.get(page_name, 0) + 1
                                            matched = True
                                        else:
                                            # Priority 4: Try TimeoutException patterns for element clickable
                                            timeout_exception_match = re.search(
                                                r"TimeoutException.*waiting\s+for\s+element\s+to\s+be\s+(?:clickable|visible).*?['\"]([^'\"]+)['\"]",
                                                search_text,
                                                re.IGNORECASE | re.DOTALL
                                            )
                                            if timeout_exception_match:
                                                # Extract element selector or description if available
                                                element_desc = timeout_exception_match.group(1).strip()
                                                if element_desc:
                                                    # Check if it's a CSS selector pattern
                                                    if re.match(r'^By\.(cssSelector|xpath|id|name|className|tagName|linkText|partialLinkText)', element_desc, re.IGNORECASE):
                                                        # Store CSS selector patterns separately
                                                        css_selector_patterns[element_desc] = css_selector_patterns.get(element_desc, 0) + 1
                                                    else:
                                                        # Meaningful element pattern
                                                        element_patterns[element_desc] = element_patterns.get(element_desc, 0) + 1
                                                    matched = True
                            
                            if not matched:
                                unmatched_count += 1
                        
                        # Combine element patterns and page counts for display
                        meaningful_patterns = []
                        
                        # Add element patterns first (more specific)
                        if element_patterns:
                            sorted_elements = sorted(element_patterns.items(), key=lambda x: (-x[1], x[0]))
                            for element_pattern, pattern_count in sorted_elements:
                                meaningful_patterns.append(f"'{element_pattern}' ({pattern_count})")
                        
                        # Add page load patterns
                        if page_counts:
                            sorted_pages = sorted(page_counts.items(), key=lambda x: (-x[1], x[0]))
                            for page_name, page_count in sorted_pages:
                                meaningful_patterns.append(f"{page_name} ({page_count})")
                        
                        # Add CSS selector patterns as "other patterns" if any
                        if css_selector_patterns:
                            css_selector_total = sum(css_selector_patterns.values())
                            meaningful_patterns.append(f"other patterns ({css_selector_total})")
                        
                        # Add unmatched count if any (but only if we have no other patterns)
                        if unmatched_count > 0 and not meaningful_patterns:
                            meaningful_patterns.append(f"Unknown page ({unmatched_count})")
                        
                        if meaningful_patterns:
                            # Format the display text
                            if len(meaningful_patterns) <= 5:
                                patterns_text = ", ".join(meaningful_patterns)
                            else:
                                patterns_text = ", ".join(meaningful_patterns[:4]) + f", and {len(meaningful_patterns) - 4} other pattern(s)"
                            
                            root_cause_note_html = f"""
                                <div class="root-cause-note-title">Representative signals</div>
                                <div style="color: #1f2933; font-size: 12px; line-height: 1.5;">{html_escape.escape(patterns_text)}</div>
                            """
                        else:
                            root_cause_note_html = "No patterns extracted from timeout failures."
                    elif category == 'ELEMENT_NOT_FOUND':
                        # Special handling for ELEMENT_NOT_FOUND: extract exception types with counts
                        exception_counts = {}
                        unmatched_failures = []  # Store unmatched failures for pattern analysis
                        
                        for failure_entry in failures:
                            rc_text = (failure_entry.root_cause or "").strip()
                            matched = False
                            
                            # Get execution log from cache
                            exec_log = test_data_cache.get_combined_log(failure_entry.test_name)
                            
                            # Combine root_cause and execution_log for searching
                            search_text = f"{rc_text} {exec_log}"
                            
                            if search_text.strip():
                                # Extract exception type (with or without colon)
                                exception_match = re.search(r'(\w+Exception)(?::|$|\s)', search_text, re.IGNORECASE)
                                if not exception_match:
                                    # Try without Exception suffix (e.g., just "NullPointer")
                                    exception_match = re.search(r'(\w+Exception)', search_text, re.IGNORECASE)
                                
                                if exception_match:
                                    exception_type = exception_match.group(1)
                                    # Normalize: remove "in X" context to group similar exceptions together
                                    # Just use the base exception type
                                    key = exception_type
                                    
                                    exception_counts[key] = exception_counts.get(key, 0) + 1
                                    matched = True
                            
                            if not matched:
                                unmatched_failures.append({
                                    'root_cause': rc_text,
                                    'exec_log': exec_log,
                                    'search_text': search_text
                                })
                        
                        # Analyze unmatched failures to find common patterns
                        if unmatched_failures:
                            # Group unmatched failures by normalized root cause patterns
                            unmatched_patterns = {}
                            for failure in unmatched_failures:
                                normalized_rc = normalize_root_cause(failure['root_cause'])
                                
                                # Try to extract meaningful patterns from normalized root cause
                                if normalized_rc:
                                    # Look for common patterns
                                    pattern = None
                                    
                                    # Pattern 1: Element not visible/clickable (check first as it's more specific)
                                    if re.search(r'element.*not.*visible|element.*not.*clickable', normalized_rc, re.IGNORECASE):
                                        pattern = "Element not visible/clickable"
                                    # Pattern 2: Element not found
                                    elif re.search(r'element.*not.*found|locator.*not.*found', normalized_rc, re.IGNORECASE):
                                        pattern = "Element not found"
                                    # Pattern 3: Timeout patterns (including waiting)
                                    elif re.search(r'not.*loaded.*after|timeout|waiting.*for|even after waiting', normalized_rc, re.IGNORECASE):
                                        pattern = "Element timeout"
                                    # Pattern 4: Stale element
                                    elif re.search(r'stale|element.*reference', normalized_rc, re.IGNORECASE):
                                        pattern = "Stale element reference"
                                    # Pattern 5: Page load issues
                                    elif re.search(r'page.*not.*load|page.*load.*fail', normalized_rc, re.IGNORECASE):
                                        pattern = "Page load failure"
                                    # Pattern 6: Click intercepted
                                    elif re.search(r'click.*intercept|element.*intercept', normalized_rc, re.IGNORECASE):
                                        pattern = "Element click intercepted"
                                    # Pattern 7: Element is null
                                    elif re.search(r'element.*is.*null|element.*null', normalized_rc, re.IGNORECASE):
                                        pattern = "Element is null"
                                    # Pattern 8: Wait/Timeout related (catch-all for wait patterns)
                                    elif re.search(r'\bwait\b|can.*t.*wait|waiting', normalized_rc, re.IGNORECASE):
                                        pattern = "Element wait timeout"
                                    
                                    if pattern:
                                        unmatched_patterns[pattern] = unmatched_patterns.get(pattern, 0) + 1
                                    else:
                                        # Use first 60 chars of normalized root cause as pattern, but normalize further
                                        short_pattern = normalized_rc[:60].strip()
                                        # Remove common variable parts
                                        short_pattern = re.sub(r'\[PAGE_ELEMENT\]|\[DURATION\]|\[ID\]', '', short_pattern)
                                        short_pattern = ' '.join(short_pattern.split())  # Normalize whitespace
                                        if short_pattern and len(short_pattern) > 10:
                                            unmatched_patterns[short_pattern] = unmatched_patterns.get(short_pattern, 0) + 1
                                        else:
                                            unmatched_patterns["Other"] = unmatched_patterns.get("Other", 0) + 1
                                else:
                                    unmatched_patterns["Other"] = unmatched_patterns.get("Other", 0) + 1
                            
                            # Add grouped patterns to exception_counts
                            for pattern, pattern_count in unmatched_patterns.items():
                                if pattern == "Other" and pattern_count > 0:
                                    exception_counts["Others"] = exception_counts.get("Others", 0) + pattern_count
                                elif pattern_count > 0:
                                    exception_counts[pattern] = exception_counts.get(pattern, 0) + pattern_count
                        
                        if exception_counts:
                            # Sort by count (descending), then alphabetically
                            sorted_exceptions = sorted(exception_counts.items(), key=lambda x: (-x[1], x[0]))
                            # Format as "ExceptionType(count)"
                            exceptions_with_counts = [f"{exc_type}({exc_count})" for exc_type, exc_count in sorted_exceptions]
                            exceptions_text = ", ".join(exceptions_with_counts)
                            
                            root_cause_note_html = f"""
                                <div class="root-cause-note-title">Representative signals</div>
                                <div style="color: #1f2933; font-size: 12px; line-height: 1.5;">{html_escape.escape(exceptions_text)}</div>
                            """
                        else:
                            root_cause_note_html = "No exception types extracted from element locator failures."
                    elif category == 'ASSERTION_FAILURE':
                        # Special handling for ASSERTION_FAILURE: categorize assertion failures into specific types
                        assertion_categories = {}
                        for failure_entry in failures:
                            rc_text = (failure_entry.root_cause or "").strip()
                            
                            # Get execution log from cache
                            exec_log = test_data_cache.get_combined_log(failure_entry.test_name)
                            
                            # Combine root_cause and execution_log for searching
                            search_text = f"{rc_text} {exec_log}"
                            
                            # Categorize assertion failure type
                            category_type = None
                            
                            if search_text.strip():
                                # Category 1: API Keys mismatch - Missing keys or keys don't match between expected and actual
                                if (re.search(r"missing\s+key\s*:", search_text, re.IGNORECASE) or
                                    re.search(r"actual\s+json\s+doesn'?t\s+contain\s+all\s+expected\s+keys", search_text, re.IGNORECASE) or
                                    re.search(r"expected\s+(?:keys|has)\s*:.*but\s+actual\s+(?:keys|has)\s*:", search_text, re.IGNORECASE)):
                                    category_type = "API Keys mismatch"
                                
                                # Category 2: Keys formatting mismatch - Class type mismatches, null values, formatting issues
                                elif (re.search(r"classes\s+of\s+actual\s+and\s+expected\s+key", search_text, re.IGNORECASE) or
                                      re.search(r"key\s*/\s*value\s+is\s+null", search_text, re.IGNORECASE) or
                                      re.search(r"class\s+\w+\.\w+\$Null", search_text, re.IGNORECASE)):
                                    category_type = "Keys formatting mismatch"
                                
                                # Category 3: Single text not matching - Expected vs Actual value mismatches for single fields
                                elif re.search(r"expected\s+['\"]?[^'\"]+['\"]?\s+was\s*[:-]\s*['\"]?[^'\"]+['\"]?\s*\.?\s*but\s+actual\s+is", search_text, re.IGNORECASE):
                                    category_type = "Single text not matching"
                            
                            # Fallback: use generic category if no specific pattern matched
                            if not category_type:
                                category_type = "Assertion failure"
                            
                            assertion_categories[category_type] = assertion_categories.get(category_type, 0) + 1
                        
                        if assertion_categories:
                            # Sort by count (descending), then alphabetically
                            sorted_categories = sorted(assertion_categories.items(), key=lambda x: (-x[1], x[0]))
                            # Format as "Category(count)"
                            categories_with_counts = [f"{category}({cat_count})" for category, cat_count in sorted_categories]
                            categories_text = ", ".join(categories_with_counts)
                            
                            root_cause_note_html = f"""
                                <div class="root-cause-note-title">Representative signals</div>
                                <div style="color: #1f2933; font-size: 12px; line-height: 1.5;">{html_escape.escape(categories_text)}</div>
                            """
                        else:
                            root_cause_note_html = "No assertion categories extracted from failures."
                    else:
                        # Default behavior for OTHER and other categories: extract exception types or error patterns with counts
                        error_patterns = {}
                        for failure_entry in failures:
                            rc_text = (failure_entry.root_cause or "").strip()
                            
                            pattern_key = None
                            if rc_text:
                                # Extract exception type
                                exception_match = re.search(r'(\w+Exception)(?::|$|\s)', rc_text, re.IGNORECASE)
                                if exception_match:
                                    exception_type = exception_match.group(1)
                                    pattern_key = exception_type
                                else:
                                    # Extract error message pattern (first 40 chars)
                                    error_msg = rc_text[:40].strip()
                                    if error_msg:
                                        # Normalize similar errors
                                        normalized = normalize_root_cause(rc_text) or error_msg.lower()
                                        pattern_key = normalized
                            
                            # Fallback: use generic pattern if no pattern matched
                            if not pattern_key:
                                pattern_key = "Unknown error"
                            
                            error_patterns[pattern_key] = error_patterns.get(pattern_key, 0) + 1
                        
                        if error_patterns:
                            # Sort by count (descending), then alphabetically
                            sorted_patterns = sorted(error_patterns.items(), key=lambda x: (-x[1], x[0]))
                            # Format as "Pattern(count)"
                            patterns_with_counts = [f"{pattern}({pattern_count})" for pattern, pattern_count in sorted_patterns]
                            patterns_text = ", ".join(patterns_with_counts)
                            
                            root_cause_note_html = f"""
                                <div class="root-cause-note-title">Representative signals</div>
                                <div style="color: #1f2933; font-size: 12px; line-height: 1.5;">{html_escape.escape(patterns_text)}</div>
                            """
                        else:
                            root_cause_note_html = "No error patterns extracted from failures."
                root_cause_note_html = f'<div class="root-cause-note">{root_cause_note_html}</div>'
                
                pill_html = f'<span class="root-cause-pill" style="background: {style["pill_bg"]}; color: {style["pill_color"]};">{style["tag"]}</span>'
                
                html += f"""
                        <div class="root-cause-card" style="--rc-color: {style['color']}; --rc-gradient: {style['gradient']};">
                            <div class="root-cause-card-content">
                                <div class="root-cause-card-header">
                                    <div>
                                        <div class="root-cause-card-title">{style['icon']} {style['label']}</div>
                                        {pill_html}
                                </div>
                                    <div class="root-cause-card-count">
                                        <span class="count">{count} tests</span>
                                        <span class="percent">{percentage:.1f}% of all failures</span>
                                </div>
                            </div>
                                <div class="root-cause-meter">
                                    <div class="root-cause-meter-fill" style="width: {percentage}%; background: {style['color']};"></div>
                            </div>
                                <div class="root-cause-meta">
                                    <span>{style['hint']}</span>
                                    <span>{len(failures)} impacted test{'' if len(failures) == 1 else 's'}</span>
                                </div>
                                {root_cause_note_html}
                                <div class="root-cause-tests">
                                    {tests_html}
                                </div>
                            </div>
                        </div>
                """
            
            html += f"""
                        </div>
                        <div class="root-cause-footnote">Percentages are calculated out of {total_failures} total failures.</div>
                    </div>
                </div>
            """
        
        # Post-report validation: Validate data consistency after report generation
        post_validation_stats = validate_post_report(
            category_counts,
            category_failures,
            test_data_cache,
            total_failures
        )
        
        # Note: Detailed tables (Potential Bugs, Automation Issues, Product Changes) removed
        # All test details are now available in Root Cause Category cards with expandable details

        # Recurring Failures
        # Always show this section, even if empty
        flaky_count = len(recurring_failures) if recurring_failures else 0
        html += f"""
            <div class="section" id="flaky-tests">
            <h2 class="section-title" style="border-color: #6c757d">⚠️ All Flaky Tests ({flaky_count} tests)</h2>
            <p class="root-cause-subtitle">Tests that atleast failed {Config.FLAKY_TESTS_MIN_FAILURES} times in the last {Config.FLAKY_TESTS_LAST_RUNS} executions. Click on execution history dots to view detailed failure information for each run.</p>
        """
        if recurring_failures:
            # Sort filtered data:
            # a) First by max number of failures (descending)
            # b) Then by failure pattern severity
            def get_pattern_severity(pattern):
                """Return severity score for failure pattern (higher = more severe)
                
                Order:
                1. Continuously failing due to same reason (highest)
                2. Continuously failing but different reasons
                3. Intermittently failing due to same reason
                4. Intermittently failing but different reasons (lowest)
                """
                pattern_lower = pattern.lower()
                if 'continuously failing due to same reason' in pattern_lower:
                    return 4  # Highest priority
                elif 'continuously failing but different reasons' in pattern_lower:
                    return 3  # Second priority
                elif 'intermittently failing due to same reason' in pattern_lower:
                    return 2  # Third priority
                elif 'intermittently failing but different reasons' in pattern_lower:
                    return 1  # Fourth priority
                else:
                    return 0  # Lowest priority
            
            def sort_key(failure):
                occurrences = failure.get('occurrences', 0)
                pattern = failure.get('failure_pattern', '')
                pattern_severity = get_pattern_severity(pattern)
                # Sort by occurrences first (descending), then by pattern severity (descending)
                return (-occurrences, -pattern_severity)
            
            sorted_recurring_failures = sorted(recurring_failures, key=sort_key)
            
            html += f"""
                    <div class="section-content recurring-failures">
                    <table>
                        <thead>
                            <tr>
                                    <th>Testcase Name</th>
                                    <th>Last {Config.FLAKY_TESTS_LAST_RUNS} Executions</th>
                                    <th>Failure Pattern</th>
                            </tr>
                        </thead>
                        <tbody>
            """
            for failure in sorted_recurring_failures:
                full_name = failure['test_name']
                
                # CRITICAL: Clean full_name to remove duplicates before processing
                full_name = remove_duplicate_class_name(full_name)
                
                # Extract just class.method for display (e.g., "TestActivation.testSecondActivationMissionCards")
                class_name, method_name = extract_class_and_method(full_name)
                display_name = f"{class_name}.{method_name}"
                
                # Generate clickable dots with execution details
                history_html = ""
                history = failure.get('history', [])
                execution_details = failure.get('execution_details', [])
                test_name_escaped = html_escape.escape(full_name)
                
                # Debug: Log if history is empty
                if not history:
                    logger.warning(f"No history found for test: {failure.get('test_name', 'unknown')}")
                    # Try to create a default history based on occurrences (10 days)
                    occurrences = failure.get('occurrences', 0)
                    if occurrences >= 7:
                        history = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0]  # All failures
                    elif occurrences >= 5:
                        history = [0, 0, 0, 0, 0, 1, 0, 1, 0, 1]  # Mostly failures
                    elif occurrences >= 3:
                        history = [0, 0, 1, 0, 1, 0, 1, 0, 1, 0]  # Intermittent failures
                    else:
                        history = [1, 0, 1, 0, 1, 0, 1, 0, 1, 0]  # Mostly passes
                
                # Generate clickable dots with data attributes
                for idx, status in enumerate(history):
                    color = "#28a745" if status == 1 else "#dc3545"  # Green or Red
                    exec_detail = execution_details[idx] if idx < len(execution_details) else {}
                    
                    # Prepare data attributes for JavaScript
                    exec_id = exec_detail.get('id', '')
                    exec_date = html_escape.escape(str(exec_detail.get('date', '')))
                    exec_build = html_escape.escape(str(exec_detail.get('buildTag', '')))
                    # Build execution URL once on the server to avoid JS duplication
                    exec_url = ""
                    if exec_build:
                        exec_url = ReportUrlBuilder.build_dashboard_url(
                            Config.DASHBOARD_BASE_URL,
                            exec_build,
                            "html/index.html",
                            project_name_from_path,
                            job_name_for_url
                        )
                        exec_url = html_escape.escape(exec_url)
                    # Get error message (already cleaned of "Results Url:" lines from DB fetch)
                    raw_error = str(exec_detail.get('failureReason', ''))
                    # Remove leading whitespace from each line and trim overall
                    cleaned_error_lines = [line.lstrip() for line in raw_error.split('\n')]
                    cleaned_error = '\n'.join(cleaned_error_lines).strip()
                    exec_error = html_escape.escape(cleaned_error)  # Full error message, no truncation, whitespace trimmed
                    exec_status = html_escape.escape(str(exec_detail.get('testStatus', '')))
                    is_padded = exec_detail.get('padded', False)
                    
                    # Create unique ID for this dot
                    test_hash = abs(hash(test_name_escaped)) % 100000
                    dot_id = f"dot_{test_hash}_{idx}"
                    
                    # Make dots clickable (all dots are clickable, but padded ones won't show details)
                    cursor_style = "cursor: pointer;"
                    title_text = f"Execution {idx + 1} ({'Pass' if status == 1 else 'Fail'})" + (f" - {exec_date}" if exec_date else "")
                    
                    # Add data attribute to indicate pass/fail status (0 = fail, 1 = pass)
                    history_status = "pass" if status == 1 else "fail"
                    
                    # Use data attributes and event listener instead of inline onclick to avoid escaping issues
                    history_html += f'''
                        <span 
                            class="history-dot" 
                            id="{dot_id}"
                            data-test-name="{test_name_escaped}"
                            data-execution-index="{idx}"
                            data-execution-id="{exec_id}"
                            data-execution-date="{exec_date}"
                            data-execution-build="{exec_build}"
                            data-execution-url="{exec_url}"
                            data-execution-error="{exec_error}"
                            data-execution-status="{exec_status}"
                            data-history-status="{history_status}"
                            data-is-padded="{is_padded}"
                            style="display:inline-block; width:14px; height:14px; background-color:{color}; border-radius:50%; margin-right:3px; vertical-align:middle; {cursor_style}"
                            title="{title_text}"
                        ></span>
                    '''
                
                # Get failure pattern
                failure_pattern = failure.get('failure_pattern', 'Unknown pattern')
                pattern_escaped = html_escape.escape(failure_pattern)
                
                # Color code based on pattern - modern, subtle colors
                pattern_color = "#6c757d"  # Default gray
                pattern_bg = "#f1f3f5"  # Default light gray background
                if "Continuously failing due to same reason" in failure_pattern:
                    pattern_color = "#d63384"  # Modern pink/red
                    pattern_bg = "#fff0f6"  # Very light pink background
                elif "Continuously failing but different reasons" in failure_pattern:
                    pattern_color = "#fd7e14"  # Modern orange
                    pattern_bg = "#fff4e6"  # Very light orange background
                elif "Intermittently failing due to same reason" in failure_pattern:
                    pattern_color = "#ffc107"  # Amber
                    pattern_bg = "#fffbf0"  # Very light yellow background
                elif "Intermittently failing but different reasons" in failure_pattern:
                    pattern_color = "#0dcaf0"  # Modern cyan
                    pattern_bg = "#e7f8ff"  # Very light cyan background
                elif "multi failure types" in failure_pattern.lower():
                    pattern_color = "#6f42c1"  # Modern purple
                    pattern_bg = "#f3e8ff"  # Very light purple background
                
                # Show full name as tooltip for debugging
                full_name_escaped = html_escape.escape(full_name)
                display_name_escaped = html_escape.escape(display_name)
                
                # Create unique ID for details row (must match dot ID pattern)
                test_hash = abs(hash(test_name_escaped)) % 100000
                details_row_id = f"details_{test_hash}"
                
                html += f"""
                            <tr>
                                <td>
                                    <div class="test-name" title="{full_name_escaped}">{display_name_escaped}</div>
                                </td>
                                <td>
                                    <div class="history-dots-container">{history_html}</div>
                                </td>
                                <td>
                                    <div class="pattern-badge" style="color: {pattern_color}; background-color: {pattern_bg};">{pattern_escaped}</div>
                                </td>
                            </tr>
                            <tr id="{details_row_id}" class="execution-details-row" style="display: none;">
                                <td colspan="3" style="padding: 0;">
                                    <div class="execution-details-content" style="padding: 16px; background-color: #f8f9fa; border-left: 3px solid #495057; margin: 12px 14px; border-radius: 6px; position: relative;">
                                        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                                            <div style="font-weight: 600; color: #495057; font-size: 12px;">
                                                📋 Execution Details
                                            </div>
                                            <button onclick="closeExecutionDetails('{details_row_id}')" style="background-color: #6c757d; color: white; border: none; border-radius: 2px; padding: 3px 7px; cursor: pointer; font-size: 10px; font-weight: 600;" title="Close details">
                                                ✕ Close
                                            </button>
                                        </div>
                                        <div id="{details_row_id}_content" style="color: #6c757d; font-size: 12px; text-align: left;">
                                            Click on a dot above to view execution details
                                        </div>
                                    </div>
                                </td>
                            </tr>
                """
            html += """
                        </tbody>
                    </table>
                </div>
            """
        else:
            # Show message when no recurring failures found
            html += f"""
                <div class="section-content">
                    <p style="color: #6c757d; padding: 20px; text-align: center; font-style: italic;">
                        ✅ No flaky tests detected in the last {Config.FLAKY_TESTS_LAST_RUNS} runs.
                        <br>
                        <small style="color: #999;">This means tests are either passing consistently or failures are isolated incidents.</small>
                    </p>
                </div>
            """
        html += """
                </div>
            """

        # Build the full logs URL
        # Build the full logs URL
        full_logs_url = ReportUrlBuilder.build_dashboard_url(Config.DASHBOARD_BASE_URL, report_name, "html/index.html", project_name_from_path, job_name_from_path)
        
        html += f"""
                <div class="footer">
                    Generated by <b>QA AI Agent</b> • <a href="{full_logs_url}" target="_blank" style="color: #3498db; text-decoration: none;">View Full Logs</a>
                </div>
            </div>
        <script>
""" + js_scripts + """
        </script>
        </body>
        </html>
        """
        
        return html, test_api_map

