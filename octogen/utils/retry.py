"""Retry logic with exponential backoff and circuit breaker integration"""

import logging
import time
from typing import Callable, Optional, Type, Tuple
from functools import wraps


logger = logging.getLogger(__name__)


def retry_with_backoff(
    func: Optional[Callable] = None,
    max_retries: int = 3,
    initial_delay: float = 1.0,
    backoff_factor: float = 2.0,
    exceptions: Tuple[Type[Exception], ...] = (Exception,)
) -> Callable:
    """Retry a function with exponential backoff.
    
    Can be used as a decorator or called directly.
    
    Args:
        func: Function to retry (when used as decorator without arguments)
        max_retries: Maximum number of retry attempts
        initial_delay: Initial delay in seconds
        backoff_factor: Multiplier for delay on each retry
        exceptions: Tuple of exceptions to catch and retry
        
    Returns:
        Decorated function or decorator
        
    Example:
        @retry_with_backoff(max_retries=3)
        def my_function():
            pass
            
        # Or call directly
        result = retry_with_backoff(my_function, max_retries=3)
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            delay = initial_delay
            last_exception = None
            
            for attempt in range(max_retries + 1):
                try:
                    return f(*args, **kwargs)
                except exceptions as e:
                    last_exception = e
                    if attempt < max_retries:
                        logger.warning(
                            f"{f.__name__} failed (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {delay:.1f}s..."
                        )
                        time.sleep(delay)
                        delay *= backoff_factor
                    else:
                        logger.error(
                            f"{f.__name__} failed after {max_retries + 1} attempts: {e}"
                        )
            
            # Re-raise the last exception
            raise last_exception
        
        return wrapper
    
    # Support both @retry_with_backoff and @retry_with_backoff()
    if func is not None:
        return decorator(func)
    return decorator
