"""
Database connection and helper functions for MySQL operations.
Centralizes all database-related code.
"""

import re
import logging
from typing import Optional, Dict

try:
    import mysql.connector
    from mysql.connector import Error
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False
    Error = Exception  # Fallback for type hints

from .settings import Config

logger = logging.getLogger(__name__)

if not MYSQL_AVAILABLE:
    logger.warning("mysql-connector-python not installed. MySQL features will be disabled.")


class Database:
    """Database connection and helper functions"""
    
    def __init__(self):
        """Initialize database connection with configuration from Config"""
        if not MYSQL_AVAILABLE:
            raise ImportError("mysql-connector-python is required. Install with: pip install mysql-connector-python")
        
        self.db_config = Config.get_db_config()
    
    def get_connection(self):
        """Get MySQL database connection."""
        if not MYSQL_AVAILABLE:
            raise ImportError("mysql-connector-python is not installed")
        
        try:
            connection = mysql.connector.connect(**self.db_config)
            return connection
        except Error as e:
            logger.error(f"Error connecting to MySQL database: {e}")
            raise
    
    @staticmethod
    def get_table_name_from_report_name(report_name: str) -> Optional[str]:
        """
        Map report name to database table name.
        Example: "Regression-AccountOpening-Tests-420" -> "results_accountopening"
        Example: "ProdSanity-All-Tests-524" -> "results_prodsanity"
        
        Args:
            report_name: Report name like "Regression-AccountOpening-Tests-420" or "ProdSanity-All-Tests-524"
            
        Returns:
            Table name like "results_accountopening" or "results_prodsanity" or None if pattern doesn't match
        """
        if not report_name:
            return None
        
        # Pattern 1: "Regression-AccountOpening-Tests-420" -> "results_accountopening"
        match = re.search(r'Regression-([A-Za-z]+)-', report_name)
        if match:
            project_name = match.group(1).lower()
            return f"results_{project_name}"
        
        # Pattern 2: "ProdSanity-All-Tests-524" -> "results_prodsanity"
        match = re.search(r'ProdSanity-', report_name)
        if match:
            return "results_prodsanity"
        
        # Fallback: try to extract any word after "Regression-"
        match = re.search(r'Regression-([A-Za-z]+)', report_name)
        if match:
            project_name = match.group(1).lower()
            return f"results_{project_name}"
        
        logger.warning(f"Could not extract table name from report_name: {report_name}")
        return None

