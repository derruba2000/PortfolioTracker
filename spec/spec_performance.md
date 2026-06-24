Here is the complete set of Epics and User Stories structured specifically for an AI coding agent. They are designed to integrate seamlessly into your Python 3.12, Poetry, SQLite, and Gradio environment.

---

## Epic 1: Data Integration & Math Engine Foundation

**Description:** Establish the necessary mathematical dependencies and SQLite data access layer required to calculate complex financial metrics before building the UI.

### Story 1.1: Dependency Management with Poetry

**User Story:** As a developer, I need to ensure the project has the correct libraries for financial calculations and visualizations so that the environment remains reproducible.
**Acceptance Criteria:**

* Add `pandas`, `numpy`, `scipy` (for advanced stats), and `plotly` (for interactive Gradio visualizations) to the project using `poetry add`.
* Verify that all packages are compatible with Python 3.12.
* Update the `poetry.lock` file.

### Story 1.2: SQLite Data Extraction Layer

**User Story:** As the calculation engine, I need to extract historical ticker prices, benchmark data, and user cash flows from the SQLite database to compute accurate metrics.
**Acceptance Criteria:**

* Create a Python module (e.g., `db_performance.py`) to query the SQLite database.
* Implement a function to return daily portfolio values and individual asset prices as Pandas DataFrames.
* Implement a function to retrieve historical cash deposit/withdrawal dates and amounts for Money-Weighted Return (MWR) calculations.

---

## Epic 2: Core Performance & Risk Calculation Engine

**Description:** Implement the backend logic and mathematical formulas for Returns, Risk, Risk-Adjusted Returns, and Benchmarking.

### Story 2.1: Pure Return Metrics (TWR & MWR)

**User Story:** As an investor, I want to see my Time-Weighted and Money-Weighted returns so I can understand both my portfolio's asset performance and my personal timing performance.
**Acceptance Criteria:**

* Implement a function calculating Time-Weighted Return (TWR) using daily valuation periods.
* Implement a function calculating Money-Weighted Return (MWR / IRR) utilizing the cash flow data from SQLite.

### Story 2.2: Risk & Risk-Adjusted Metrics

**User Story:** As an investor, I want to understand my portfolio's volatility, maximum drawdowns, and risk-adjusted ratios to evaluate if my returns justify the risks taken.
**Acceptance Criteria:**

* Implement mathematical functions for Volatility (Standard Deviation) and Maximum Drawdown.
* Implement functions for Beta (covariance of portfolio vs. market variance).
* Implement functions for Sharpe Ratio, Sortino Ratio, and Alpha, assuming a configurable risk-free rate (e.g., 10-year Treasury yield).

### Story 2.3: Advanced Analytics & Benchmarking

**User Story:** As an advanced investor, I want to compare my portfolio against blended benchmarks, evaluate tracking error, and analyze internal correlations to ensure true diversification.
**Acceptance Criteria:**

* Implement a calculation for R-Squared and Tracking Error against a selected SQLite benchmark index.
* Implement a Correlation Matrix generator for all individual tickers currently held in the portfolio.
* Implement a Historical Stress Test function that calculates portfolio performance during predefined historical date ranges (e.g., 2020 COVID crash).

---

## Epic 3: Gradio UI & Visualization Implementation

**Description:** Build the user interface within the Gradio app, placing all performance data under a dedicated "Performance" tab and using horizontal sub-tabs to organize the data logically.

### Story 3.1: Gradio "Performance" Tab Structure

**User Story:** As a user, I want a dedicated Performance tab with horizontal sub-tabs so that I can easily navigate between different categories of financial analysis without clutter.
**Acceptance Criteria:**

* Create a main `gr.Tab("Performance")` in the existing Gradio application.
* Inside the main tab, create horizontal sub-tabs: `gr.Tab("Returns & Risk")`, `gr.Tab("Benchmarking")`, and `gr.Tab("Advanced Analytics")`.

### Story 3.2: Returns & Risk Sub-Tab Visualizations

**User Story:** As a user, I want visual representations of my returns and drawdowns so I can quickly gauge my historical performance.
**Acceptance Criteria:**

* Create a Plotly line chart comparing TWR and MWR over time.
* Create a Plotly "Underwater Chart" (area chart) visualizing Maximum Drawdowns from peak value.
* Display Risk metrics (Volatility, Sharpe, Sortino, Alpha, Beta) using `gr.DataFrame` or `gr.Number` summary cards.

### Story 3.3: Benchmarking Sub-Tab Visualizations

**User Story:** As a user, I want to visually compare my portfolio's trajectory against contextual benchmarks.
**Acceptance Criteria:**

* Add a Gradio Dropdown to select the comparative benchmark (e.g., S&P 500, Blended 60/40).
* Create a Plotly comparative line chart showing portfolio growth vs. benchmark growth.
* Display Tracking Error and R-Squared metrics clearly below the chart.

### Story 3.4: Advanced Analytics Sub-Tab Visualizations

**User Story:** As a user, I want visual tools for correlation and stress testing to optimize my asset allocation.
**Acceptance Criteria:**

* Create a Plotly Heatmap to visualize the Correlation Matrix of portfolio tickers.
* Create a Gradio Bar Chart showing the portfolio's simulated performance during predefined Historical Stress Test periods.

---

## Epic 4: Project Documentation Updates

**Description:** Keep the project's foundational documentation accurate to reflect the new performance analysis architecture, UI additions, and dependencies.

### Story 4.1: Update Architecture Documentation

**User Story:** As a maintainer, I need `architecture.md` updated so I understand how the Gradio UI, SQLite, and math engines interact for the performance feature.
**Acceptance Criteria:**

* Add a new section to `architecture.md` titled "Performance Analysis Engine".
* Document the data flow from SQLite -> Math Modules -> Plotly -> Gradio Tabs.

### Story 4.2: Update Project Readme

**User Story:** As a developer onboarding to the project, I need the `README.md` updated so I know what new features exist and how to run them.
**Acceptance Criteria:**

* Update the features list in `README.md` to include "Advanced Portfolio Performance Analysis (TWR, MWR, Sharpe, Drawdowns)".
* Note any new environment variables or Poetry setup steps required for the new math and plotting dependencies.