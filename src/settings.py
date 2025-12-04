"""
Configuration management for the QA AI Agent.
Centralizes environment variable loading, configuration, and constants.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables once at module level
_config_path = Path(__file__).parent.parent / 'config' / '.env'
if _config_path.exists():
    load_dotenv(_config_path)
else:
    # Fallback to root .env if config/.env doesn't exist
    load_dotenv(Path(__file__).parent.parent / '.env')


class Config:
    """Centralized configuration class"""
    
    # Database Configuration
    DB_HOST = os.getenv('DB_HOST', 'localhost')
    DB_PORT = int(os.getenv('DB_PORT', '3306'))
    DB_USER = os.getenv('DB_USER', 'root')
    DB_PASSWORD = os.getenv('DB_PASSWORD', '')
    DB_NAME = os.getenv('DB_NAME', 'thanos')
    
    # LLM Configuration
    LLM_PROVIDER = os.getenv('LLM_PROVIDER', 'ollama').lower()
    OLLAMA_MODEL = os.getenv('OLLAMA_MODEL', 'llama3.2:3b')
    OLLAMA_BASE_URL = os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
    
    # Report Configuration
    INPUT_DIR = os.getenv('INPUT_DIR', 'testdata')
    OUTPUT_DIR = os.getenv('OUTPUT_DIR', 'reports')
    
    # Dashboard URL Configuration (for linking to test reports)
    DASHBOARD_BASE_URL = os.getenv('DASHBOARD_BASE_URL', 'https://qa.dashboard.example.com')
    
    # Logging Configuration
    LOG_FILE_NAME = 'agent.log'
    LOG_FORMAT = '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    
    # Flaky Tests Detection Constants
    FLAKY_TESTS_LAST_RUNS = int(os.getenv('FLAKY_TESTS_LAST_RUNS', '10'))  # X: Number of last runs to check
    FLAKY_TESTS_MIN_FAILURES = int(os.getenv('FLAKY_TESTS_MIN_FAILURES', '5'))  # Y: Minimum failures required
    
    @classmethod
    def get_db_config(cls) -> dict:
        """Get database configuration dictionary"""
        return {
            'host': cls.DB_HOST,
            'port': cls.DB_PORT,
            'user': cls.DB_USER,
            'password': cls.DB_PASSWORD,
            'database': cls.DB_NAME
        }

