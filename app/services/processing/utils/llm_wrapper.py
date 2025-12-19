"""
Shared LLM call wrapper with retry logic, timeout handling, and error management.
"""
import asyncio
import logging
import time
from typing import Optional, Callable, Any, Dict
from functools import wraps
from langchain_openai import AzureChatOpenAI
from openai import RateLimitError, APIError, Timeout

logger = logging.getLogger(__name__)


class LLMCallError(Exception):
    """Base exception for LLM call errors."""
    pass


class LLMTimeoutError(LLMCallError):
    """Exception raised when LLM call times out."""
    pass


class LLMRateLimitError(LLMCallError):
    """Exception raised when rate limit is hit."""
    pass


def call_llm_with_retry(
    llm: AzureChatOpenAI,
    prompt: str,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: int = 60,
    context: str = ""
) -> Any:
    """
    Call LLM synchronously with retry logic, rate limit handling, and timeout.
    
    Args:
        llm: AzureChatOpenAI instance
        prompt: Prompt string
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
        timeout: Timeout in seconds for each call
        context: Context string for logging (e.g., "culture extraction")
        
    Returns:
        LLM response object
        
    Raises:
        LLMTimeoutError: If call times out
        LLMRateLimitError: If rate limit is hit after all retries
        LLMCallError: For other LLM call errors
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            
            # Use invoke with timeout handling
            # Note: AzureChatOpenAI doesn't have built-in timeout, so we use asyncio
            # For sync calls, we'll rely on the underlying library's timeout
            response = llm.invoke(prompt)
            
            elapsed = time.time() - start_time
            logger.debug(
                f"LLM call successful. Context: {context}. "
                f"Attempt: {attempt + 1}/{max_retries}. "
                f"Time: {elapsed:.2f}s"
            )
            
            return response
            
        except RateLimitError as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)  # Exponential backoff
                logger.warning(
                    f"Rate limit hit. Context: {context}. "
                    f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(delay)
            else:
                logger.error(
                    f"Rate limit error after {max_retries} attempts. Context: {context}"
                )
                raise LLMRateLimitError(
                    f"Rate limit exceeded after {max_retries} attempts. Context: {context}"
                ) from e
                
        except Timeout as e:
            last_exception = e
            logger.error(
                f"LLM call timed out. Context: {context}. "
                f"Attempt: {attempt + 1}/{max_retries}"
            )
            if attempt == max_retries - 1:
                raise LLMTimeoutError(
                    f"LLM call timed out after {timeout}s. Context: {context}"
                ) from e
            # Retry on timeout
            delay = base_delay * (2 ** attempt)
            time.sleep(delay)
            
        except APIError as e:
            last_exception = e
            error_code = getattr(e, 'status_code', None)
            
            # Retry on 5xx errors (server errors)
            if error_code and 500 <= error_code < 600:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Server error {error_code}. Context: {context}. "
                        f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    logger.error(
                        f"Server error {error_code} after {max_retries} attempts. Context: {context}"
                    )
                    raise LLMCallError(
                        f"Server error {error_code} after {max_retries} attempts. Context: {context}"
                    ) from e
            else:
                # Don't retry on 4xx errors (client errors)
                logger.error(
                    f"API error {error_code}. Context: {context}. Not retrying."
                )
                raise LLMCallError(
                    f"API error {error_code}. Context: {context}"
                ) from e
                
        except Exception as e:
            last_exception = e
            # Check if it's a timeout-related error
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Timeout error. Context: {context}. "
                        f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue
                else:
                    raise LLMTimeoutError(
                        f"Timeout error after {max_retries} attempts. Context: {context}"
                    ) from e
            
            # For other errors, only retry if it's a transient error
            if attempt < max_retries - 1:
                # Check if error message suggests it's retryable
                retryable_keywords = [
                    "connection", "network", "temporary", "unavailable",
                    "service", "busy", "overloaded"
                ]
                if any(keyword in str(e).lower() for keyword in retryable_keywords):
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Transient error: {str(e)}. Context: {context}. "
                        f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(delay)
                    continue
            
            # Non-retryable error or max retries reached
            logger.error(
                f"LLM call failed. Context: {context}. "
                f"Attempt: {attempt + 1}/{max_retries}. Error: {str(e)}"
            )
            raise LLMCallError(
                f"LLM call failed after {attempt + 1} attempts. Context: {context}. Error: {str(e)}"
            ) from e
    
    # Should not reach here, but just in case
    raise LLMCallError(
        f"LLM call failed after {max_retries} attempts. Context: {context}"
    ) from last_exception


async def call_llm_async_with_retry(
    llm: AzureChatOpenAI,
    prompt: str,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: int = 60,
    context: str = ""
) -> Any:
    """
    Call LLM asynchronously with retry logic, rate limit handling, and timeout.
    
    Args:
        llm: AzureChatOpenAI instance
        prompt: Prompt string
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
        timeout: Timeout in seconds for each call
        context: Context string for logging
        
    Returns:
        LLM response object
        
    Raises:
        LLMTimeoutError: If call times out
        LLMRateLimitError: If rate limit is hit after all retries
        LLMCallError: For other LLM call errors
    """
    last_exception = None
    
    for attempt in range(max_retries):
        try:
            start_time = time.time()
            
            # Use asyncio.wait_for for timeout
            response = await asyncio.wait_for(
                llm.ainvoke(prompt),
                timeout=timeout
            )
            
            elapsed = time.time() - start_time
            logger.debug(
                f"LLM call successful (async). Context: {context}. "
                f"Attempt: {attempt + 1}/{max_retries}. "
                f"Time: {elapsed:.2f}s"
            )
            
            return response
            
        except asyncio.TimeoutError:
            last_exception = asyncio.TimeoutError()
            logger.error(
                f"LLM call timed out (async). Context: {context}. "
                f"Attempt: {attempt + 1}/{max_retries}"
            )
            if attempt == max_retries - 1:
                raise LLMTimeoutError(
                    f"LLM call timed out after {timeout}s. Context: {context}"
                ) from last_exception
            delay = base_delay * (2 ** attempt)
            await asyncio.sleep(delay)
            
        except RateLimitError as e:
            last_exception = e
            if attempt < max_retries - 1:
                delay = base_delay * (2 ** attempt)
                logger.warning(
                    f"Rate limit hit (async). Context: {context}. "
                    f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                )
                await asyncio.sleep(delay)
            else:
                logger.error(
                    f"Rate limit error after {max_retries} attempts (async). Context: {context}"
                )
                raise LLMRateLimitError(
                    f"Rate limit exceeded after {max_retries} attempts. Context: {context}"
                ) from e
                
        except APIError as e:
            last_exception = e
            error_code = getattr(e, 'status_code', None)
            
            if error_code and 500 <= error_code < 600:
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Server error {error_code} (async). Context: {context}. "
                        f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise LLMCallError(
                        f"Server error {error_code} after {max_retries} attempts. Context: {context}"
                    ) from e
            else:
                logger.error(
                    f"API error {error_code} (async). Context: {context}. Not retrying."
                )
                raise LLMCallError(
                    f"API error {error_code}. Context: {context}"
                ) from e
                
        except Exception as e:
            last_exception = e
            if "timeout" in str(e).lower() or "timed out" in str(e).lower():
                if attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Timeout error (async). Context: {context}. "
                        f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue
                else:
                    raise LLMTimeoutError(
                        f"Timeout error after {max_retries} attempts. Context: {context}"
                    ) from e
            
            if attempt < max_retries - 1:
                retryable_keywords = [
                    "connection", "network", "temporary", "unavailable",
                    "service", "busy", "overloaded"
                ]
                if any(keyword in str(e).lower() for keyword in retryable_keywords):
                    delay = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Transient error (async): {str(e)}. Context: {context}. "
                        f"Retrying in {delay:.1f}s (attempt {attempt + 1}/{max_retries})"
                    )
                    await asyncio.sleep(delay)
                    continue
            
            logger.error(
                f"LLM call failed (async). Context: {context}. "
                f"Attempt: {attempt + 1}/{max_retries}. Error: {str(e)}"
            )
            raise LLMCallError(
                f"LLM call failed after {attempt + 1} attempts. Context: {context}. Error: {str(e)}"
            ) from e
    
    raise LLMCallError(
        f"LLM call failed after {max_retries} attempts. Context: {context}"
    ) from last_exception









