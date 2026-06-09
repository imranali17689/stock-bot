#!/usr/bin/env python3
"""
Performance Tracker
Monitors live trading performance from Alpaca and compares to SPY benchmark.
"""

import os
import json
import requests
import yfinance as yf
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from supabase import create_client, Client
import pandas as pd

# Load environment variables
load_dotenv()

# Configuration
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SECRET_KEY = os.getenv('SUPABASE_SECRET_KEY')

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

def get_alpaca_headers() -> Dict[str, str]:
    """Get headers for Alpaca API requests."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        raise ValueError("Alpaca API credentials not found in environment variables")
    
    return {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY,
        'Content-Type': 'application/json'
    }

def get_account_info() -> Optional[Dict[str, Any]]:
    """Fetch account information from Alpaca."""
    try:
        url = f"{ALPACA_BASE_URL}/v2/account"
        headers = get_alpaca_headers()
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        return response.json()
        
    except Exception as e:
        print(f"✗ Error fetching account info: {e}")
        return None

def get_positions() -> List[Dict[str, Any]]:
    """Fetch current positions from Alpaca."""
    try:
        url = f"{ALPACA_BASE_URL}/v2/positions"
        headers = get_alpaca_headers()
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        return response.json()
        
    except Exception as e:
        print(f"✗ Error fetching positions: {e}")
        return []

def get_orders(status: str = None, limit: int = 100) -> List[Dict[str, Any]]:
    """Fetch orders from Alpaca."""
    try:
        url = f"{ALPACA_BASE_URL}/v2/orders"
        headers = get_alpaca_headers()
        
        params = {'limit': limit}
        if status:
            params['status'] = status
            
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        return response.json()
        
    except Exception as e:
        print(f"✗ Error fetching orders: {e}")
        return []

def get_portfolio_history(period: str = "1M") -> Optional[Dict[str, Any]]:
    """Fetch portfolio history from Alpaca."""
    try:
        url = f"{ALPACA_BASE_URL}/v2/account/portfolio/history"
        headers = get_alpaca_headers()
        
        params = {'period': period, 'timeframe': '1D'}
        
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        
        return response.json()
        
    except Exception as e:
        print(f"✗ Error fetching portfolio history: {e}")
        return None

def get_spy_data(start_date: datetime, end_date: datetime = None) -> Optional[pd.DataFrame]:
    """Fetch SPY data for benchmark comparison."""
    try:
        if end_date is None:
            end_date = datetime.now()
            
        spy = yf.Ticker('SPY')
        data = spy.history(start=start_date, end=end_date)
        return data
        
    except Exception as e:
        print(f"✗ Error fetching SPY data: {e}")
        return None

def calculate_position_metrics(positions: List[Dict], orders: List[Dict]) -> List[Dict]:
    """Calculate detailed metrics for each position."""
    position_metrics = []
    
    for position in positions:
        symbol = position['symbol']
        qty = float(position['qty'])
        market_value = float(position['market_value'])
        cost_basis = float(position['cost_basis'])
        unrealized_pl = float(position['unrealized_pl'])
        unrealized_plpc = float(position['unrealized_plpc']) * 100
        
        # Find entry date from orders
        entry_date = None
        entry_price = None
        
        for order in orders:
            if (order['symbol'] == symbol and 
                order['side'] == 'buy' and 
                order['status'] == 'filled'):
                entry_date = datetime.fromisoformat(order['filled_at'].replace('Z', '+00:00'))
                entry_price = float(order['filled_avg_price']) if order['filled_avg_price'] else None
                break
        
        # Calculate days held
        days_held = 0
        if entry_date:
            days_held = (datetime.now(entry_date.tzinfo) - entry_date).days
        
        position_metrics.append({
            'symbol': symbol,
            'quantity': qty,
            'market_value': market_value,
            'cost_basis': cost_basis,
            'unrealized_pl': unrealized_pl,
            'unrealized_plpc': unrealized_plpc,
            'entry_date': entry_date.strftime('%Y-%m-%d') if entry_date else 'Unknown',
            'entry_price': entry_price,
            'days_held': days_held,
            'current_price': market_value / qty if qty != 0 else 0
        })
    
    return position_metrics

def calculate_portfolio_performance(account_info: Dict, portfolio_history: Dict) -> Dict[str, Any]:
    """Calculate overall portfolio performance metrics."""
    portfolio_value = float(account_info['portfolio_value'])
    equity = float(account_info['equity'])
    
    # Get historical data from portfolio history
    if portfolio_history and portfolio_history.get('equity'):
        equity_history = portfolio_history['equity']
        timestamps = portfolio_history['timestamp']
        
        if equity_history and len(equity_history) > 0:
            initial_value = equity_history[0]
            current_value = equity_history[-1]
            
            total_return_pct = ((current_value - initial_value) / initial_value * 100) if initial_value > 0 else 0
            
            # Calculate start date
            start_timestamp = timestamps[0] if timestamps else None
            start_date = datetime.fromtimestamp(start_timestamp) if start_timestamp else datetime.now() - timedelta(days=30)
            
        else:
            total_return_pct = 0
            start_date = datetime.now() - timedelta(days=30)
    else:
        total_return_pct = 0
        start_date = datetime.now() - timedelta(days=30)
    
    return {
        'portfolio_value': portfolio_value,
        'equity': equity,
        'total_return_pct': total_return_pct,
        'start_date': start_date
    }

def compare_to_spy(portfolio_performance: Dict) -> Dict[str, Any]:
    """Compare portfolio performance to SPY benchmark."""
    start_date = portfolio_performance['start_date']
    
    # Get SPY data
    spy_data = get_spy_data(start_date)
    
    if spy_data is not None and len(spy_data) > 0:
        spy_start = spy_data.iloc[0]['Close']
        spy_current = spy_data.iloc[-1]['Close']
        spy_return_pct = ((spy_current - spy_start) / spy_start * 100)
        
        outperformance = portfolio_performance['total_return_pct'] - spy_return_pct
        
        return {
            'spy_start_price': spy_start,
            'spy_current_price': spy_current,
            'spy_return_pct': spy_return_pct,
            'outperformance': outperformance
        }
    else:
        return {
            'spy_start_price': 0,
            'spy_current_price': 0,
            'spy_return_pct': 0,
            'outperformance': 0
        }

def save_performance_snapshot(portfolio_performance: Dict, spy_performance: Dict, positions_count: int) -> bool:
    """Save daily performance snapshot to Supabase."""
    try:
        snapshot_data = {
            'snapshot_date': date.today().isoformat(),
            'portfolio_value': portfolio_performance['portfolio_value'],
            'spy_value': spy_performance['spy_current_price'],
            'total_return_pct': portfolio_performance['total_return_pct'],
            'positions_count': positions_count
        }
        
        # Check if snapshot for today already exists
        existing = supabase.table('performance_snapshots').select('*').eq('snapshot_date', snapshot_data['snapshot_date']).execute()
        
        if existing.data:
            # Update existing snapshot
            result = supabase.table('performance_snapshots').update(snapshot_data).eq('snapshot_date', snapshot_data['snapshot_date']).execute()
            print("📊 Updated today's performance snapshot")
        else:
            # Insert new snapshot
            result = supabase.table('performance_snapshots').insert(snapshot_data).execute()
            print("📊 Saved new performance snapshot")
        
        return True
        
    except Exception as e:
        print(f"✗ Error saving performance snapshot: {e}")
        return False

def print_performance_report(account_info: Dict, position_metrics: List[Dict], 
                           portfolio_performance: Dict, spy_performance: Dict):
    """Print a comprehensive performance report."""
    print("📊 LIVE TRADING PERFORMANCE REPORT")
    print("=" * 70)
    
    # Account summary
    print("💰 ACCOUNT SUMMARY:")
    print(f"   💵 Cash: ${float(account_info['cash']):,.2f}")
    print(f"   📈 Portfolio Value: ${portfolio_performance['portfolio_value']:,.2f}")
    print(f"   💎 Equity: ${portfolio_performance['equity']:,.2f}")
    print(f"   📊 Day P&L: ${float(account_info.get('unrealized_pl', 0)):,.2f}")
    
    # Performance vs benchmark
    print(f"\n🏆 PERFORMANCE COMPARISON:")
    print(f"   📈 Portfolio Return: {portfolio_performance['total_return_pct']:+.2f}%")
    print(f"   📊 SPY Benchmark: {spy_performance['spy_return_pct']:+.2f}%")
    
    outperformance = spy_performance['outperformance']
    perf_emoji = "🟢" if outperformance > 0 else "🔴"
    perf_text = "outperformance" if outperformance > 0 else "underperformance"
    print(f"   {perf_emoji} vs SPY: {outperformance:+.2f}% {perf_text}")
    
    # Current positions
    if position_metrics:
        print(f"\n📊 CURRENT POSITIONS ({len(position_metrics)}):")
        
        total_unrealized_pl = sum(pos['unrealized_pl'] for pos in position_metrics)
        total_market_value = sum(pos['market_value'] for pos in position_metrics)
        
        for pos in position_metrics:
            pl_emoji = "🟢" if pos['unrealized_pl'] >= 0 else "🔴"
            print(f"   {pl_emoji} {pos['symbol']}: {pos['quantity']:.4f} shares")
            print(f"      💰 Value: ${pos['market_value']:,.2f} | P&L: ${pos['unrealized_pl']:+,.2f} ({pos['unrealized_plpc']:+.1f}%)")
            
            # Format prices with None checks
            entry_price_str = f"${pos['entry_price']:.2f}" if pos['entry_price'] is not None else "N/A"
            current_price_str = f"${pos['current_price']:.2f}" if pos['current_price'] is not None else "N/A"
            print(f"      📅 Held: {pos['days_held']} days | Entry: {entry_price_str} → Current: {current_price_str}")
        
        print(f"\n   📊 Total Positions P&L: ${total_unrealized_pl:+,.2f}")
        print(f"   💰 Total Positions Value: ${total_market_value:,.2f}")
        
        # Best and worst performers
        if len(position_metrics) > 1:
            best_pos = max(position_metrics, key=lambda x: x['unrealized_plpc'])
            worst_pos = min(position_metrics, key=lambda x: x['unrealized_plpc'])
            print(f"\n   🏆 Best Performer: {best_pos['symbol']} ({best_pos['unrealized_plpc']:+.1f}%)")
            print(f"   📉 Worst Performer: {worst_pos['symbol']} ({worst_pos['unrealized_plpc']:+.1f}%)")
    else:
        print(f"\n📊 CURRENT POSITIONS: None")
    
    # Summary statistics
    print(f"\n📈 SUMMARY:")
    print(f"   📅 Tracking Period: {(datetime.now() - portfolio_performance['start_date']).days} days")
    print(f"   🎯 Active Positions: {len(position_metrics)}")
    
    if position_metrics:
        avg_return = sum(pos['unrealized_plpc'] for pos in position_metrics) / len(position_metrics)
        winning_positions = len([pos for pos in position_metrics if pos['unrealized_pl'] > 0])
        win_rate = (winning_positions / len(position_metrics)) * 100
        print(f"   📊 Average Position Return: {avg_return:+.1f}%")
        print(f"   🏅 Winning Positions: {winning_positions}/{len(position_metrics)} ({win_rate:.1f}%)")

def main():
    """Main performance tracking function."""
    print("📊 Performance Tracker Starting...")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    # Fetch account data
    print("📡 Fetching account data from Alpaca...")
    account_info = get_account_info()
    if not account_info:
        print("❌ Cannot fetch account information")
        return
    
    positions = get_positions()
    orders = get_orders(limit=200)
    portfolio_history = get_portfolio_history()
    
    print(f"✓ Account info, {len(positions)} positions, {len(orders)} orders loaded")
    
    # Calculate metrics
    print("🧮 Calculating performance metrics...")
    position_metrics = calculate_position_metrics(positions, orders)
    portfolio_performance = calculate_portfolio_performance(account_info, portfolio_history)
    spy_performance = compare_to_spy(portfolio_performance)
    
    # Save snapshot
    print("💾 Saving performance snapshot...")
    save_performance_snapshot(portfolio_performance, spy_performance, len(positions))
    
    # Print report
    print_performance_report(account_info, position_metrics, portfolio_performance, spy_performance)
    
    print("\n🎯 Performance tracking complete!")

if __name__ == "__main__":
    main()