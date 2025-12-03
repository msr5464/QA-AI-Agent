# 🤖 QA AI Agent - Automation Report Analyzer

An intelligent AI-powered agent that automatically analyzes automation test reports using a database-first approach. Queries MySQL for test results, enhances with HTML execution logs, and provides actionable insights by distinguishing between product bugs and automation code issues.

## ✨ Features

### 🎯 Core Capabilities

- **📊 Database-First Data Retrieval**
  - Queries MySQL database for test results by buildTag
  - Extracts execution logs from HTML reports
  - Merges database data with HTML execution logs
  - Handles multiple test suites and formats

- **🤖 Two-Level AI Classification System**
  - Uses OpenAI GPT-4 or Ollama (local LLM) for intelligent analysis
  - **Level 1 - High-Level Classification**:
    - 🐛 **Product Bugs** - Real application defects requiring developer attention
    - 🔧 **Automation Issues** - Test framework problems, flaky tests, locator issues
  - **Level 2 - Root Cause Categories**:
    - **ELEMENT_NOT_FOUND** - Element locator issues, WebElement access problems
    - **TIMEOUT** - Page load timeouts
    - **ASSERTION_FAILURE** - Assertion/validation failures (always Product Bug)
    - **ENVIRONMENT_ISSUE** - Environment-related problems
    - **OTHER** - Unclassified failures
  - Provides confidence levels (HIGH, MEDIUM, LOW) for each classification
  - Extracts root causes and recommended actions
  - Failures grouped by root cause category in "🧩 Failures by Root Cause Category" section

- **📈 Historical Analysis & Trends**
  - Tracks recurring failures over time using MySQL database
  - Identifies flaky tests and patterns
  - Detects trends (improving, declining, stable)
  - Shows execution history with visual indicators

- **📧 Comprehensive Reporting**
  - Generates beautiful, interactive HTML reports with modern UI
  - Executive summaries with actionable insights and donut charts
  - **🧩 Failures by Root Cause Category** - Grouped failures with expandable details
  - **⚠️ Intermittent Failures** - Flaky test detection with execution history
  - Copy-to-clipboard functionality, tooltips, and interactive elements
  - Slack integration
  - Grouped failures by root cause categories and API endpoints

- **🔍 Advanced Analysis**
  - API endpoint extraction and grouping
  - Similar failure detection
  - Root cause normalization (handles dynamic values)
  - Execution history visualization

## 🚀 Quick Start

### Prerequisites

- Python 3.9+ (3.11+ recommended)
- MySQL database (for historical tracking)
- OpenAI API key OR Ollama installed locally

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd myAgents

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Configuration

1. **Create environment file**:
```bash
cp config/.env.example config/.env
```

2. **Edit `config/.env`**:
   - Set `LLM_PROVIDER=ollama` to use the bundled local workflow (default) or switch to `openai` if you have API access.
   - Adjust the `INPUT_DIR`/`OUTPUT_DIR` paths to wherever your reports live.
   - Provide your database, Slack, and flaky-test thresholds as needed.

> Refer to `config/.env.example` for the complete list of supported variables and default values.

### Running the Agent

**macOS/Linux**

```bash
./scripts/run.sh --report-dir testdata/Regression-AccountOpening-Tests-420 --no-slack
```

**Windows (PowerShell)**

```powershell
.\scripts\run.ps1 --report-dir testdata/Regression-AccountOpening-Tests-420 --no-slack
```

Both scripts default to `--report-dir testdata/Regression-Growth-Tests-442 --no-slack` when no arguments are passed. Supply additional CLI flags (e.g., `--slack-channel`, `--dashboard-url`) exactly as you would with `python src/main.py`.

**Note**: High-level flow — locate report, query MySQL, parse HTML logs, merge everything, run AI analysis, and render HTML/Slack outputs. Full details live in the **Workflow & Data Flow** section below.

The agent uses a database-first approach:
1. Queries MySQL database for test results by buildTag
2. Extracts execution logs from HTML reports
3. Merges database data with HTML logs
4. Analyzes failures using AI (two-level classification system)
5. Generates an interactive HTML report with root cause categories

## 📁 Project Structure

```
myQaAgent/
├── README.md                      # This file
├── requirements.txt               # Python dependencies
├── scripts/                      # Cross-platform helper scripts
│   ├── run.sh                    # macOS/Linux entrypoint
│   ├── run.ps1                   # Windows entrypoint
│   └── windows/
│       └── setup.ps1             # Windows bootstrap script
├── config/
│   ├── .env.example              # Template env variables (copy to .env)
│   ├── .env                      # Local environment values (gitignored)
│   └── prompts.yaml              # AI prompts configuration
├── src/
│   ├── main.py                   # Main orchestrator
│   ├── settings.py               # Centralized configuration & constants
│   ├── database.py               # Database connection & helpers
│   ├── utils.py                  # Common utility functions
│   ├── agent/
│   │   ├── analyzer.py          # AI-powered failure analyzer
│   │   ├── memory.py            # Historical tracking & recurring failures
│   │   └── summary_generator.py # Executive summary generation
│   ├── parsers/
│   │   ├── html_parser.py       # HTML report parser (extracts execution logs)
│   │   ├── data_builder.py      # Merges DB results with HTML logs
│   │   └── models.py            # Data models (TestResult, TestSummary, etc.)
│   └── reporters/
│       ├── report_generator.py   # HTML report generator
│       ├── html_styles.py        # CSS styles (extracted for maintainability)
│       ├── html_scripts.py       # JavaScript code (extracted for maintainability)
│       ├── category_rules.py     # Root cause category classification rules
│       ├── data_validator.py     # Data validation before/after report generation
│       └── slack_reporter.py     # Slack notifications
├── testdata/                     # Default INPUT_DIR (gitignored contents)
├── reports/                      # Default OUTPUT_DIR (gitignored contents)
├── tests/                        # Unit and integration tests
│   ├── unit/
│   └── integration/
```

`testdata/` and `reports/` are the defaults consumed by `Config`. If you store inputs elsewhere, update `INPUT_DIR`/`OUTPUT_DIR` in your `.env`.

All component and architecture details are described directly in this README (see **Architecture & Components** below).

## 🏗 Architecture & Components

The QA AI Agent is built around a modular, database-first architecture so each concern (data ingestion, intelligence, reporting) evolves independently.

### Parsers (`src/parsers/`)
- `html_parser.py` extracts suite metadata, execution logs, API traces, stack traces, and durations from ReportNG/TestNG HTML files.
- `data_builder.py` merges database records with HTML artifacts, deduplicates rows, and produces `TestResult` models with links, logs, and normalized durations.
- `models.py` defines strongly typed data containers such as `TestResult`, `TestSummary`, and `TestStatus`.

### Agent (`src/agent/`)
- `analyzer.py` (TestAnalyzer) builds prompts, calls OpenAI or Ollama, and classifies failures with confidence, root-cause text, and recommended actions.
- `memory.py` (AgentMemory) queries MySQL, reconstructs execution histories, detects recurring failures (default: ≥4 failures across last 10 runs), and computes health trends.
- `summary_generator.py` produces executive summaries (LLM-backed) that highlight category breakdowns, flaky hotspots, and next-step recommendations.

### Reporters (`src/reporters/`)
- `report_generator.py` produces the interactive HTML report, pulling styles from `html_styles.py` and behavior from `html_scripts.py`.
- `category_rules.py` refines AI-provided categories using prioritized rules (e.g., ElementClickIntercepted before Timeout) to keep output consistent release-over-release.
- `data_validator.py` performs pre/post generation validation for data integrity, and `slack_reporter.py` pushes concise summaries to Slack when configured.

### Utilities & Configuration
- `src/utils.py` houses helpers such as `TestNameNormalizer`, HTML cache utilities, and text cleaners for root-cause normalization.
- `src/settings.py` centralizes environment configuration (database, LLM provider, report paths, flaky detection thresholds, dashboards, Slack).

### Key Design Decisions
1. **Database-First**: Prefer querying MySQL first, then enrich with HTML logs for fidelity.
2. **AI + Rules**: Blend LLM flexibility with deterministic rule-engine adjustments.
3. **Historical Context**: Persist past executions for flaky detection and trend reporting.
4. **Separation of Concerns**: Parsers, Agent, and Reporters evolve independently, easing maintenance.

## 🔄 Workflow & Data Flow

1. **Locate report directory** (CLI args or most-recent folder).
2. **Query MySQL** via `AgentMemory` for the matching `buildTag`.
3. **Parse HTML** overview + suite files to capture logs, durations, links.
4. **Merge datasets** into unified `TestResult` objects.
5. **Run historical analysis** to detect recurring failures and trends.
6. **Call AI** for each unique failure (OpenAI or Ollama).
7. **Refine root-cause category** with the rule engine.
8. **Generate executive summary** and metrics.
9. **Render HTML report** with CSS/JS assets.
10. **Save + send notifications** (reports directory + Slack if enabled).

```
┌────────────────────┐
│  Report Directory  │
└────────┬───────────┘
         │
         ▼
┌────────────────────┐
│  AgentMemory (DB)  │─┐
└────────┬───────────┘ │
         │             │
         ▼             │
┌────────────────────┐ │
│   HTML Parsers     │ │
└────────┬───────────┘ │
         │             │
         └────┬────────┘
              ▼
      ┌───────────────┐
      │ Data Builder  │
      └──────┬────────┘
             ▼
      ┌───────────────┐
      │ TestAnalyzer  │
      │ + Rule Engine │
      └──────┬────────┘
             ▼
      ┌───────────────┐
      │ Summary &     │
      │ Report Gen    │
      └──────┬────────┘
             ▼
      ┌───────────────┐
      │ HTML + Slack  │
      └───────────────┘
```

### Phase 1 — Data Collection & Merging
```
Report Dir ─┐
            ├─> HTML Parser (overview + suites) ┐
MySQL DB  ──┘                                   ├─> Data Builder → TestResult[]
            └─> testcaseName, status, logs     ┘
```
- Multiple name-matching strategies (exact, `Class.method`, cleaned class, method-only) keep DB rows aligned with HTML artifacts.
- Execution histories and HTML links are cached for later visualization.

**Data matching strategies**
```
1. Exact match (full testcaseName)
2. Class.method (last two segments)
3. Cleaned class names (dedupe repeated segments)
4. Method-only (case-insensitive) fallback
```

### Phase 2 — AI Analysis & Classification
```
TestResult (failures) ─┬─> TestAnalyzer (LLM)
                       └─> AgentMemory (history/trends)
                                     │
                          FailureClassification[]
                                     │
                         CategoryRuleEngine (priority rules)
                                     │
                         Final grouped categories
```
- Level 1 output: `PRODUCT_BUG` vs `AUTOMATION_ISSUE` with confidence + recommendations.
- Level 2 output: `ELEMENT_NOT_FOUND`, `TIMEOUT`, `ASSERTION_FAILURE`, `ENVIRONMENT_ISSUE`, or `OTHER`.

### Phase 3 — Report Generation
```
Summary stats + classifications + history
        │
        ├─> SummaryGenerator (AI narrative)
        └─> ReportGenerator (HTML/CSS/JS)
                │
                └─> Interactive HTML report + Slack payload
```

### Classification Flow (Two Levels)
```
Test Failure
   │
   ▼
AI Analysis (TestAnalyzer)
   │
   ▼
FailureClassification
   ├─ Level 1: PRODUCT_BUG / AUTOMATION_ISSUE
   └─ Level 2: Initial root_cause_category
        │
        ▼
CategoryRuleEngine (priority order:
 ElementClickIntercepted → PageLoadTimeout → Locator → IllegalArgument → NonPageTimeout → Assertion)
        │
        ▼
Final root cause category → grouped in report
```

### Flaky Test Detection Flow
```
Current + historical test names
        │
        ▼
Query last X runs per test (default 10)
        │
        ▼
Count failures per test
        │
        ▼
Filter occurrences ≥ Y (default 4)
        │
        ▼
Categorize patterns (continuous/intermittent, same/different reason)
        │
        ▼
Sort by severity → Flaky tests table
```

### HTML Report Generation Flow
```
Input data (stats, categories, flaky list, summaries)
        │
        ▼
ReportGenerator
  1. Compose base HTML
  2. Inject CSS (html_styles.py)
  3. Inject JS (html_scripts.py)
  4. Render sections:
     • Header & KPIs
     • Executive Summary
     • 🧩 Failures by Root Cause
     • ⚠️ Flaky Tests
     • Footer & links
        │
        ▼
Save AI-Analysis-Report_*.html + optional Slack notification
```


## 🛠️ Technology Stack

**Core Runtime**
- Python 3.9+ (3.11 recommended for performance)
- MySQL for historical storage
- BeautifulSoup4 + lxml for HTML parsing
- LangChain + httpx for LLM integrations (OpenAI or Ollama)

**AI Providers**
- OpenAI GPT-4 family (`gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`)
- Ollama local models (default `llama3.2:3b`, configurable URL/model)

**Reporting & Tooling**
- HTML5/CSS3/Vanilla JS for interactive reports (donut charts, tooltips, copy-to-clipboard)
- Slack SDK for notifications
- python-dotenv, pathlib, logging for configuration and diagnostics

**Testing**
- pytest + pytest-cov

## 📊 Key Features Explained

Each highlight below maps to the **Architecture**, **Workflow**, and **Report Features** sections earlier in this README.

### 1. Two-Level AI Classification System

The AI analyzes each test failure and classifies it at two levels:

**Level 1 - High-Level**: PRODUCT_BUG or AUTOMATION_ISSUE  
**Level 2 - Root Cause Categories**: ELEMENT_NOT_FOUND, TIMEOUT, ASSERTION_FAILURE, ENVIRONMENT_ISSUE, OTHER

Failures are grouped by root cause category in the "🧩 Failures by Root Cause Category" section of the report (see **Workflow & Data Flow → Classification Flow** above).

### 2. Flaky Test Detection

Identifies tests failing repeatedly (configurable: 4+ failures in last 10 runs) and categorizes failure patterns (see **Workflow & Data Flow → Flaky Test Detection Flow**).

### 3. Historical Analysis & Trends

Tracks test quality trends (improving/declining/stable) and provides execution history visualization. Refer to the **Workflow & Data Flow** section for the full narrative.

Ready to run it in your environment? Configure the basics below and launch via `scripts/run.sh` or `scripts/run.ps1`. Detailed Windows + Jenkins instructions live in `scripts/DEPLOYMENT.md`.

## 🔧 Configuration Options

- **AI provider**: Set `LLM_PROVIDER` to `ollama` (default) or `openai`. When using OpenAI, supply `OPENAI_API_KEY` and your preferred `OPENAI_MODEL`. For Ollama, adjust `OLLAMA_MODEL` / `OLLAMA_BASE_URL` if you host it elsewhere.
- **Database**: Update `DB_HOST`, `DB_USER`, `DB_PASSWORD`, and `DB_NAME` to point at the MySQL instance that stores your automation runs. Each suite/buildTag should have its own results table (e.g., `results_accountopening`).
- **Report paths**: `INPUT_DIR` and `OUTPUT_DIR` default to `testdata/` and `reports/`. Change them in `.env` if your artifacts live somewhere else.
- **Slack & dashboards**: Provide `SLACK_BOT_TOKEN`, `SLACK_CHANNEL`, and `DASHBOARD_BASE_URL` to enable outgoing notifications and deep links.
- **Flaky detection**: Tune `FLAKY_TESTS_LAST_RUNS` (window) and `FLAKY_TESTS_MIN_FAILURES` (threshold) to match your stability expectations.

Full variable list with defaults lives in `config/.env.example`.


## 📈 Report Features

### HTML Report Includes:

1. **Executive Summary** 📊
   - Overall statistics and test suite health
   - Failure breakdown by category (interactive donut chart)
   - Critical flaky tests summary
   - Key insights and actionable recommendations
   - Trend analysis (improving/declining/stable)

2. **🧩 Failures by Root Cause Category**
   - Failures grouped by root cause category:
     - ELEMENT_NOT_FOUND
     - TIMEOUT
     - ASSERTION_FAILURE
     - ENVIRONMENT_ISSUE
     - OTHER
   - Each category shows count, percentage, and representative signals
   - Expandable test details with root cause and recommended actions
   - Copy-to-clipboard and link-to-full-logs functionality

3. **⚠️ Intermittent Failures (Flaky Tests)**
   - Tests failing repeatedly (configurable: 4+ failures in last 10 runs)
   - Execution history visualization with colored dots
   - Failure pattern categorization
   - Clickable dots showing detailed execution information
   - Sorted by severity (most critical first)

4. **Interactive Features**
   - Expandable sections for test details
   - Tooltips on hover
   - Copy testcase names to clipboard
   - Links to full test logs
   - Responsive design for all screen sizes

## 🧪 Testing

- `pytest tests/` – run all unit and integration suites
- `pytest --cov=src tests/` – include coverage reporting
- `pytest tests/unit/test_analyzer.py` – focus on a specific module

## 📚 Documentation

All architectural, workflow, and troubleshooting guidance now lives in this README so onboarding stays in a single place.

## 🔒 Security Notes

- Never commit `config/.env` file (contains API keys and passwords)
- Use environment variables for sensitive data
- Database credentials should be secured
- Consider using parameterized queries for database operations

## 🐛 Troubleshooting

### Common Issues

**Q: No test results found in database?**  
A: Ensure test results have been inserted into MySQL database with the correct `buildTag` matching the report directory name

**Q: Report directory not found?**  
A: Check `INPUT_DIR` path in `config/.env` and ensure report directory exists

**Q: AI classification seems inaccurate?**  
A: Try switching to a different model (e.g., `gpt-4o` instead of `gpt-4o-mini`) or refine prompts in `config/prompts.yaml`

**Q: Database connection errors?**  
A: Verify MySQL is running and credentials in `config/.env` are correct

**Q: Ollama not working?**  
A: Ensure Ollama is running (`ollama serve`) and model is downloaded (`ollama pull llama3.2:3b`)

## 🤝 Contributing

This is currently a private project. For questions or suggestions, contact the development team.

## 📝 License

Internal use only - [Your Company Name]

## 🆘 Support

For issues or questions:
- Revisit the **Workflow & Data Flow** and **Architecture** sections above
- Review the [troubleshooting section](#-troubleshooting)
- Contact the development team