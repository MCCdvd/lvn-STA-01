# LVN STA-01

Repository for LVN backtesting and parameter optimization across multiple tickers.

## Core scripts

- `backtest.py`: single-ticker backtest engine.
- `optimizer.py`: monthly optimizer, baseline comparison, and `optimized_params.json` generation.
- `run_all_tickers_backtest.py`: batch backtest runner using optimized parameters.
- `scripts/log_results.py`: SQLite logger for daily and monthly runs.
- `scripts/send_email.py`: SMTP email sender with retry logic.

## Automated production workflows

### Daily backtest (`.github/workflows/daily-backtest.yml`)

- Trigger: every day at **08:00 Europe/Rome** (DST-safe schedule gate).
- Runs `run_all_tickers_backtest.py` with `optimized_params.json`.
- Logs results in `backtest_results.db`.
- Sends email to `dmacchiarini@gmail.com` containing:
  - complete ticker ranking (best to worst)
  - total P&L summary
  - execution time
- On failure, sends an error alert email with log/stack trace tail.

### Monthly optimization (`.github/workflows/monthly-optimize.yml`)

- Trigger: **1st day of month, 10:00 Europe/Rome** (DST-safe schedule gate).
- Runs `optimizer.py` and refreshes `optimized_params.json`.
- Logs optimization run and per-ticker parameter ranking in SQLite.
- Sends email including:
  - new optimized parameters summary
  - performance comparison (old vs new from SQLite history)
  - top/bottom performers
- On failure, sends an error alert email with log/stack trace tail.

## SQLite database

Database file: `backtest_results.db` (created automatically on first run).

Main tables:

- `daily_backtest_runs`
- `daily_backtest_tickers`
- `monthly_optimization_runs`
- `monthly_optimization_tickers`

Quick local query example:

```bash
sqlite3 backtest_results.db "SELECT run_timestamp_utc,total_pnl FROM daily_backtest_runs ORDER BY id DESC LIMIT 5;"
```

## GitHub Secrets setup (required)

Add these repository secrets:

- `EMAIL_ADDRESS`: Gmail sender address
- `EMAIL_PASSWORD`: Gmail App Password (not the normal account password)

### Gmail App Password steps

1. Enable 2-Step Verification on the sender Gmail account.
2. Generate an App Password from Google Account security settings.
3. Use that App Password as `EMAIL_PASSWORD`.

SMTP settings used by the project:

- Host: `smtp.gmail.com`
- Port: `587`
- TLS: enabled

## Manual smoke commands

Daily batch run:

```bash
python run_all_tickers_backtest.py --optimized-params optimized_params.json --data-dir . --output-dir output/production --parallel --max-workers 4
```

Monthly optimization run:

```bash
python optimizer.py --data-dir . --output-dir output/optimization --optimized-params-file optimized_params.json
```

Log daily results to SQLite:

```bash
python scripts/log_results.py --db-path backtest_results.db daily --summary-csv output/production/batch_summary.csv --ticker-csv output/production/ticker_results.csv
```
