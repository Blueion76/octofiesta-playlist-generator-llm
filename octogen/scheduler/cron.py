"""Cron scheduling support for OctoGen"""

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

try:
    from croniter import croniter
    CRONITER_AVAILABLE = True
except ImportError:
    CRONITER_AVAILABLE = False


logger = logging.getLogger(__name__)


def calculate_next_run(cron_expression: str) -> datetime:
    """Calculate next run time from cron expression.
    
    Args:
        cron_expression: Cron expression string
        
    Returns:
        Next run datetime
    """
    if not CRONITER_AVAILABLE:
        raise ImportError("croniter package required for scheduling")
    
    now = datetime.now(timezone.utc)
    cron = croniter(cron_expression, now)
    return cron.get_next(datetime)


def wait_until(target_time: datetime) -> None:
    """Wait until target time.
    
    Args:
        target_time: Target datetime to wait until
    """
    now = datetime.now(timezone.utc)
    
    if target_time <= now:
        return
    
    wait_seconds = (target_time - now).total_seconds()
    logger.info("Waiting %.1f seconds until next run at %s", 
                wait_seconds, target_time.strftime("%Y-%m-%d %H:%M:%S %Z"))
    
    time.sleep(wait_seconds)


def calculate_cron_interval(cron_expression: str) -> float:
    """Calculate average interval from cron expression.
    
    Args:
        cron_expression: Cron expression string
        
    Returns:
        Average interval in seconds
    """
    if not CRONITER_AVAILABLE:
        return 86400.0  # Default to 24 hours
    
    try:
        now = datetime.now(timezone.utc)
        cron = croniter(cron_expression, now)
        
        # Calculate intervals for next 10 runs
        times = [cron.get_next(datetime) for _ in range(10)]
        intervals = [(times[i+1] - times[i]).total_seconds() for i in range(len(times)-1)]
        
        return sum(intervals) / len(intervals) if intervals else 86400.0
    except Exception:
        return 86400.0


def run_with_schedule(func: Callable, cron_expression: str, **kwargs) -> None:
    """Run function on a schedule defined by cron expression.
    
    Args:
        func: Function to run
        cron_expression: Cron expression for schedule
        **kwargs: Additional arguments to pass to function
    """
    if not CRONITER_AVAILABLE:
        logger.error("croniter not available, cannot run scheduled tasks")
        logger.error("Install with: pip install croniter")
        return
    
    logger.info(f"Starting scheduled execution with cron: {cron_expression}")
    
    while True:
        try:
            # Calculate next run
            next_run = calculate_next_run(cron_expression)
            
            # Wait until next run
            wait_until(next_run)
            
            # Execute function
            logger.info("Executing scheduled task")
            func(**kwargs)
            
        except KeyboardInterrupt:
            logger.info("Scheduling interrupted by user")
            break
        except Exception as e:
            logger.error(f"Error in scheduled execution: {e}")
            # Wait a bit before retrying
            time.sleep(60)
