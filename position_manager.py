#!/usr/bin/env python3
"""
Position Manager
Manages trading positions with stop loss and take profit rules.
"""

import os
import requests
import logging
import sys
from datetime import datetime
from typing import List, Dict, Any
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

# Initialize Supabase client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

# Risk management constants
STOP_LOSS_PCT = 0.05      # 5% stop loss threshold (positive value, used as -STOP_LOSS_PCT in comparisons)
TAKE_PROFIT_PCT = 0.04    # 4% take profit (reduced from 10% for more frequent intraday exits)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('position_manager.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def get_alpaca_headers() -> Dict[str, str]:
    """Get headers for Alpaca API requests."""
    if not ALPACA_API_KEY or not ALPACA_SECRET_KEY:
        raise ValueError("Alpaca API credentials not found in environment variables")
    
    return {
        'APCA-API-KEY-ID': ALPACA_API_KEY,
        'APCA-API-SECRET-KEY': ALPACA_SECRET_KEY,
        'Content-Type': 'application/json'
    }

def log_trade_exit(ticker: str, exit_price: float, exit_reason: str, pnl_dollars: float, 
                  pnl_pct: float, shares: float, notional_value: float) -> bool:
    """
    Log trade exit to Supabase trades table by updating the most recent open trade.
    
    Args:
        ticker (str): Stock symbol
        exit_price (float): Price at exit
        exit_reason (str): Reason for exit ('stop_loss', 'take_profit', 'eod_close', 'manual')
        pnl_dollars (float): P&L in dollars
        pnl_pct (float): P&L percentage
        shares (float): Number of shares
        notional_value (float): Exit value in dollars
        
    Returns:
        bool: True if logged successfully, False otherwise
    """
    try:
        # Find the most recent open trade for this ticker
        result = supabase.table('trades').select('*').eq('ticker', ticker).is_('exit_time', 'null').order('entry_time', desc=True).limit(1).execute()
        
        if result.data and len(result.data) > 0:
            trade_id = result.data[0]['id']
            
            exit_data = {
                'exit_price': exit_price,
                'exit_time': datetime.now().isoformat(),
                'pnl_dollars': pnl_dollars,
                'pnl_pct': pnl_pct,
                'exit_reason': exit_reason
            }
            
            update_result = supabase.table('trades').update(exit_data).eq('id', trade_id).execute()
            
            if update_result.data:
                logger.info(f"📝 Trade exit logged for {ticker} (Reason: {exit_reason})")
                return True
            else:
                logger.warning(f"⚠️ Failed to update trade exit for {ticker}")
                return False
        else:
            logger.warning(f"⚠️ No open trade found for {ticker} to update")
            return False
            
    except Exception as e:
        logger.warning(f"⚠️ Error logging trade exit for {ticker}: {e}")
        return False

def get_open_positions() -> List[Dict[str, Any]]:
    """
    Get all open positions from Alpaca.
    
    Returns:
        List[Dict]: List of position data or empty list on error
    """
    try:
        url = f"{ALPACA_BASE_URL}/v2/positions"
        headers = get_alpaca_headers()
        
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        positions = response.json()
        logger.info(f"📊 Found {len(positions)} open positions")
        
        return positions
        
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Error fetching positions: {e}")
        return []
    except Exception as e:
        logger.error(f"✗ Unexpected error fetching positions: {e}")
        return []

def close_position(symbol: str, exit_reason: str = 'manual') -> bool:
    """
    Close a specific position by symbol.
    
    Args:
        symbol (str): Stock ticker symbol to close
        exit_reason (str): Reason for closing ('stop_loss', 'take_profit', 'eod_close', 'manual')
        
    Returns:
        bool: True if successful, False on error
    """
    try:
        # Get position data before closing for logging
        positions = get_open_positions()
        position_data = None
        for pos in positions:
            if pos['symbol'] == symbol:
                position_data = pos
                break
        
        url = f"{ALPACA_BASE_URL}/v2/positions/{symbol}"
        headers = get_alpaca_headers()
        
        response = requests.delete(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        logger.info(f"✅ Successfully closed position for {symbol}")
        
        # Log trade exit if we have position data
        if position_data:
            try:
                current_price = float(position_data['market_value']) / float(position_data['qty']) if float(position_data['qty']) != 0 else 0
                unrealized_pl = float(position_data['unrealized_pl'])
                unrealized_plpc = float(position_data['unrealized_plpc']) * 100  # Convert to percentage
                qty = float(position_data['qty'])
                market_value = float(position_data['market_value'])
                
                log_trade_exit(symbol, current_price, exit_reason, unrealized_pl, 
                             unrealized_plpc, qty, market_value)
            except Exception as log_error:
                logger.warning(f"⚠️ Failed to log trade exit for {symbol}: {log_error}")
        
        return True
        
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Error closing position for {symbol}: {e}")
        if hasattr(e, 'response') and e.response:
            try:
                error_detail = e.response.json()
                logger.error(f"   Error details: {error_detail}")
            except:
                pass
        return False
    except Exception as e:
        logger.error(f"✗ Unexpected error closing position for {symbol}: {e}")
        return False

def check_and_exit_positions() -> Dict[str, Any]:
    """
    Check all positions for stop loss or take profit conditions and exit as needed.
    
    Returns:
        Dict: Summary of actions taken
    """
    logger.info("🤖 Checking positions for exit conditions...")
    
    summary = {
        'checked': 0,
        'stop_loss_exits': 0,
        'take_profit_exits': 0,
        'errors': 0
    }
    
    positions = get_open_positions()
    if not positions:
        logger.info("📊 No positions to check")
        return summary
    
    summary['checked'] = len(positions)
    
    for position in positions:
        try:
            symbol = position['symbol']
            unrealized_plpc = float(position['unrealized_plpc'])  # This is already a decimal (e.g., -0.032 = -3.2%)
            pct_display = unrealized_plpc * 100  # Convert to percentage for display
            
            logger.info(f"📊 Checking {symbol}: {pct_display:+.2f}% P&L")
            
            # Check for stop loss condition
            if unrealized_plpc <= -STOP_LOSS_PCT:
                logger.warning(f"🔴 STOP LOSS triggered for {symbol} at {pct_display:.2f}%")
                if close_position(symbol, 'stop_loss'):
                    summary['stop_loss_exits'] += 1
                else:
                    summary['errors'] += 1
                    
            # Check for take profit condition
            elif unrealized_plpc >= TAKE_PROFIT_PCT:
                logger.info(f"🟢 TAKE PROFIT triggered for {symbol} at {pct_display:.2f}%")
                if close_position(symbol, 'take_profit'):
                    summary['take_profit_exits'] += 1
                else:
                    summary['errors'] += 1
            else:
                # Position is within normal range
                logger.info(f"   ⭕ {symbol} within normal range ({pct_display:+.2f}%)")
                
        except Exception as e:
            logger.error(f"✗ Error processing position {position.get('symbol', 'unknown')}: {e}")
            summary['errors'] += 1
    
    return summary

def log_performance_snapshot() -> bool:
    """
    Log a performance snapshot to Supabase after positions are closed.
    
    Returns:
        bool: True if logged successfully, False otherwise
    """
    try:
        # Get account information from Alpaca
        account_url = f"{ALPACA_BASE_URL}/v2/account"
        headers = get_alpaca_headers()
        
        account_response = requests.get(account_url, headers=headers, timeout=10)
        account_response.raise_for_status()
        account_data = account_response.json()
        
        portfolio_value = float(account_data['portfolio_value'])
        cash = float(account_data['cash'])
        
        # Get SPY current price from Alpaca market data API
        spy_url = "https://data.alpaca.markets/v2/stocks/SPY/trades/latest"
        spy_response = requests.get(spy_url, headers=headers, timeout=10)
        spy_response.raise_for_status()
        spy_data = spy_response.json()
        
        spy_price = float(spy_data['trade']['p'])  # 'p' is price in Alpaca trades response
        
        # Calculate total return percentage (assuming $100k starting balance)
        starting_balance = 100000.0
        total_return_pct = ((portfolio_value - starting_balance) / starting_balance) * 100
        
        # Count open positions
        positions = get_open_positions()
        positions_count = len(positions)
        
        # Prepare snapshot data
        snapshot_data = {
            'snapshot_date': datetime.now().date().isoformat(),
            'portfolio_value': portfolio_value,
            'spy_value': spy_price,
            'total_return_pct': total_return_pct,
            'positions_count': positions_count
        }
        
        # Insert into Supabase
        result = supabase.table('performance_snapshots').insert(snapshot_data).execute()
        
        if result.data:
            logger.info(f"📊 Performance snapshot logged: Portfolio: ${portfolio_value:,.2f}, SPY: ${spy_price:.2f}, Return: {total_return_pct:+.2f}%, Positions: {positions_count}")
            return True
        else:
            logger.error("✗ Failed to insert performance snapshot")
            return False
            
    except requests.exceptions.RequestException as e:
        logger.error(f"✗ Error fetching data for performance snapshot: {e}")
        return False
    except Exception as e:
        logger.error(f"✗ Error logging performance snapshot: {e}")
        return False

def close_all_positions() -> Dict[str, Any]:
    """
    Close all open positions. Used for end-of-day cleanup.
    
    Returns:
        Dict: Summary of actions taken
    """
    logger.info("🔄 Closing all open positions...")
    
    summary = {
        'total_positions': 0,
        'closed_successfully': 0,
        'errors': 0
    }
    
    positions = get_open_positions()
    if not positions:
        logger.info("📊 No positions to close")
        return summary
    
    summary['total_positions'] = len(positions)
    
    for position in positions:
        try:
            symbol = position['symbol']
            market_value = float(position['market_value'])
            unrealized_pl = float(position['unrealized_pl'])
            
            logger.info(f"🔄 Closing {symbol} (Value: ${market_value:,.2f}, P&L: ${unrealized_pl:+,.2f})")
            
            if close_position(symbol, 'eod_close'):
                summary['closed_successfully'] += 1
            else:
                summary['errors'] += 1
                
        except Exception as e:
            logger.error(f"✗ Error closing position {position.get('symbol', 'unknown')}: {e}")
            summary['errors'] += 1
    
    # Log performance snapshot after closing all positions
    logger.info("📊 Logging performance snapshot after position closure...")
    log_performance_snapshot()
    
    return summary

def main():
    """
    Main function to check and manage positions.
    """
    logger.info("🤖 Position Manager Starting...")
    logger.info(f"⏰ {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 60)
    
    # Check positions for exit conditions
    summary = check_and_exit_positions()
    
    # Print summary
    logger.info("=" * 60)
    logger.info("📋 POSITION MANAGEMENT SUMMARY")
    logger.info("=" * 60)
    logger.info(f"📊 Positions Checked: {summary['checked']}")
    logger.info(f"🔴 Stop Loss Exits: {summary['stop_loss_exits']}")
    logger.info(f"🟢 Take Profit Exits: {summary['take_profit_exits']}")
    logger.info(f"❌ Errors: {summary['errors']}")
    
    total_exits = summary['stop_loss_exits'] + summary['take_profit_exits']
    logger.info(f"🎯 Total Positions Closed: {total_exits}")
    
    if summary['errors'] > 0:
        logger.warning(f"⚠️  {summary['errors']} errors occurred during position management")
    
    logger.info("🎯 Position management complete!")

if __name__ == "__main__":
    main()