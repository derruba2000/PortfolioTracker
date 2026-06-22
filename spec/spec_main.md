Here is a comprehensive low-level technical design document and implementation plan tailored for a **Python-based stack using SQLite as the database and Gradio as the frontend UI**.

This document is structured to be handed directly to a development team, translating your business needs into architectural decisions and actionable Agile tickets.

---

# 🏗️ Technical Architecture & Low-Level Design

### Tech Stack

* **Frontend:** Gradio (Python) using `gr.Blocks()` for tabbed navigation and interactive dashboards.
* **Backend Logic:** Python 3.10+ (using `Pandas` for financial timeseries vectorization and `yfinance`/external APIs for market data).
* **Database:** SQLite3.
* **ORM:** SQLAlchemy (to map Python objects to SQLite and handle relationships safely).

### Addressing the SQLite "Decimal" Constraint

*Requirement:* "Use Decimal data types... rather than floating-point."
*Design Choice:* SQLite does not have a native `DECIMAL` type (it uses `REAL` for floating points). To strictly fulfill the data integrity requirement, the SQLAlchemy models will store financial values as `Integer` (representing cents/basis points, e.g., $100.50 stored as 10050) OR as `String/Text` converted to Python's exact `decimal.Decimal` object on the fly.

---

## 🗄️ Database Schema (SQLite via SQLAlchemy)

Here is the relational mapping required to support your Data Foundation and Strategic Modeling.

* **`Brokers`**: `id` (PK), `name`
* **`Accounts`**: `id` (PK), `broker_id` (FK), `name`, `description`, `currency_code`, `tax_wrapper_type`, `is_simulated` (Boolean, default False)
* **`Portfolios`**: `id` (PK), `account_id` (FK), `name`, `description`
* **`Strategies`**: `id` (PK), `name`, `description`
* **`AccountStrategies`**: `account_id` (FK), `strategy_id` (FK), `allocation_weight` (e.g., 0.70 for 70%)
* **`Securities`**: `id` (PK), `ticker`, `name`, `asset_class`, `currency_code`
* **`Benchmarks`**: `id` (PK), `ticker`, `name`
* **`Transactions`**: `id` (PK), `portfolio_id` (FK), `security_id` (FK), `date` (DateTime), `type` (Enum: BUY, SELL, DIVIDEND, SPLIT), `description`, `quantity` (Decimal), `price` (Decimal), `fees` (Decimal), `total_value` (Decimal), `currency_exchange_rate` (Decimal).
* **`PriceHistory`**: `security_id` (FK), `date` (Date), `close_price` (Decimal) — *Unique constraint on (security_id, date).*
* **`FxRateHistory`**: `base_currency_code`, `quote_currency_code`, `date`, `rate` — *Unique constraint on (base_currency_code, quote_currency_code, date).*

---

## 🗺️ Use Case to Technical Requirement Mapping

| User Use Case | Technical Implementation | Gradio UI Component |
| --- | --- | --- |
| **The Data Entry** | Create/Update endpoints for `Transactions` table. CSV parser for bulk uploads mapping to SQLAlchemy schema. | `gr.Tab("Data Entry")` containing `gr.Textbox`, `gr.Dropdown` forms, and a `gr.File` upload block. |
| **The Daily Check-In** | Aggregate `Transactions` to current positions. Fetch latest EOD prices from `PriceHistory`. Calculate Current Value = Quantity * Price. | `gr.Tab("Dashboard")` with `gr.Dataframe` for positions and `gr.LinePlot` for equity curve. |
| **The Rebalancer** | Query `AccountStrategies`. Calculate current asset class % vs target %. Output drift delta. | `gr.Tab("Rebalance")` with a `gr.BarPlot` showing Actual vs Target, and a generated text list of suggested Buy/Sells. |
| **The Tax Prepper** | Filter `Transactions` by year. Implement FIFO (First In, First Out) algorithm in Python to match BUY lots to SELL lots to calculate Realized Gains. | `gr.Tab("Tax Reports")` with `gr.Dropdown` for Tax Year, outputting a downloadable `gr.Dataframe`. |
| **The Performance Analyst** | Time-Series analysis. Calculate daily portfolio value, adjust for cash flows (deposits/withdrawals), apply TWR formula, overlay Benchmark `PriceHistory`. | `gr.Tab("Performance")` comparing portfolio TWR vs `Benchmarks` via `gr.LinePlot`. |

---

## 📋 Consolidated Functional & Non-Functional Requirements

**FR1. Data Ingestion Module:** System must expose APIs (internal Python functions) to log manual trades and parse standard CSV formats. Must handle corporate actions (Splits adjust `quantity` and cost basis without creating a cash flow).
**FR2. Market Data Pipeline:** System requires a scheduled task (e.g., cron, background thread, or manual UI trigger) to fetch EOD prices into `PriceHistory` and FX rates into `FxRateHistory` via `yfinance` or similar.
**FR3. Analytical Engine (Python/Pandas):** * *Cost Basis:* Must calculate average cost per share.

* *TWR:* Must calculate daily valuation and Time-Weighted Return to isolate performance from external cash flows.
* *Tax Lots:* Must implement FIFO queue for shares to calculate Realized Capital Gains accurately.
**NFR1. Security & Local Deployment:** Application is single-user, deployed locally via Gradio. If hosted remotely, Gradio's native authentication (`gr.Blocks().launch(auth=("user", "pass"))`) must be enabled.
**NFR2. Data Integrity:** All currency and share quantities must use exact decimal arithmetic (Python `decimal` module).
**NFR3. Extensibility:** Asset classes and trade types must be Enums to allow future expansion (Crypto, Real Estate) without altering table schemas.
**NFR4. Simulation Firewall:** Any query calculating Global Net Worth, Total Performance, or Dashboard Summary must exclude simulated accounts by default with `WHERE account.is_simulated = False`. Simulated accounts are visible only when explicitly requested or in a dedicated sandbox view.

---

## 🎟️ Development Tickets (Agile Epics & Stories)

These tickets are ready to be imported into Jira, Trello, or GitHub Projects.

### Epic 1: Scaffold & Data Foundation

* **Ticket 1.1: Project Setup & Gradio Skeleton**
* *Task:* Initialize Python environment, install `gradio`, `sqlalchemy`, `pandas`. Create a basic Gradio app with tabs (Dashboard, Brokers, Accounts, Portfolios, Data Entry, Market Data, Performance, Tax, Settings).


* **Ticket 1.2: SQLite Database & SQLAlchemy ORM**
* *Task:* Implement SQLAlchemy models for the 4-tier hierarchy `Broker -> Account -> Portfolio -> Transaction`, plus `Securities`. Add `tax_wrapper_type` and `is_simulated = Column(Boolean, default=False)` to `Account`. Implement `TypeDecorators` to handle precise Decimals in SQLite. Create DB initialization script.


* **Ticket 1.3: Strategic Modeling Schema**
* *Task:* Add `Strategies`, `AccountStrategies`, and `Benchmarks` tables. Create seed data script for default asset classes and benchmarks.



### Epic 2: Data Ingestion (The Data Entry)

* **Ticket 2.1: Manual Transaction UI**
* *Task:* Build Gradio form for manual trade entry (Date, Ticker, Type, Quantity, Price, Fees). Include dependent dropdowns so choosing an Account dynamically updates the Portfolio dropdown to show only portfolios assigned to that account. Wire to SQLAlchemy `Session.add()`.


* **Ticket 2.2: CSV Bulk Import Engine**
* *Task:* Build a Python service that takes a Pandas DataFrame (from Gradio `gr.File` upload), accepts a `portfolio_id` selected in the UI, maps columns, validates data, and bulk-inserts into the `Transactions` table for the selected sub-portfolio.


* **Ticket 2.3: Corporate Actions Handling (Splits/Dividends)**
* *Task:* Write backend logic to process SPLIT transactions (multiplying existing holding quantities and dividing cost basis) and DIVIDEND transactions (updating cash balance / yield tracking).


* **Ticket 2.4: Account Creation UI (Real vs Test)**
* *Task:* Add a dedicated Accounts tab. When creating a new Account via the Gradio UI, add a Toggle/Checkbox for "Is this a Simulation / Paper Trading account?". Account creation must not create a portfolio automatically. Ensure simulated accounts are visually distinguished in dropdown menus with a "TEST" badge. Include a read-only table listing all accounts.


* **Ticket 2.5: Portfolio Creation UI**
* *Task:* Add a dedicated Portfolios tab. Let the user select an existing Account and create one or more Portfolios under that Account. The Data Entry Account and Portfolio dropdowns must refresh from these records. Include a read-only table listing all portfolios.


* **Ticket 2.6: Broker Listing UI**
* *Task:* Add a dedicated Brokers tab listing all broker records created through account setup.



### Epic 3: Market Data Engine

* **Ticket 3.1: EOD Price Fetcher**
* *Task:* Integrate `yfinance` (or similar API). Write a function that checks unique `Securities` in the DB and fetches missing daily closing prices, saving to `PriceHistory`. Add a local Gradio Market Data tab for manual refresh.


* **Ticket 3.2: FX / Currency Conversion**
* *Task:* Add logic to fetch historical FX rates into `FxRateHistory` if an Account currency differs from a Security currency. Normalise all reporting to the Account's base currency in downstream analytics.



### Epic 4: Analytics Core (The Backend Brain)

* **Ticket 4.1: Current Position Calculator**
* *Task:* Write a Pandas/SQL querying function that aggregates `Transactions` to output current holdings (Ticker, Total Shares, Average Cost). Exclude simulated accounts by default.


* **Ticket 4.2: Realized & Unrealized P&L**
* *Task:* Combine Position Calculator with latest `PriceHistory` to calculate Unrealized P&L. Implement FIFO lot matching to calculate Realized P&L on SELL transactions. Expose realized P&L in the Tax tab.


* **Ticket 4.3: Time-Weighted Return (TWR) Engine**
* *Task:* Build the complex timeseries algorithm: calculate daily portfolio value, identify days with cash flows (deposits/withdrawals), calculate sub-period returns, and geometrically link them for TWR. Expose the curve in the Performance tab.



### Epic 5: Dashboard & UI (The Daily Check-in)

* **Ticket 5.1: Main Dashboard UI**
* *Task:* Wire Ticket 4.1 & 4.2 to the Gradio Dashboard tab. Display Total Net Worth, Daily P&L, and a `gr.Dataframe` of all current open positions. Add a global Live Mode / Sandbox Mode switch at the top of the app. Live Mode filters out simulated accounts. Sandbox Mode shows only simulated accounts and changes the dashboard color treatment to avoid confusion.


* **Ticket 5.2: Risk & Allocation Visualizations**
* *Task:* Group positions by `asset_class` and `currency`. Render dashboard allocation visualizations using Gradio plot components. Apply the global Live/Sandbox account mode to these visualizations.



### Epic 6: Strategic Rebalancing & Tax (Advanced Features)

* **Ticket 6.1: The Rebalancer UI**
* *Task:* Compare current Asset Allocation against `AccountStrategies` targets. Calculate the "Drift" and display buy/sell recommendations to return to target weights. Allow the user to set account target allocations by asset class.


* **Ticket 6.2: Tax Prepper Report**
* *Task:* Create a Gradio tab filtering the FIFO Realized Gains engine by Fiscal Year. Export a consolidated report of gains, losses, and total dividends received as CSV.


* **Ticket 6.3: Benchmark Overlay**
* *Task:* On the Performance tab, plot the portfolio's TWR equity curve against a selected `Benchmark` (e.g., S&P 500) normalized to base 100 for visual comparison. Fetch benchmark history on demand.
