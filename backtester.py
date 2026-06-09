#!/usr/bin/env python3
"""
Stock Trading Strategy Backtester
Simulates portfolio performance using historical signals and price data.
"""

import os
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Any
from dotenv import load_dotenv
from supabase import create_client, Client
import numpy as np

# Load environment variables
load_dotenv()

# Configuration
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SECRET_KEY = os.getenv('SUPABASE_SECRET_KEY')

WATCHLIST = [
    'AAPL', 'NVDA', 'MSFT', 'GOOGL', 'AMZN', 
    'META', 'TSLA', 'JPM', 'V', 'AMD'
]

INITIAL_CAPITAL = 10000.0
POSITION_SIZE = 1000.0
BULLISH_THRESHOLD = 7
BEARISH_THRESHOLD = 4

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

class Portfolio:
    """Portfolio class to track holdings and performance."""
    
    def __init__(self, initial_cash: float):
        self.cash = initial_cash
        self.positions = {}  # ticker -> shares
        self.trades = []
        self.portfolio_history = []
        
    def get_portfolio_value(self, prices: Dict[str, float]) -> float:
        """Calculate total portfolio value."""
        stock_value = sum(
            self.positions.get(ticker, 0) * prices.get(ticker, 0) 
            for ticker in self.positions
        )
        return self.cash + stock_value
    
    def buy_stock(self, ticker: str, price: float, date: str, signal_score: int):
        """Buy stock with fixed dollar amount."""
        if self.cash < POSITION_SIZE:
            return False
            
        shares = POSITION_SIZE / price
        self.positions[ticker] = self.positions.get(ticker, 0) + shares
        self.cash -= POSITION_SIZE
        
        self.trades.append({
            'date': date,
            'ticker': ticker,
            'action': 'BUY',
            'shares': shares,
            'price': price,
            'amount': POSITION_SIZE,
            'signal_score': signal_score
        })
        return True
    
    def sell_stock(self, ticker: str, price: float, date: str, signal_score: int):
        """Sell all shares of a stock."""
        if ticker not in self.positions or self.positions[ticker] <= 0:
            return False
            
        shares = self.positions[ticker]
        amount = shares * price
        self.cash += amount
        self.positions[ticker] = 0
        
        self.trades.append({
            'date': date,
            'ticker': ticker,
            'action': 'SELL',
            'shares': shares,
            'price': price,
            'amount': amount,
            'signal_score': signal_score
        })
        return True

def load_signals() -> List[Dict[str, Any]]:
    """Load all signals from Supabase ordered by date."""
    try:
        result = supabase.table('signals').select('*').order('created_at').execute()
        
        if result.data:
            print(f"📡 Loaded {len(result.data)} signals from database")
            return result.data
        else:
            print("📡 No signals found in database")
            return []
            
    except Exception as e:
        print(f"✗ Error loading signals: {e}")
        return []

def load_price_data(tickers: List[str], months: int = 6) -> Dict[str, pd.DataFrame]:
    """Load historical price data for all tickers."""
    print(f"📈 Loading {months} months of price data for {len(tickers)} tickers...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)
    
    price_data = {}
    
    for ticker in tickers:
        try:
            stock = yf.Ticker(ticker)
            data = stock.history(start=start_date, end=end_date)
            
            if not data.empty:
                price_data[ticker] = data
                print(f"✓ {ticker}: {len(data)} days of data")
            else:
                print(f"✗ {ticker}: No data available")
                
        except Exception as e:
            print(f"✗ Error loading {ticker}: {e}")
    
    return price_data

def get_spy_data(months: int = 6) -> pd.DataFrame:
    """Load SPY data for benchmark comparison."""
    print("📊 Loading SPY benchmark data...")
    
    end_date = datetime.now()
    start_date = end_date - timedelta(days=months * 30)
    
    try:
        spy = yf.Ticker('SPY')
        data = spy.history(start=start_date, end=end_date)
        print(f"✓ SPY: {len(data)} days of benchmark data")
        return data
    except Exception as e:
        print(f"✗ Error loading SPY: {e}")
        return pd.DataFrame()

def run_backtest(signals: List[Dict], price_data: Dict[str, pd.DataFrame]) -> Portfolio:
    """Run the backtest simulation."""
    print("🤖 Running backtest simulation...")
    print("=" * 60)
    
    portfolio = Portfolio(INITIAL_CAPITAL)
    
    # Convert signals to DataFrame for easier processing
    signals_df = pd.DataFrame(signals)
    if signals_df.empty:
        print("⚠️ No signals to process")
        return portfolio
    
    signals_df['created_at'] = pd.to_datetime(signals_df['created_at'])
    signals_df['date'] = signals_df['created_at'].dt.date
    
    # Get all unique dates and sort them
    all_dates = sorted(signals_df['date'].unique())
    
    print(f"📅 Backtesting from {all_dates[0]} to {all_dates[-1]}")
    print(f"📊 Processing {len(signals_df)} signals across {len(all_dates)} days")
    
    for date in all_dates:
        day_signals = signals_df[signals_df['date'] == date]
        
        # Get prices for this date
        prices = {}
        for ticker in WATCHLIST:
            if ticker in price_data:
                ticker_data = price_data[ticker]
                # Find the closest trading day
                available_dates = ticker_data.index.date
                closest_date = min(available_dates, key=lambda x: abs((x - date).days))
                prices[ticker] = ticker_data.loc[ticker_data.index.date == closest_date, 'Close'].iloc[0]
        
        # Process signals for this date
        for _, signal in day_signals.iterrows():
            ticker = signal['ticker']
            score = signal['sentiment_score']
            direction = signal['direction']
            
            if ticker not in prices:
                continue
                
            price = prices[ticker]
            
            # Execute trades based on signals
            if direction == 'bullish' and score >= BULLISH_THRESHOLD:
                success = portfolio.buy_stock(ticker, price, str(date), score)
                if success:
                    print(f"📈 {date}: BUY {ticker} @ ${price:.2f} (Score: {score})")
                    
            elif direction == 'bearish' and score <= BEARISH_THRESHOLD:
                success = portfolio.sell_stock(ticker, price, str(date), score)
                if success:
                    print(f"📉 {date}: SELL {ticker} @ ${price:.2f} (Score: {score})")
        
        # Record portfolio value
        portfolio_value = portfolio.get_portfolio_value(prices)
        portfolio.portfolio_history.append({
            'date': date,
            'value': portfolio_value,
            'cash': portfolio.cash
        })
    
    return portfolio

def analyze_performance(portfolio: Portfolio, spy_data: pd.DataFrame) -> Dict[str, Any]:
    """Analyze portfolio performance and generate metrics."""
    print("\n" + "=" * 60)
    print("📊 ANALYZING PERFORMANCE")
    print("=" * 60)
    
    if not portfolio.portfolio_history:
        print("⚠️ No portfolio history to analyze")
        return {}
    
    # Portfolio metrics
    initial_value = INITIAL_CAPITAL
    final_value = portfolio.portfolio_history[-1]['value']
    total_return = (final_value - initial_value) / initial_value * 100
    
    # Trade analysis
    trades = portfolio.trades
    buy_trades = [t for t in trades if t['action'] == 'BUY']
    sell_trades = [t for t in trades if t['action'] == 'SELL']
    
    # Win rate calculation (simplified)
    profitable_trades = 0
    total_closed_trades = 0
    ticker_performance = {}
    
    for sell_trade in sell_trades:
        ticker = sell_trade['ticker']
        sell_date = sell_trade['date']
        sell_price = sell_trade['price']
        
        # Find corresponding buy trade (most recent before sell)
        buy_trade = None
        for buy in reversed(buy_trades):
            if buy['ticker'] == ticker and buy['date'] <= sell_date:
                buy_trade = buy
                break
        
        if buy_trade:
            profit = (sell_price - buy_trade['price']) / buy_trade['price'] * 100
            if profit > 0:
                profitable_trades += 1
            total_closed_trades += 1
            
            if ticker not in ticker_performance:
                ticker_performance[ticker] = []
            ticker_performance[ticker].append(profit)
    
    win_rate = (profitable_trades / total_closed_trades * 100) if total_closed_trades > 0 else 0
    
    # SPY benchmark
    spy_return = 0
    if not spy_data.empty and len(portfolio.portfolio_history) > 0:
        start_date = portfolio.portfolio_history[0]['date']
        end_date = portfolio.portfolio_history[-1]['date']
        
        spy_start = spy_data[spy_data.index.date >= start_date].iloc[0]['Close'] if len(spy_data[spy_data.index.date >= start_date]) > 0 else None
        spy_end = spy_data[spy_data.index.date <= end_date].iloc[-1]['Close'] if len(spy_data[spy_data.index.date <= end_date]) > 0 else None
        
        if spy_start and spy_end:
            spy_return = (spy_end - spy_start) / spy_start * 100
    
    # Best and worst performing tickers
    avg_ticker_performance = {}
    for ticker, profits in ticker_performance.items():
        avg_ticker_performance[ticker] = np.mean(profits)
    
    best_ticker = max(avg_ticker_performance.items(), key=lambda x: x[1]) if avg_ticker_performance else ('N/A', 0)
    worst_ticker = min(avg_ticker_performance.items(), key=lambda x: x[1]) if avg_ticker_performance else ('N/A', 0)
    
    return {
        'total_return': total_return,
        'spy_return': spy_return,
        'win_rate': win_rate,
        'total_trades': len(trades),
        'buy_trades': len(buy_trades),
        'sell_trades': len(sell_trades),
        'initial_value': initial_value,
        'final_value': final_value,
        'best_ticker': best_ticker,
        'worst_ticker': worst_ticker,
        'portfolio_history': portfolio.portfolio_history,
        'trades': trades
    }

def print_report(analysis: Dict[str, Any]):
    """Print formatted performance report."""
    print("📋 BACKTEST RESULTS")
    print("=" * 60)
    
    # Performance summary
    print("💰 PERFORMANCE SUMMARY:")
    print(f"   💵 Initial Capital: ${analysis['initial_value']:,.2f}")
    print(f"   📈 Final Portfolio Value: ${analysis['final_value']:,.2f}")
    print(f"   📊 Total Return: {analysis['total_return']:+.2f}%")
    print(f"   🏆 SPY Benchmark: {analysis['spy_return']:+.2f}%")
    
    outperformance = analysis['total_return'] - analysis['spy_return']
    perf_emoji = "🟢" if outperformance > 0 else "🔴"
    print(f"   {perf_emoji} vs SPY: {outperformance:+.2f}% {'outperformance' if outperformance > 0 else 'underperformance'}")
    
    # Trading statistics
    print(f"\n📈 TRADING STATISTICS:")
    print(f"   🎯 Total Trades: {analysis['total_trades']}")
    print(f"   🟢 Buy Orders: {analysis['buy_trades']}")
    print(f"   🔴 Sell Orders: {analysis['sell_trades']}")
    print(f"   🏅 Win Rate: {analysis['win_rate']:.1f}%")
    
    # Best and worst performers
    best_ticker, best_perf = analysis['best_ticker']
    worst_ticker, worst_perf = analysis['worst_ticker']
    print(f"\n🏆 TICKER PERFORMANCE:")
    print(f"   🥇 Best: {best_ticker} ({best_perf:+.1f}% avg)")
    print(f"   🥉 Worst: {worst_ticker} ({worst_perf:+.1f}% avg)")
    
    # Portfolio value over time (summary)
    history = analysis['portfolio_history']
    if len(history) > 1:
        print(f"\n📊 PORTFOLIO TIMELINE:")
        print(f"   📅 Start Date: {history[0]['date']}")
        print(f"   📅 End Date: {history[-1]['date']}")
        print(f"   📈 Max Value: ${max(h['value'] for h in history):,.2f}")
        print(f"   📉 Min Value: ${min(h['value'] for h in history):,.2f}")

def main():
    """Main backtest execution function."""
    print("🧪 Stock Trading Strategy Backtester")
    print("=" * 60)
    
    # Load signals
    signals = load_signals()
    if not signals:
        print("❌ No signals available for backtesting")
        return
    
    # Load price data
    price_data = load_price_data(WATCHLIST, months=6)
    if not price_data:
        print("❌ No price data available")
        return
    
    # Load SPY benchmark
    spy_data = get_spy_data(months=6)
    
    # Run backtest
    portfolio = run_backtest(signals, price_data)
    
    # Analyze results
    analysis = analyze_performance(portfolio, spy_data)
    
    # Print report
    print_report(analysis)
    
    print("\n🎯 Backtest complete!")

if __name__ == "__main__":
    main()