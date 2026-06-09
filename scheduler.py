#!/usr/bin/env python3
"""
Stock Signal Engine Scheduler
Runs the signal engine daily at 8:00 AM Eastern time using APScheduler.
"""

import logging
import signal
import sys
from datetime import datetime
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from pytz import timezone
from dotenv import load_dotenv

# Import the main function from signal_engine
from signal_engine import main as run_signal_engine

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
    logger.info(f"📅 Job started at: {job_start_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    try:
        # Run the main signal engine function
        run_signal_engine()
        
        job_end_time = datetime.now()
        duration = job_end_time - job_start_time
        
        logger.info("✅ Stock Signal Engine job completed successfully!")
        logger.info(f"⏱️  Job finished at: {job_end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.info(f"⌚ Total duration: {duration.total_seconds():.1f} seconds")
        
    except Exception as e:
        job_end_time = datetime.now()
        duration = job_end_time - job_start_time
        
        logger.error("❌ Stock Signal Engine job failed!")
        logger.error(f"🐛 Error: {str(e)}")
        logger.error(f"⏱️  Job failed at: {job_end_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        logger.error(f"⌚ Duration before failure: {duration.total_seconds():.1f} seconds")
        
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
    logger.info("🤖 Stock Signal Engine Scheduler Starting...")
    
    # Set up signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Create scheduler with Eastern timezone
    eastern = timezone('US/Eastern')
    scheduler = BlockingScheduler(timezone=eastern)
    
    # Add job to run daily at 8:00 AM Eastern
    scheduler.add_job(
        func=signal_engine_job,
        trigger=CronTrigger(hour=8, minute=0, timezone=eastern),
        id='daily_signal_engine',
        name='Daily Stock Signal Analysis',
        max_instances=1,  # Prevent overlapping jobs
        misfire_grace_time=300,  # Allow 5 minutes grace period for missed jobs
        replace_existing=True
    )
    
    logger.info("📅 Scheduled daily job at 8:00 AM Eastern Time")
    
    # Option to run immediately for testing
    if len(sys.argv) > 1 and sys.argv[1] == '--run-now':
        logger.info("🧪 Running signal engine immediately for testing...")
        signal_engine_job()
        logger.info("🧪 Test run completed, exiting...")
        return
    
    try:
        # Start the scheduler (this will block)
        logger.info("🔄 Scheduler started. Press Ctrl+C to stop.")
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