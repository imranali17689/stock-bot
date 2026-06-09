#!/usr/bin/env python3
"""
Stock Trading System Scheduler
Runs the signal engine at 8:00 AM and trader at 8:30 AM Eastern time daily.
"""

import logging
import signal
import sys
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from dotenv import load_dotenv

# Import main functions from both modules
from signal_engine import main as run_signal_engine
from trader import main as run_trader

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)

def signal_engine_job():
    """
    Wrapper function for the signal engine job with logging.
    """
    job_start_time = datetime.now()
    logger.info("🚀 Starting Stock Signal Engine job...")
    logger.info(f"📅 Signal Engine started at: {job_start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    try:
        # Run the main signal engine function
        run_signal_engine()
        
        job_end_time = datetime.now()
        duration = job_end_time - job_start_time
        
        logger.info("✅ Stock Signal Engine job completed successfully!")
        logger.info(f"⏱️  Signal Engine finished at: {job_end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"⌚ Signal Engine duration: {duration.total_seconds():.1f} seconds")
        
    except Exception as e:
        job_end_time = datetime.now()
        duration = job_end_time - job_start_time
        
        logger.error("❌ Stock Signal Engine job failed!")
        logger.error(f"🐛 Signal Engine error: {str(e)}")
        logger.error(f"⏱️  Signal Engine failed at: {job_end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.error(f"⌚ Signal Engine duration before failure: {duration.total_seconds():.1f} seconds")
        
        # Re-raise the exception for APScheduler to handle
        raise

def trader_job():
    """
    Wrapper function for the trader job with logging.
    """
    job_start_time = datetime.now()
    logger.info("💰 Starting Stock Trader job...")
    logger.info(f"📅 Trader started at: {job_start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    try:
        # Run the main trader function
        run_trader()
        
        job_end_time = datetime.now()
        duration = job_end_time - job_start_time
        
        logger.info("✅ Stock Trader job completed successfully!")
        logger.info(f"⏱️  Trader finished at: {job_end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"⌚ Trader duration: {duration.total_seconds():.1f} seconds")
        
    except Exception as e:
        job_end_time = datetime.now()
        duration = job_end_time - job_start_time
        
        logger.error("❌ Stock Trader job failed!")
        logger.error(f"🐛 Trader error: {str(e)}")
        logger.error(f"⏱️  Trader failed at: {job_end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.error(f"⌚ Trader duration before failure: {duration.total_seconds():.1f} seconds")
        
        # Re-raise the exception for APScheduler to handle
        raise

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    logger.info("🛑 Received shutdown signal, stopping scheduler...")
    sys.exit(0)

def main():
    """
    Main function to set up and run the scheduler.
    """
    logger.info("🤖 Stock Trading System Scheduler Starting...")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create scheduler with Eastern timezone
    eastern = timezone('US/Eastern')
    scheduler = BlockingScheduler(timezone=eastern)
    
    # Job 1: Signal Engine at 8:00 AM Eastern daily
    scheduler.add_job(
        func=signal_engine_job,
        trigger=CronTrigger(hour=8, minute=0, timezone=eastern),
        id='daily_signal_engine',
        name='Daily Stock Signal Analysis',
        max_instances=1,  # Prevent overlapping jobs
        misfire_grace_time=300,  # Allow 5 minutes grace period for missed jobs
        replace_existing=True
    )
    
    # Job 2: Trader at 8:30 AM Eastern daily (30 minutes after signal engine)
    scheduler.add_job(
        func=trader_job,
        trigger=CronTrigger(hour=8, minute=30, timezone=eastern),
        id='daily_trader',
        name='Daily Stock Trading Execution',
        max_instances=1,  # Prevent overlapping jobs
        misfire_grace_time=300,  # Allow 5 minutes grace period for missed jobs
        replace_existing=True
    )
    
    logger.info("📅 Scheduled daily jobs:")
    logger.info("   🔍 Signal Engine: 8:00 AM Eastern Time")
    logger.info("   💰 Trader: 8:30 AM Eastern Time")
    logger.info("   ⏱️  30-minute delay ensures signal analysis completes first")
    
    # Handle command line options for testing
    if len(sys.argv) > 1:
        if sys.argv[1] == '--run-signals':
            logger.info("🧪 Running signal engine immediately for testing...")
            signal_engine_job()
            logger.info("🧪 Signal engine test completed, exiting...")
            return
        elif sys.argv[1] == '--run-trader':
            logger.info("🧪 Running trader immediately for testing...")
            trader_job()
            logger.info("🧪 Trader test completed, exiting...")
            return
        elif sys.argv[1] == '--run-both':
            logger.info("🧪 Running both jobs immediately for testing...")
            signal_engine_job()
            logger.info("🧪 Signal engine completed, starting trader...")
            trader_job()
            logger.info("🧪 Both jobs completed, exiting...")
            return
        elif sys.argv[1] == '--run-now':
            # Backward compatibility
            logger.info("🧪 Running signal engine immediately for testing...")
            signal_engine_job()
            logger.info("🧪 Test run completed, exiting...")
            return
    
    try:
        # Start the scheduler (this will block)
        logger.info("🔄 Scheduler started. Press Ctrl+C to stop.")
        logger.info("📋 Available test commands:")
        logger.info("   --run-signals: Test signal engine only")
        logger.info("   --run-trader: Test trader only") 
        logger.info("   --run-both: Test both jobs in sequence")
        scheduler.start()
    except KeyboardInterrupt:
        logger.info("🛑 Scheduler stopped by user")
    except Exception as e:
        logger.error(f"❌ Scheduler error: {e}")
        raise
    finally:
        logger.info("👋 Scheduler shutdown complete")

if __name__ == "__main__":
    main()