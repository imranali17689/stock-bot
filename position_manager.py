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

# Load environment variables
load_dotenv()

# Configuration
ALPACA_API_KEY = os.getenv('ALPACA_API_KEY')
ALPACA_SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')
ALPACA_BASE_URL = os.getenv('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets')

# Risk management constants
STOP_LOSS_PCT = 0.05      # 5% stop loss
TAKE_PROFIT_PCT = 0.10    # 10% take profit

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

def close_position(symbol: str) -> bool:
    """
    Close a specific position by symbol.
    
    Args:
        symbol (str): Stock ticker symbol to close
        
    Returns:
        bool: True if successful, False on error
    """
    try:
        url = f"{ALPACA_BASE_URL}/v2/positions/{symbol}"
        headers = get_alpaca_headers()
        
        response = requests.delete(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        logger.info(f"✅ Successfully closed position for {symbol}")
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
                if close_position(symbol):
                    summary['stop_loss_exits'] += 1
                else:
                    summary['errors'] += 1
                    
            # Check for take profit condition
            elif unrealized_plpc >= TAKE_PROFIT_PCT:
                logger.info(f"🟢 TAKE PROFIT triggered for {symbol} at {pct_display:.2f}%")
                if close_position(symbol):
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
            
            if close_position(symbol):
                summary['closed_successfully'] += 1
            else:
                summary['errors'] += 1
                
        except Exception as e:
            logger.error(f"✗ Error closing position {position.get('symbol', 'unknown')}: {e}")
            summary['errors'] += 1
    
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