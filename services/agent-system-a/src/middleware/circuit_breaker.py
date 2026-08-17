"""
Circuit Breaker Pattern — Protects External HTTP Calls.

States:
- CLOSED: normal operation, requests pass through
- OPEN: service is down, fail immediately with graceful error (no HTTP call)
- HALF_OPEN: after recovery timeout, allow one probe request through

Config:
- failure_threshold: consecutive failures before tripping open (default: 3)
- recovery_timeout: seconds before trying again (default: 30)

Usage:
    mcp_breaker = CircuitBreaker("mcp-server", failure_threshold=3, recovery_timeout=30)

    try:
        result = mcp_breaker.call(lambda: httpx.post(...))
    except CircuitBreakerOpen as e:
        return {"error": "Service temporarily unavailable"}
"""

import time
import logging
from typing import Callable, Any
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreakerOpen(Exception):
    """Raised when the circuit breaker is open and requests are blocked."""

    def __init__(self, service_name: str, recovery_in: float):
        self.service_name = service_name
        self.recovery_in = recovery_in
        super().__init__(
            f"Circuit breaker OPEN for '{service_name}'. "
            f"Service unavailable. Retry in {recovery_in:.0f}s."
        )


class CircuitBreaker:
    """
    In-memory circuit breaker for external service calls.

    Thread-safe for single-process use (FastAPI with uvicorn workers).
    """

    def __init__(self, service_name: str, failure_threshold: int = 3, recovery_timeout: int = 30):
        self.service_name = service_name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time = 0.0
        self._last_success_time = 0.0

    @property
    def state(self) -> CircuitState:
        """Get current state, checking if we should transition to HALF_OPEN."""
        if self._state == CircuitState.OPEN:
            elapsed = time.time() - self._last_failure_time
            if elapsed >= self.recovery_timeout:
                self._state = CircuitState.HALF_OPEN
                logger.info(f"[CircuitBreaker:{self.service_name}] OPEN → HALF_OPEN (recovery timeout elapsed)")
        return self._state

    def call(self, func: Callable, *args, **kwargs) -> Any:
        """
        Execute a function through the circuit breaker.

        Args:
            func: Callable that makes the external HTTP request.

        Returns:
            The result of func() if successful.

        Raises:
            CircuitBreakerOpen: If the circuit is open and requests are blocked.
        """
        current_state = self.state

        if current_state == CircuitState.OPEN:
            recovery_in = self.recovery_timeout - (time.time() - self._last_failure_time)
            logger.warning(
                f"[CircuitBreaker:{self.service_name}] OPEN — blocking request (retry in {recovery_in:.0f}s)"
            )
            raise CircuitBreakerOpen(self.service_name, recovery_in)

        try:
            result = func(*args, **kwargs)
            self._on_success()
            return result

        except CircuitBreakerOpen:
            raise  # Re-raise, don't count as failure

        except Exception as e:
            self._on_failure(e)
            raise

    def _on_success(self):
        """Record a successful call."""
        self._failure_count = 0
        self._last_success_time = time.time()

        if self._state == CircuitState.HALF_OPEN:
            self._state = CircuitState.CLOSED
            logger.info(f"[CircuitBreaker:{self.service_name}] HALF_OPEN → CLOSED (probe succeeded)")

    def _on_failure(self, error: Exception):
        """Record a failed call."""
        self._failure_count += 1
        self._last_failure_time = time.time()

        logger.warning(
            f"[CircuitBreaker:{self.service_name}] failure #{self._failure_count}/{self.failure_threshold}: {error}"
        )

        if self._failure_count >= self.failure_threshold:
            self._state = CircuitState.OPEN
            logger.error(
                f"[CircuitBreaker:{self.service_name}] CLOSED → OPEN "
                f"({self._failure_count} consecutive failures)"
            )

    def reset(self):
        """Manually reset the circuit breaker."""
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        logger.info(f"[CircuitBreaker:{self.service_name}] manually reset to CLOSED")

    @property
    def status(self) -> dict:
        """Get circuit breaker status for monitoring."""
        return {
            "service": self.service_name,
            "state": self.state.value,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout": self.recovery_timeout,
        }
