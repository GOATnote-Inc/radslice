"""Retry with exponential backoff and circuit breaker."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


class CircuitOpenError(Exception):
    """Raised when the circuit breaker is open."""

    pass


@dataclass
class CircuitBreaker:
    """Simple circuit breaker: opens after N consecutive failures, resets after cooldown."""

    failure_threshold: int = 5
    cooldown_seconds: float = 60.0
    _consecutive_failures: int = field(default=0, init=False)
    _last_failure_time: float = field(default=0.0, init=False)
    _state: str = field(default="closed", init=False)  # closed | open | half_open

    def record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = "closed"

    def record_failure(self) -> None:
        self._consecutive_failures += 1
        self._last_failure_time = time.time()
        if self._consecutive_failures >= self.failure_threshold:
            self._state = "open"
            logger.warning(
                "Circuit breaker opened after %d consecutive failures",
                self._consecutive_failures,
            )

    def check(self) -> None:
        """Raise CircuitOpenError if circuit is open and cooldown hasn't elapsed."""
        if self._state == "open":
            elapsed = time.time() - self._last_failure_time
            if elapsed < self.cooldown_seconds:
                raise CircuitOpenError(
                    f"Circuit open, {self.cooldown_seconds - elapsed:.1f}s remaining"
                )
            self._state = "half_open"

    @property
    def state(self) -> str:
        return self._state


async def retry_with_backoff(
    fn,
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
    circuit_breaker: CircuitBreaker | None = None,
    **kwargs,
):
    """Retry an async function with exponential backoff.

    Args:
        fn: Async callable to retry.
        max_retries: Maximum number of retry attempts.
        base_delay: Initial delay in seconds.
        max_delay: Maximum delay cap.
        backoff_factor: Multiplier for each retry.
        retryable_exceptions: Exception types to retry on.
        circuit_breaker: Optional circuit breaker instance.

    Returns:
        Result of fn(*args, **kwargs).
    """
    last_exc = None
    for attempt in range(max_retries + 1):
        if circuit_breaker:
            circuit_breaker.check()

        try:
            result = await fn(*args, **kwargs)
            if circuit_breaker:
                circuit_breaker.record_success()
            return result
        except retryable_exceptions as exc:
            last_exc = exc
            if circuit_breaker:
                circuit_breaker.record_failure()
            if attempt == max_retries:
                break
            delay = min(base_delay * (backoff_factor**attempt), max_delay)
            logger.warning(
                "Attempt %d/%d failed: %s. Retrying in %.1fs",
                attempt + 1,
                max_retries + 1,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]
