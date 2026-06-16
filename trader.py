#!/usr/bin/env python3
"""
Stock Trader
Executes trades based on sentiment signals using Alpaca Paper Trading API.
"""

import os
import json
import requests
from datetime import datetime, date, timedelta
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
                   sentiment_score: int, direction: str, rolling_avg_score: float = None) -> bool:
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
            'shares': float(order_response.get('filled_qty', 0)) if order_response.get('filled_qty') else 0.0,
            'rolling_avg_score': rolling_avg_score if rolling_avg_score is not None else sentiment_score
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

def get_rolling_sentiment_signals() -> List[Dict[str, Any]]:
    """
    Fetch signals with 3-day rolling averages for sentiment scores.
    
    Returns:
        List[Dict]: List of signals with rolling averages per ticker
    """
    try:
        # Calculate date range for last 3 days
        today = date.today()
        three_days_ago = today - timedelta(days=3)
        
        today_str = today.isoformat()
        three_days_ago_str = three_days_ago.isoformat()
        
        # Get all signals from last 3 days
        all_recent_signals = supabase.table('signals').select('*').gte('created_at', three_days_ago_str).order('created_at', desc=True).execute()
        
        if not all_recent_signals.data:
            print("📡 No signals found for the last 3 days")
            return []
        
        # Get today's most recent signals for direction and confidence
        todays_signals = supabase.table('signals').select('*').gte('created_at', today_str).order('created_at', desc=True).execute()
        
        if not todays_signals.data:
            print("📡 No signals found for today")
            return []
        
        # Group today's signals by ticker (keep most recent)
        todays_by_ticker = {}
        for signal in todays_signals.data:
            ticker = signal['ticker']
            if ticker not in todays_by_ticker:
                todays_by_ticker[ticker] = signal
        
        # Group all recent signals by ticker
        signals_by_ticker = {}
        for signal in all_recent_signals.data:
            ticker = signal['ticker']
            if ticker not in signals_by_ticker:
                signals_by_ticker[ticker] = []
            signals_by_ticker[ticker].append(signal)
        
        # Calculate rolling averages
        rolling_signals = []
        
        for ticker in todays_by_ticker:
            today_signal = todays_by_ticker[ticker]
            
            # Get last 3 days of signals for this ticker (limit to 3 most recent)
            recent_signals = signals_by_ticker.get(ticker, [])[:3]
            
            if recent_signals:
                # Calculate rolling average of sentiment scores
                sentiment_scores = [s['sentiment_score'] for s in recent_signals]
                rolling_avg_score = sum(sentiment_scores) / len(sentiment_scores)
                
                # Create enhanced signal with rolling average
                enhanced_signal = today_signal.copy()
                enhanced_signal['rolling_avg_score'] = rolling_avg_score
                enhanced_signal['days_in_average'] = len(sentiment_scores)
                
                rolling_signals.append(enhanced_signal)
                
                print(f"📊 {ticker}: Rolling avg {rolling_avg_score:.1f} (last {len(sentiment_scores)} days: {sentiment_scores})")
            else:
                # Fallback to today's signal only
                enhanced_signal = today_signal.copy()
                enhanced_signal['rolling_avg_score'] = today_signal['sentiment_score']
                enhanced_signal['days_in_average'] = 1
                rolling_signals.append(enhanced_signal)
                
                print(f"📊 {ticker}: No historical data, using today's score {today_signal['sentiment_score']}")
        
        print(f"📡 Calculated rolling averages for {len(rolling_signals)} tickers")
        return rolling_signals
        
    except Exception as e:
        print(f"✗ Error calculating rolling sentiment signals: {e}")
        # Fallback to today's signals only
        try:
            today = date.today().isoformat()
            fallback_signals = supabase.table('signals').select('*').gte('created_at', today).order('created_at', desc=True).execute()
            
            if fallback_signals.data:
                # Group by ticker and keep only the most recent, add rolling_avg_score = sentiment_score
                ticker_signals = {}
                for signal in fallback_signals.data:
                    ticker = signal['ticker']
                    if ticker not in ticker_signals:
                        enhanced_signal = signal.copy()
                        enhanced_signal['rolling_avg_score'] = signal['sentiment_score']
                        enhanced_signal['days_in_average'] = 1
                        ticker_signals[ticker] = enhanced_signal
                
                result_data = list(ticker_signals.values())
                print(f"📡 Fallback: Using {len(result_data)} today's signals without rolling average")
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
        sentiment_score = signal['sentiment_score']  # Today's score for display
        rolling_avg_score = signal.get('rolling_avg_score', sentiment_score)  # 3-day average for decisions
        direction = signal['direction']  # Today's direction for decisions
        confidence = signal['confidence']  # Today's confidence
        days_in_avg = signal.get('days_in_average', 1)
        
        print(f"\n📊 {ticker} | Today: {sentiment_score}/10 | 3-Day Avg: {rolling_avg_score:.1f}/10 | {direction.upper()} | {confidence}")
        print(f"   📈 Rolling average based on {days_in_avg} day(s)")
        
        try:
            # Determine action based on rolling average score and today's direction
            if direction == 'bullish' and rolling_avg_score >= BULLISH_THRESHOLD:
                # Buy signal
                if ticker in position_symbols:
                    print(f"   ⚠️  Already hold {ticker} (${position_symbols[ticker]:,.2f}), skipping buy")
                    trade_summary['skipped'] += 1
                else:
                    print(f"   🟢 BUY signal triggered (Rolling avg: {rolling_avg_score:.1f} >= {BULLISH_THRESHOLD})")
                    order = place_order(ticker, 'buy', MAX_POSITION_SIZE)
                    if order:
                        trade_summary['buy_orders'] += 1
                        trade_summary['total_buy_amount'] += MAX_POSITION_SIZE
                        # Log trade entry with rolling average
                        log_trade_entry(ticker, order, MAX_POSITION_SIZE, sentiment_score, direction, rolling_avg_score)
                    else:
                        trade_summary['errors'] += 1
                        
            elif direction == 'bearish' and rolling_avg_score <= BEARISH_THRESHOLD:
                # Sell signal
                if ticker in position_symbols:
                    current_value = position_symbols[ticker]
                    print(f"   🔴 SELL signal triggered for existing position (Rolling avg: {rolling_avg_score:.1f} <= {BEARISH_THRESHOLD})")
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
                if direction == 'neutral':
                    action_reason = "neutral sentiment"
                elif direction == 'bullish':
                    action_reason = f"rolling avg {rolling_avg_score:.1f} below buy threshold ({BULLISH_THRESHOLD})"
                else:  # bearish
                    action_reason = f"rolling avg {rolling_avg_score:.1f} above sell threshold ({BEARISH_THRESHOLD})"
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
    signals = get_rolling_sentiment_signals()
    
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