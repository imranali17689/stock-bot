#!/usr/bin/env python3
"""
Stock Trader
Executes trades based on sentiment signals using Alpaca Paper Trading API.
"""

import os
import json
import requests
from datetime import datetime, date
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from supabase import create_client, Client

# Load environment variables
load_dotenv()

# Configuration
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_SECRET_KEY = os.getenv('SUPABASE_SECRET_KEY')

# Trading configuration
MAX_POSITION_SIZE = 1000.0  # Maximum $1000 per position
BULLISH_THRESHOLD = 7       # Buy signals for sentiment_score >= 7
BEARISH_THRESHOLD = 4       # Sell signals for sentiment_score <= 4

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

def get_account() -> Optional[Dict[str, Any]]:
    """
    Fetch and print account information from Alpaca.
    
    Returns:
        Dict: Account information or None if error
    """
    try:
        url = f"{ALPACA_BASE_URL}/v2/account"
        headers = get_alpaca_headers()
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        account_data = response.json()
        
        # Print formatted account info
        buying_power = float(account_data.get('buying_power', 0))
        portfolio_value = float(account_data.get('portfolio_value', 0))
        equity = float(account_data.get('equity', 0))
        cash = float(account_data.get('cash', 0))
        
        print("💰 Account Information:")
        print(f"   💵 Cash: ${cash:,.2f}")
        print(f"   📊 Portfolio Value: ${portfolio_value:,.2f}")
        print(f"   💎 Equity: ${equity:,.2f}")
        print(f"   🛒 Buying Power: ${buying_power:,.2f}")
        print(f"   📈 Day P&L: ${float(account_data.get('unrealized_pl', 0)):,.2f}")
        
        return account_data
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching account info: {e}")
        return None
    except Exception as e:
        print(f"✗ Unexpected error fetching account: {e}")
        return None

def place_order(ticker: str, side: str, dollars: float) -> Optional[Dict[str, Any]]:
    """
    Place a market order for a given dollar amount using fractional shares.
    
    Args:
        ticker (str): Stock ticker symbol
        side (str): 'buy' or 'sell'
        dollars (float): Dollar amount to trade
        
    Returns:
        Dict: Order response or None if error
    """
    try:
        url = f"{ALPACA_BASE_URL}/v2/orders"
        headers = get_alpaca_headers()
        
        # Prepare order data for fractional shares by notional value
        order_data = {
            'symbol': ticker,
            'side': side,
            'type': 'market',
            'time_in_force': 'day',
            'notional': dollars  # Use notional for dollar-based orders
        }
        
        response = requests.post(url, headers=headers, json=order_data, timeout=10)
        response.raise_for_status()
        
        order_response = response.json()
        
        print(f"✅ Order placed: {side.upper()} ${dollars} of {ticker}")
        print(f"   📝 Order ID: {order_response.get('id')}")
        print(f"   ⏰ Status: {order_response.get('status')}")
        
        return order_response
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error placing {side} order for {ticker}: {e}")
        if hasattr(e, 'response') and e.response:
            try:
                error_detail = e.response.json()
                print(f"   Error details: {error_detail}")
            except:
                pass
        return None
    except Exception as e:
        print(f"✗ Unexpected error placing order for {ticker}: {e}")
        return None

def get_positions() -> List[Dict[str, Any]]:
    """
    Get all current open positions.
    
    Returns:
        List[Dict]: List of position data
    """
    try:
        url = f"{ALPACA_BASE_URL}/v2/positions"
        headers = get_alpaca_headers()
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        positions = response.json()
        
        if positions:
            print("📊 Current Positions:")
            for position in positions:
                symbol = position['symbol']
                qty = float(position['qty'])
                market_value = float(position['market_value'])
                unrealized_pl = float(position['unrealized_pl'])
                unrealized_plpc = float(position['unrealized_plpc']) * 100
                
                pl_emoji = "🟢" if unrealized_pl >= 0 else "🔴"
                print(f"   {pl_emoji} {symbol}: {qty:.4f} shares | ${market_value:,.2f} | P&L: ${unrealized_pl:,.2f} ({unrealized_plpc:+.2f}%)")
        else:
            print("📊 No open positions")
        
        return positions
        
    except requests.exceptions.RequestException as e:
        print(f"✗ Error fetching positions: {e}")
        return []
    except Exception as e:
        print(f"✗ Unexpected error fetching positions: {e}")
        return []

def log_trade_entry(ticker: str, order_response: Dict[str, Any], notional_value: float, 
                   sentiment_score: int, direction: str) -> bool:
    """
    Log trade entry to Supabase trades table.
    
    Args:
        ticker (str): Stock symbol
        order_response (Dict): Alpaca order response
        notional_value (float): Dollar amount invested
        sentiment_score (int): Sentiment score from signal
        direction (str): Signal direction (bullish/bearish)
        
    Returns:
        bool: True if logged successfully, False otherwise
    """
    try:
        trade_data = {
            'ticker': ticker,
            'entry_time': datetime.now().isoformat(),
            'notional_value': notional_value,
            'sentiment_score': sentiment_score,
            'direction': direction,
            'shares': float(order_response.get('filled_qty', 0)) if order_response.get('filled_qty') else 0.0
        }
        
        result = supabase.table('trades').insert(trade_data).execute()
        
        if result.data:
            print(f"📝 Trade entry logged for {ticker}")
            return True
        else:
            print(f"⚠️ Failed to log trade entry for {ticker}")
            return False
            
    except Exception as e:
        print(f"⚠️ Error logging trade entry for {ticker}: {e}")
        return False

def get_todays_signals() -> List[Dict[str, Any]]:
    """
    Fetch today's most recent signals from Supabase (one per ticker).
    
    Returns:
        List[Dict]: List of today's most recent signals per ticker
    """
    try:
        today = date.today().isoformat()
        
        # Use raw SQL query with DISTINCT ON to get most recent signal per ticker
        # This ensures we only get the latest signal for each ticker from today
        query = """
        SELECT DISTINCT ON (ticker) *
        FROM signals 
        WHERE created_at >= %s
        ORDER BY ticker, created_at DESC
        """
        
        result = supabase.rpc('execute_sql', {
            'query': query,
            'params': [today]
        }).execute()
        
        # Alternative approach using Supabase client if RPC doesn't work
        if not result.data:
            # Fallback: get all today's signals and filter in Python
            all_signals = supabase.table('signals').select('*').gte('created_at', today).order('created_at', desc=True).execute()
            
            if all_signals.data:
                # Group by ticker and keep only the most recent
                ticker_signals = {}
                for signal in all_signals.data:
                    ticker = signal['ticker']
                    if ticker not in ticker_signals:
                        ticker_signals[ticker] = signal
                
                result.data = list(ticker_signals.values())
        
        if result.data:
            print(f"📡 Found {len(result.data)} unique ticker signals from today")
            # Print which tickers we got signals for
            tickers = [signal['ticker'] for signal in result.data]
            print(f"   📊 Tickers: {', '.join(sorted(tickers))}")
            return result.data
        else:
            print("📡 No signals found for today")
            return []
            
    except Exception as e:
        print(f"✗ Error fetching signals from database: {e}")
        # Fallback to original method if advanced query fails
        try:
            today = date.today().isoformat()
            all_signals = supabase.table('signals').select('*').gte('created_at', today).order('created_at', desc=True).execute()
            
            if all_signals.data:
                # Group by ticker and keep only the most recent
                ticker_signals = {}
                for signal in all_signals.data:
                    ticker = signal['ticker']
                    if ticker not in ticker_signals:
                        ticker_signals[ticker] = signal
                
                result_data = list(ticker_signals.values())
                print(f"📡 Found {len(result_data)} unique ticker signals from today (fallback method)")
                return result_data
            return []
        except Exception as fallback_error:
            print(f"✗ Fallback query also failed: {fallback_error}")
            return []

def execute_signals(signals: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Execute trades based on sentiment signals.
    
    Args:
        signals (List[Dict]): List of signal dictionaries
        
    Returns:
        Dict: Trade execution summary
    """
    print("🤖 Executing Trading Signals...")
    print("=" * 60)
    
    trade_summary = {
        'total_signals': len(signals),
        'buy_orders': 0,
        'sell_orders': 0,
        'skipped': 0,
        'errors': 0,
        'total_buy_amount': 0.0,
        'total_sell_amount': 0.0
    }
    
    # Get current positions to check what we own
    current_positions = get_positions()
    position_symbols = {pos['symbol']: float(pos['market_value']) for pos in current_positions}
    
    print(f"\n🎯 Processing {len(signals)} signals...")
    
    for signal in signals:
        ticker = signal['ticker']
        sentiment_score = signal['sentiment_score']
        direction = signal['direction']
        confidence = signal['confidence']
        
        print(f"\n📊 {ticker} | Score: {sentiment_score}/10 | {direction.upper()} | {confidence}")
        
        try:
            # Determine action based on sentiment
            if direction == 'bullish' and sentiment_score >= BULLISH_THRESHOLD:
                # Buy signal
                if ticker in position_symbols:
                    print(f"   ⚠️  Already hold {ticker} (${position_symbols[ticker]:,.2f}), skipping buy")
                    trade_summary['skipped'] += 1
                else:
                    print(f"   🟢 BUY signal triggered")
                    order = place_order(ticker, 'buy', MAX_POSITION_SIZE)
                    if order:
                        trade_summary['buy_orders'] += 1
                        trade_summary['total_buy_amount'] += MAX_POSITION_SIZE
                        # Log trade entry
                        log_trade_entry(ticker, order, MAX_POSITION_SIZE, sentiment_score, direction)
                    else:
                        trade_summary['errors'] += 1
                        
            elif direction == 'bearish' and sentiment_score <= BEARISH_THRESHOLD:
                # Sell signal
                if ticker in position_symbols:
                    current_value = position_symbols[ticker]
                    print(f"   🔴 SELL signal triggered for existing position")
                    order = place_order(ticker, 'sell', current_value)
                    if order:
                        trade_summary['sell_orders'] += 1
                        trade_summary['total_sell_amount'] += current_value
                    else:
                        trade_summary['errors'] += 1
                else:
                    print(f"   ⚠️  No position in {ticker} to sell, skipping")
                    trade_summary['skipped'] += 1
                    
            else:
                # No action
                action_reason = "neutral sentiment" if direction == 'neutral' else f"score {sentiment_score} below threshold"
                print(f"   ⭕ No action: {action_reason}")
                trade_summary['skipped'] += 1
                
        except Exception as e:
            print(f"   ✗ Error processing {ticker}: {e}")
            trade_summary['errors'] += 1
    
    return trade_summary

def print_trade_summary(summary: Dict[str, Any]) -> None:
    """Print formatted trade execution summary."""
    print("\n" + "=" * 60)
    print("📋 TRADE EXECUTION SUMMARY")
    print("=" * 60)
    print(f"📊 Total Signals Processed: {summary['total_signals']}")
    print(f"🟢 Buy Orders Placed: {summary['buy_orders']}")
    print(f"🔴 Sell Orders Placed: {summary['sell_orders']}")
    print(f"⭕ Signals Skipped: {summary['skipped']}")
    print(f"❌ Errors: {summary['errors']}")
    
    if summary['total_buy_amount'] > 0:
        print(f"💰 Total Buy Amount: ${summary['total_buy_amount']:,.2f}")
    if summary['total_sell_amount'] > 0:
        print(f"💸 Total Sell Amount: ${summary['total_sell_amount']:,.2f}")
    
    net_flow = summary['total_buy_amount'] - summary['total_sell_amount']
    if net_flow != 0:
        flow_direction = "Net Investment" if net_flow > 0 else "Net Divestment"
        print(f"📈 {flow_direction}: ${abs(net_flow):,.2f}")

def main():
    """
    Main function to fetch signals and execute trades.
    """
    print("🤖 Stock Trader Starting...")
    print(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)
    
    # Check account status
    account = get_account()
    if not account:
        print("❌ Cannot access trading account, aborting")
        return
    
    print("\n" + "=" * 60)
    
    # Get today's signals
    signals = get_todays_signals()
    
    if not signals:
        print("⚠️  No signals available for trading")
        return
    
    print("\n" + "=" * 60)
    
    # Execute trades based on signals
    trade_summary = execute_signals(signals)
    
    # Print summary
    print_trade_summary(trade_summary)
    
    # Show final positions
    print("\n" + "=" * 60)
    get_positions()
    
    print("\n🎯 Trading session complete!")

if __name__ == "__main__":
    main()