"""Retry management with exponential backoff for downloads."""

import asyncio
import random
from typing import Callable, Any, Optional, Type, Union
from datetime import datetime, timedelta
from api.exceptions import RateLimitError, NetworkError, ZenfolioAPIError
from config.settings import Settings
from logs.logger import get_logger, log_api_rate_limit
from progress.console_progress import console_progress
import aiohttp

logger = get_logger(__name__)


class RetryManager:
    """Manages retry logic with exponential backoff and jitter."""
    
    def __init__(self, settings: Settings):
        """Initialize retry manager.
        
        Args:
            settings: Application settings
        """
        self.settings = settings
        self.max_retries = settings.max_retries
        self.initial_backoff = settings.initial_backoff_seconds
        self.max_backoff = settings.max_backoff_seconds
    
    async def retry_with_backoff(
        self,
        func: Callable,
        *args,
        retryable_exceptions: tuple = (
            NetworkError,
            RateLimitError,
            TimeoutError,
            asyncio.TimeoutError,
            ConnectionError,
            OSError
        ),
        max_retries: Optional[int] = None,
        **kwargs
    ) -> Any:
        """Execute function with retry and exponential backoff.
        
        Args:
            func: Function to execute
            *args: Function arguments
            retryable_exceptions: Exceptions that should trigger retry
            max_retries: Override default max retries
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: Last exception if all retries exhausted
        """
        max_attempts = (max_retries or self.max_retries) + 1
        last_exception = None
        
        for attempt in range(max_attempts):
            try:
                if asyncio.iscoroutinefunction(func):
                    result = await func(*args, **kwargs)
                else:
                    result = func(*args, **kwargs)
                
                # Clear retry info on success
                if attempt > 0:
                    console_progress.clear_retry_info()
                
                return result
                    
            except retryable_exceptions as e:
                last_exception = e
                
                if attempt == max_attempts - 1:
                    # Last attempt, don't retry
                    logger.debug(f"All retry attempts exhausted for {func.__name__}: {e}")
                    break
                
                # Calculate backoff time
                backoff_time = await self._calculate_backoff(attempt, e)
                
                # Provide comprehensive error logging for debugging
                error_type = type(e).__name__
                
                # Extract detailed error information
                error_details = {
                    'function': func.__name__,
                    'attempt': f"{attempt + 1}/{max_attempts}",
                    'error_type': error_type,
                    'error_message': str(e),
                    'backoff_time': f"{backoff_time:.2f}s"
                }
                
                # Add HTTP-specific details if available
                if hasattr(e, 'status'):
                    error_details['status_code'] = e.status
                if hasattr(e, 'message'):
                    error_details['http_message'] = e.message
                if hasattr(e, 'headers'):
                    error_details['response_headers'] = dict(e.headers) if e.headers else None
                
                # Add aiohttp-specific details
                if isinstance(e, aiohttp.ClientError):
                    if hasattr(e, 'status'):
                        error_details['aiohttp_status'] = e.status
                    if hasattr(e, 'request_info'):
                        error_details['url'] = str(e.request_info.url) if e.request_info else None
                        error_details['method'] = e.request_info.method if e.request_info else None
                
                # Check for Zenfolio image retrieval scenario (timeout on attempt 3+)
                if isinstance(e, (TimeoutError, asyncio.TimeoutError)) and attempt >= 2:
                    # Show skip info in progress bar instead of logging
                    console_progress.set_skip_info("will be added to retry queue")
                    logger.debug(f"ZENFOLIO IMAGE RETRIEVAL: Skipping after {attempt + 1} attempts - will be added to retry queue")
                    # Don't retry further for this scenario
                    break
                elif isinstance(e, (TimeoutError, asyncio.TimeoutError)):
                    # Show retry info in progress bar for attempts > 1
                    if attempt > 0:
                        console_progress.set_retry_info(attempt + 1, max_attempts)
                    
                    # Only log as DEBUG during active downloads to keep interface clean
                    logger.debug(f"DOWNLOAD TIMEOUT (retry {attempt + 1}/{max_retries or self.max_retries}): {error_details}")
                else:
                    # Show retry info in progress bar for attempts > 1
                    if attempt > 0:
                        console_progress.set_retry_info(attempt + 1, max_attempts)
                    
                    # Only log as DEBUG during active downloads to keep interface clean
                    logger.debug(f"DOWNLOAD ERROR (retry {attempt + 1}/{max_retries or self.max_retries}): {error_details}")
                
                await asyncio.sleep(backoff_time)
            
            except Exception as e:
                # Non-retryable exception
                console_progress.clear_retry_info()
                error_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
                logger.debug(f"Non-retryable error in {func.__name__}: {error_msg}")
                raise
        
        # If we get here, all retries were exhausted
        console_progress.clear_retry_info()
        raise last_exception
    
    async def _calculate_backoff(self, attempt: int, exception: Exception) -> float:
        """Calculate backoff time for retry attempt.
        
        Args:
            attempt: Current attempt number (0-based)
            exception: Exception that triggered retry
            
        Returns:
            Backoff time in seconds
        """
        # Handle rate limit exceptions specially
        if isinstance(exception, RateLimitError) and exception.retry_after:
            log_api_rate_limit(exception.retry_after)
            return exception.retry_after
        
        # Handle timeout errors with shorter initial backoff
        if isinstance(exception, (TimeoutError, asyncio.TimeoutError)):
            # Use shorter backoff for timeouts since they're often transient
            base_backoff = min(self.initial_backoff, 2.0) * (1.5 ** attempt)
        else:
            # Exponential backoff with jitter for other errors
            base_backoff = self.initial_backoff * (2 ** attempt)
        
        # Cap at max backoff
        base_backoff = min(base_backoff, self.max_backoff)
        
        # Add jitter (±25% of base backoff)
        jitter = base_backoff * 0.25 * (2 * random.random() - 1)
        backoff_time = base_backoff + jitter
        
        # Ensure minimum backoff
        return max(backoff_time, 0.1)
    
    def create_retry_decorator(
        self,
        retryable_exceptions: tuple = (NetworkError, RateLimitError),
        max_retries: Optional[int] = None
    ):
        """Create a retry decorator for functions.
        
        Args:
            retryable_exceptions: Exceptions that should trigger retry
            max_retries: Override default max retries
            
        Returns:
            Decorator function
        """
        def decorator(func):
            async def wrapper(*args, **kwargs):
                return await self.retry_with_backoff(
                    func, *args,
                    retryable_exceptions=retryable_exceptions,
                    max_retries=max_retries,
                    **kwargs
                )
            return wrapper
        return decorator


class CircuitBreaker:
    """Circuit breaker pattern for handling repeated failures."""
    
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        """Initialize circuit breaker.
        
        Args:
            failure_threshold: Number of failures before opening circuit
            recovery_timeout: Time to wait before attempting recovery
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failure_count = 0
        self.last_failure_time: Optional[datetime] = None
        self.state = "closed"  # closed, open, half-open
    
    async def call(self, func: Callable, *args, **kwargs) -> Any:
        """Execute function through circuit breaker.
        
        Args:
            func: Function to execute
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Function result
            
        Raises:
            Exception: If circuit is open or function fails
        """
        if self.state == "open":
            if self._should_attempt_reset():
                self.state = "half-open"
                logger.debug("Circuit breaker attempting recovery")
            else:
                raise Exception("Circuit breaker is open - too many recent failures")
        
        try:
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # Success - reset failure count
            if self.state == "half-open":
                self.state = "closed"
                logger.debug("Circuit breaker recovered")
            
            self.failure_count = 0
            return result
            
        except Exception as e:
            self._record_failure()
            raise
    
    def _record_failure(self) -> None:
        """Record a failure and potentially open the circuit."""
        self.failure_count += 1
        self.last_failure_time = datetime.now()
        
        if self.failure_count >= self.failure_threshold:
            self.state = "open"
            logger.warning(
                f"Circuit breaker opened after {self.failure_count} failures. "
                f"Will attempt recovery in {self.recovery_timeout} seconds"
            )
    
    def _should_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt recovery."""
        if not self.last_failure_time:
            return True
        
        time_since_failure = datetime.now() - self.last_failure_time
        return time_since_failure.total_seconds() >= self.recovery_timeout
    
    def reset(self) -> None:
        """Manually reset the circuit breaker."""
        self.state = "closed"
        self.failure_count = 0
        self.last_failure_time = None
        logger.debug("Circuit breaker manually reset")


class DownloadRetryManager(RetryManager):
    """Specialized retry manager for download operations."""
    
    def __init__(self, settings: Settings):
        """Initialize download retry manager."""
        super().__init__(settings)
        self.circuit_breaker = CircuitBreaker(
            failure_threshold=10,
            recovery_timeout=120.0
        )
        self.last_attempt_count = 0
    
    async def retry_download(
        self,
        download_func: Callable,
        file_path: str,
        *args,
        **kwargs
    ) -> Any:
        """Retry download with circuit breaker protection.
        
        Args:
            download_func: Download function to execute
            file_path: Path of file being downloaded (for logging)
            *args: Function arguments
            **kwargs: Function keyword arguments
            
        Returns:
            Download result
        """
        self.last_attempt_count = 0
        try:
            return await self.circuit_breaker.call(
                self._retry_with_attempt_tracking,
                download_func,
                *args,
                retryable_exceptions=(
                    NetworkError,
                    RateLimitError,
                    ZenfolioAPIError,
                    TimeoutError,
                    asyncio.TimeoutError,
                    aiohttp.ServerTimeoutError,
                    aiohttp.ClientError,
                    ConnectionError,
                    OSError
                ),
                **kwargs
            )
        except Exception as e:
            error_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
            logger.debug(f"Download failed for {file_path}: {error_msg}")
            raise
    
    async def _retry_with_attempt_tracking(
        self,
        func: Callable,
        *args,
        retryable_exceptions: tuple = (
            NetworkError,
            RateLimitError,
            TimeoutError,
            asyncio.TimeoutError,
            ConnectionError,
            OSError
        ),
        max_retries: Optional[int] = None,
        **kwargs
    ) -> Any:
        """Execute function with retry and track attempt count."""
        max_attempts = (max_retries or self.max_retries) + 1
        last_exception = None
        
        for attempt in range(max_attempts):
            self.last_attempt_count = attempt + 1
            try:
                return await func(*args, **kwargs)
            except retryable_exceptions as e:
                last_exception = e
                
                if attempt == max_attempts - 1:
                    # Last attempt, don't retry
                    logger.debug(f"All retry attempts exhausted for {func.__name__}: {e}")
                    break
                
                # Calculate backoff time
                backoff_time = await self._calculate_backoff(attempt, e)
                
                # Provide comprehensive error logging for debugging
                error_type = type(e).__name__
                
                # Extract detailed error information
                error_details = {
                    'function': func.__name__,
                    'attempt': f"{attempt + 1}/{max_attempts}",
                    'error_type': error_type,
                    'error_message': str(e),
                    'backoff_time': f"{backoff_time:.2f}s"
                }
                
                # Add HTTP-specific details if available
                if hasattr(e, 'status'):
                    error_details['status_code'] = e.status
                if hasattr(e, 'message'):
                    error_details['http_message'] = e.message
                if hasattr(e, 'headers'):
                    error_details['response_headers'] = dict(e.headers) if e.headers else None
                
                # Add aiohttp-specific details
                if isinstance(e, aiohttp.ClientError):
                    if hasattr(e, 'status'):
                        error_details['aiohttp_status'] = e.status
                    if hasattr(e, 'request_info'):
                        error_details['url'] = str(e.request_info.url) if e.request_info else None
                        error_details['method'] = e.request_info.method if e.request_info else None
                
                # Check for Zenfolio image retrieval scenario (timeout on attempt 3+)
                if isinstance(e, (TimeoutError, asyncio.TimeoutError)) and attempt >= 2:
                    # Show skip info in progress bar instead of logging
                    console_progress.set_skip_info("will be added to retry queue")
                    logger.debug(f"ZENFOLIO IMAGE RETRIEVAL: Skipping after {attempt + 1} attempts - will be added to retry queue")
                    # Don't retry further for this scenario
                    break
                elif isinstance(e, (TimeoutError, asyncio.TimeoutError)):
                    # Show retry info in progress bar for attempts > 1
                    if attempt > 0:
                        console_progress.set_retry_info(attempt + 1, max_attempts)
                    
                    # Only log as DEBUG during active downloads to keep interface clean
                    logger.debug(f"DOWNLOAD TIMEOUT (retry {attempt + 1}/{max_retries or self.max_retries}): {error_details}")
                else:
                    # Show retry info in progress bar for attempts > 1
                    if attempt > 0:
                        console_progress.set_retry_info(attempt + 1, max_attempts)
                    
                    # Only log as DEBUG during active downloads to keep interface clean
                    logger.debug(f"DOWNLOAD ERROR (retry {attempt + 1}/{max_retries or self.max_retries}): {error_details}")
                
                await asyncio.sleep(backoff_time)
            
            except Exception as e:
                # Non-retryable exception
                console_progress.clear_retry_info()
                error_msg = str(e) if str(e) else f"{type(e).__name__}: {repr(e)}"
                logger.debug(f"Non-retryable error in {func.__name__}: {error_msg}")
                raise
        
        # If we get here, all retries were exhausted
        console_progress.clear_retry_info()
        raise last_exception