# Portfolio Tracker

Local-first portfolio management app built with Python 3.12, Gradio, SQLAlchemy, Pandas, and SQLite.

## Quick Start

```bash
poetry install
poetry run portfolio-init-db
poetry run portfolio-app
```

The app runs at `http://127.0.0.1:7860`.

## Configuration

Database path is read from `.env` using `DATABASE_PATH`.

```bash
DATABASE_PATH=/Users/joaoramo/Data/trading_experiment/portfolio_management.sqlite3
```

If `.env` is missing, a default path from `config.py` is used.

The parent database directory is created automatically.

## Commands

```bash
poetry run portfolio-init-db   # create/update schema and seed defaults
poetry run portfolio-seed-db   # seed default benchmarks and strategies
poetry run portfolio-app       # run UI app (initializes DB first)
poetry run pytest              # run test suite
```

## UI Overview

Top-level tabs:

- Dashboard
- Rebalance
- Master Data
- Transactions Entry
- Performance
- Tax
- Import / Export
- Settings

Nested tabs:

- Master Data: Brokers, Accounts, Portfolios, Securities
- Transactions Entry: Transactions, Cash Transfer

## Main Workflows

The Dashboard reporting-currency filter converts all position values, totals, and
allocation charts to GBP, EUR, or USD using the latest available FX close on or
before today.

### 1) Master Data

- Create and manage brokers.
- Create and edit accounts (currency, tax wrapper, simulated flag, active flag).
- Create and edit portfolios (description, URL, active flag).
- Manage securities and ticker defaults.

### 2) Transactions

- Add manual transactions (`BUY`, `SELL`, `DIVIDEND`, `SPLIT`, `DEPOSIT`, `WITHDRAWAL`).
- Import CSV into the selected portfolio.
- Transfer cash between accounts (creates paired withdrawal/deposit entries).
- Filter tables by `All`, `Real`, or `Test`.

CSV aliases supported include `Symbol -> Ticker`, `Shares -> Quantity`, `Fee -> Fees`, `Amount -> Total Value`, and `Notes/Memo -> Description`.

### 3) Market Data Import

Use `Import / Export > Import Market Data` to merge prices and FX rates from the
Delta table paths configured in Settings:

- Price rows are stored in `price_history`.
- FX rows are stored in `fx_rate_history`.
- Existing symbol/date rows are updated and new rows are inserted.
- Import failures are stored in `import_error_logs`.

### 4) Analytics, Rebalance, Tax

- Dashboard shows summary, positions, and allocation charts.
- Performance tab shows portfolio TWR and benchmark overlay.
- Rebalance tab compares current vs target asset-class allocation and suggests trades.
- Tax tab shows FIFO realized gains, tax-prep report, and CSV export.

## Live And Sandbox Modes

A global mode toggle controls Dashboard, Performance, and Tax outputs:

- `Live Mode`: includes real accounts only.
- `Sandbox Mode`: includes simulated accounts only.

This prevents simulated accounts from contaminating real portfolio summaries.

## Settings

Theme selection is saved in:

- `~/.portfolio_management/settings.json`

Current themes: Base, Soft, Monochrome, Glass, Ocean.

## Architecture And Design Notes

Detailed architecture documentation is available at [doc/architecture.md](doc/architecture.md).
