"""
agents/retry_utils.py
─────────────────────
Transient failures के लिए retry logic।
Google APIs में rate limiting और network errors आम हैं।
"""

from __future__ import annotations

import logging
import time
from functools import wraps
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def retry_on_failure(
    max_attempts: int = 3,
    delay_sec: float = 2.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
) -> Callable:
    """
    Decorator: function call को retry करता है अगर exception आए।
    
    Usage:
        @retry_on_failure(max_attempts=3, delay_sec=2)
        def my_api_call():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay_sec

            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"⚠️  Attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {current_delay}s..."
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(
                            f"❌ All {max_attempts} attempts failed: {e}"
                        )

            raise last_exception  # type: ignore
        return wrapper
    return decorator


def retry_on_failure_async(
    max_attempts: int = 3,
    delay_sec: float = 2.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple = (Exception,),
) -> Callable:
    """
    Async version: async function call को retry करता है।
    """
    import asyncio

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            current_delay = delay_sec

            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(
                            f"⚠️  Attempt {attempt}/{max_attempts} failed: {e}. "
                            f"Retrying in {current_delay}s..."
                        )
                        await asyncio.sleep(current_delay)
                        current_delay *= backoff_factor
                    else:
                        logger.error(
                            f"❌ All {max_attempts} attempts failed: {e}"
                        )

            raise last_exception  # type: ignore
        return wrapper
    return decorator
