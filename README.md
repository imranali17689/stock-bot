# Stock Bot 🤖

An autonomous stock trading system that uses AI-powered sentiment analysis to execute daily trades on Alpaca's paper trading platform.

## How It Works

1. **8:00 AM** — Signal engine pulls the latest news for 30 tickers from Finnhub, scores sentiment using Claude AI (bullish/bearish/neutral with confidence rating), and stores results in Supabase
2. **8:30 AM** — Trader reads today's signals and opens positions for any ticker scoring 7+ bullish
3. **Every 30 min (9AM–3:30PM)** — Position manager checks all open positions and closes anything hitting -5% stop loss or +10% take profit
4. **3:45 PM** — EOD close liquidates all remaining positions and logs a daily performance snapshot

## Stack

- **Python** — core system
- **Anthropic Claude API** — LLM sentiment scoring
- **Finnhub API** — live news feed
- **Alpaca API** — paper trade execution
- **Supabase** — signal history, trade log, performance snapshots
- **APScheduler** — job scheduling
- **Railway** — cloud deployment (runs 24/7 without local machine)

## Architecture

signal_engine.py     # News ingestion + Claude sentiment scoring
trader.py            # Alpaca order execution based on signals
position_manager.py  # Stop loss / take profit / EOD close logic
scheduler.py         # Orchestrates all jobs on a daily cron schedule

## Database Tables

- `signals` — daily sentiment scores per ticker (score, direction, confidence, summary)
- `trades` — full trade lifecycle (entry price, exit price, P&L, exit reason)
- `performance_snapshots` — daily portfolio value vs SPY benchmark

## Usage

Normal operation (runs all jobs on schedule):
python scheduler.py

Test individual components:
python scheduler.py --run-signals
python scheduler.py --run-trader
python scheduler.py --run-manager
python scheduler.py --run-eod

## Configuration

Create a .env file with:
ALPACA_API_KEY=
ALPACA_SECRET_KEY=
ALPACA_BASE_URL=https://paper-api.alpaca.markets
FINNHUB_API_KEY=
ANTHROPIC_API_KEY=
SUPABASE_URL=
SUPABASE_SECRET_KEY=