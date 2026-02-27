"""Tests for retry.py — backoff and circuit breaker."""

from __future__ import annotations

import time

import pytest

from radslice.retry import CircuitBreaker, CircuitOpenError, retry_with_backoff


class TestCircuitBreaker:
    def test_initial_state(self):
        cb = CircuitBreaker()
        assert cb.state == "closed"

    def test_opens_after_threshold(self):
        cb = CircuitBreaker(failure_threshold=3)
        for _ in range(3):
            cb.record_failure()
        assert cb.state == "open"

    def test_stays_closed_below_threshold(self):
        cb = CircuitBreaker(failure_threshold=5)
        for _ in range(4):
            cb.record_failure()
        assert cb.state == "closed"

    def test_success_resets(self):
        cb = CircuitBreaker(failure_threshold=3)
        cb.record_failure()
        cb.record_failure()
        cb.record_success()
        assert cb.state == "closed"
        assert cb._consecutive_failures == 0

    def test_check_raises_when_open(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=60)
        cb.record_failure()
        with pytest.raises(CircuitOpenError):
            cb.check()

    def test_half_open_after_cooldown(self):
        cb = CircuitBreaker(failure_threshold=1, cooldown_seconds=0.01)
        cb.record_failure()
        time.sleep(0.02)
        cb.check()  # Should not raise
        assert cb.state == "half_open"

    def test_check_passes_when_closed(self):
        cb = CircuitBreaker()
        cb.check()  # Should not raise


class TestRetryWithBackoff:
    @pytest.mark.asyncio
    async def test_success_no_retry(self):
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            return "ok"

        result = await retry_with_backoff(fn, max_retries=3, base_delay=0.01)
        assert result == "ok"
        assert call_count == 1

    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("fail")
            return "ok"

        result = await retry_with_backoff(
            fn, max_retries=3, base_delay=0.01, retryable_exceptions=(ValueError,)
        )
        assert result == "ok"
        assert call_count == 3

    @pytest.mark.asyncio
    async def test_exhausted_retries(self):
        async def fn():
            raise ValueError("always fails")

        with pytest.raises(ValueError, match="always fails"):
            await retry_with_backoff(
                fn, max_retries=2, base_delay=0.01, retryable_exceptions=(ValueError,)
            )

    @pytest.mark.asyncio
    async def test_non_retryable_exception(self):
        async def fn():
            raise TypeError("not retryable")

        with pytest.raises(TypeError):
            await retry_with_backoff(
                fn, max_retries=3, base_delay=0.01, retryable_exceptions=(ValueError,)
            )

    @pytest.mark.asyncio
    async def test_circuit_breaker_integration(self):
        cb = CircuitBreaker(failure_threshold=2, cooldown_seconds=60)
        call_count = 0

        async def fn():
            nonlocal call_count
            call_count += 1
            raise ValueError("fail")

        with pytest.raises((ValueError, CircuitOpenError)):
            await retry_with_backoff(
                fn,
                max_retries=5,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),
                circuit_breaker=cb,
            )
