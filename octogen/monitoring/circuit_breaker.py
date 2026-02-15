"""Circuit breaker pattern for resilient external API calls"""

import logging
import time
from enum import Enum
from typing import Callable, Any, Optional
from functools import wraps


logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states"""
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """Circuit breaker to prevent cascading failures.
    
    Tracks failures and automatically opens circuit after threshold.
    Attempts recovery after timeout period.
    """
    
    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        timeout: int = 60,
        half_open_attempts: int = 1
    ):
        """Initialize circuit breaker.
        
        Args:
            name: Name of the circuit for logging
            failure_threshold: Number of failures before opening circuit
            timeout: Seconds to wait before attempting recovery
            half_open_attempts: Number of successful calls needed to close circuit
        """
        self.name = name
        self.failure_threshold = failure_threshold
        self.timeout = timeout
        self.half_open_attempts = half_open_attempts
        
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: Optional[float] = None
        
    def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker.
        
        Args:
            func: Function to call
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result
            
        Raises:
            Exception: If circuit is open or function fails
        """
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self._transition_to_half_open()
            else:
                raise Exception(f"Circuit breaker {self.name} is OPEN")
        
        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise e
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return False
        return time.time() - self.last_failure_time >= self.timeout
    
    def _transition_to_half_open(self) -> None:
        """Transition from OPEN to HALF_OPEN state"""
        logger.info(f"Circuit breaker {self.name}: OPEN -> HALF_OPEN (attempting recovery)")
        self.state = CircuitState.HALF_OPEN
        self.success_count = 0
    
    def _on_success(self) -> None:
        """Handle successful call"""
        if self.state == CircuitState.HALF_OPEN:
            self.success_count += 1
            if self.success_count >= self.half_open_attempts:
                self._transition_to_closed()
        elif self.state == CircuitState.CLOSED:
            # Reset failure count on success
            self.failure_count = 0
    
    def _on_failure(self) -> None:
        """Handle failed call"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        
        if self.state == CircuitState.HALF_OPEN:
            self._transition_to_open()
        elif self.state == CircuitState.CLOSED:
            if self.failure_count >= self.failure_threshold:
                self._transition_to_open()
    
    def _transition_to_open(self) -> None:
        """Transition to OPEN state"""
        logger.warning(
            f"Circuit breaker {self.name}: {self.state.value} -> OPEN "
            f"({self.failure_count} failures)"
        )
        self.state = CircuitState.OPEN
    
    def _transition_to_closed(self) -> None:
        """Transition to CLOSED state"""
        logger.info(f"Circuit breaker {self.name}: HALF_OPEN -> CLOSED (recovered)")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
    
    def reset(self) -> None:
        """Manually reset circuit breaker to CLOSED state"""
        logger.info(f"Circuit breaker {self.name}: Manual reset to CLOSED")
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time = None


def circuit_breaker(
    name: str,
    failure_threshold: int = 5,
    timeout: int = 60
):
    """Decorator to apply circuit breaker to a function.
    
    Args:
        name: Name of the circuit
        failure_threshold: Number of failures before opening
        timeout: Seconds before attempting recovery
        
    Returns:
        Decorated function
    """
    breaker = CircuitBreaker(name, failure_threshold, timeout)
    
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            return breaker.call(func, *args, **kwargs)
        wrapper.circuit_breaker = breaker  # Expose breaker for testing/reset
        return wrapper
    return decorator
