# Portfolio Management

Local Python 3.12 portfolio management app using Gradio, SQLAlchemy, Pandas, and SQLite.

## Setup

```bash
poetry install
poetry run portfolio-init-db
poetry run portfolio-app
```

The SQLite database path is configured in `.env`:

```bash
DATABASE_PATH=/Users/joaoramo/Data/trading_experiment/portfolio_management.sqlite3
```

The app creates the parent database directory automatically.

## Developer Documentation

See [doc/architecture.md](doc/architecture.md) for the solution architecture, Mermaid diagrams, database model, startup flow, and onboarding notes.

## Account And Portfolio Workflow

Use the `Brokers` tab to view all brokers that have been created.

Use the `Accounts` tab to create broker accounts, including an optional description. Creating an account does not create a portfolio automatically. Existing account descriptions can be loaded, edited, and saved from the same tab.

Use the `Portfolios` tab to add one or more portfolios to an existing account, including an optional description. The `Data Entry` tab then uses dependent dropdowns: select an account first, then select one of that account's portfolios before adding or importing transactions.

The `Accounts` and `Portfolios` tabs include read-only tables so you can review what has already been configured.

## Market Data

Use the `Market Data` tab to fetch missing daily close prices and FX rates via Yahoo Finance.

- Security prices are stored in `price_history`.
- FX rates are stored in `fx_rate_history`.
- FX pairs use Yahoo Finance symbols such as `EURGBP=X`.
- The date range is optional; if omitted, the app looks back 365 days and only inserts missing rows.

## Analytics

The global mode switch controls analytics views:

- `Live Mode`: dashboard, performance, and tax analytics show real accounts only.
- `Sandbox Mode`: dashboard, performance, and tax analytics show simulated accounts only.

The dashboard shows a different colored banner in Sandbox Mode so simulated results are visually distinct.

Current analytics include:

- Current position quantity and average cost
- Latest-price market value from `price_history`
- Unrealized P&L
- Allocation by asset class
- Allocation by currency
- FIFO realized P&L in the `Tax` tab
- Time-weighted return curve in the `Performance` tab

The TWR engine treats `DEPOSIT` and `WITHDRAWAL` transactions without a security as external cash flows.

## Advanced Tools

The `Rebalance` tab lets you set target asset-class weights per account and compare them against the current allocation. The resulting table shows drift plus suggested buy/sell value by asset class.

The `Tax` tab includes:

- FIFO realized gains
- Dividend rows in the tax-prep report
- CSV export for the tax-prep report

The `Performance` tab can overlay the portfolio TWR index against a selected benchmark. Benchmark data is fetched on demand when you click `Refresh Benchmark Overlay`.

## CSV Transaction Import

The Data Entry tab imports CSV files into the selected portfolio. Common aliases such as `Symbol` for `Ticker`, `Shares` for `Quantity`, `Fee` for `Fees`, `Amount` for `Total Value`, and `Notes` or `Memo` for `Description` are supported.

Recommended columns:

```csv
Date,Type,Description,Ticker,Security Name,Asset Class,Security Currency,Quantity,Price,Fees,Total Value,FX Rate
2026-06-21,BUY,Initial allocation,VWCE,Vanguard FTSE All-World UCITS ETF,ETF,EUR,2.5,100.25,1.50,,1
2026-06-22,DIVIDEND,Quarterly distribution,VWCE,Vanguard FTSE All-World UCITS ETF,ETF,EUR,1,3.25,0,,1
2026-06-23,SPLIT,Share split,VWCE,Vanguard FTSE All-World UCITS ETF,ETF,EUR,2,0,0,,1
```

For `SPLIT`, store the split ratio in `Quantity`; for example `2` means a 2-for-1 split. Split transactions are stored with zero cash flow.

## Simulated Accounts

Accounts can be marked as simulation or paper trading accounts. Any future global net worth, total performance, or dashboard summary query must exclude simulated accounts by default using `exclude_simulated_accounts`.
