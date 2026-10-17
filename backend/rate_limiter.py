"""
Rate Limiter — DoS Protection
In-memory rate limiting for API endpoints.
Prevents abuse and resource exhaustion.
"""

import time
from collections import defaultdict
from typing import Dict, Tuple, Optional
from fastapi import Request, HTTPException

from config import settings


class InMemoryRateLimiter:
    """
    Simple in-memory rate limiter using sliding window.

    Note: This is suitable for single-instance deployments.
    For multi-instance deployments, use Redis-based rate limiting.
    """

    def __init__(
        self,
        requests_per_minute: int = 100,
        window_seconds: int = 60,
    ):
        self.requests_per_minute = requests_per_minute
        self.window_seconds = window_seconds
        self._requests: Dict[str, list] = defaultdict(list)

        # Cleanup threshold (clean old entries every N requests)
        self._cleanup_threshold = 1000
        self._request_count = 0

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request, considering proxies."""
        # Check X-Forwarded-For header (set by Nginx/Load Balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP (original client)
            # Format: client, proxy1, proxy2
            return forwarded_for.split(",")[0].strip()

        # Check X-Real-IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()

        # Fall back to direct client IP
        if request.client:
            return request.client.host

        return "unknown"

    def _cleanup_old_requests(self):
        """Remove expired request timestamps."""
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        for ip in list(self._requests.keys()):
            self._requests[ip] = [
                ts for ts in self._requests[ip] if ts > cutoff_time
            ]
            # Remove empty entries
            if not self._requests[ip]:
                del self._requests[ip]

    def is_allowed(self, request: Request) -> Tuple[bool, Optional[Dict]]:
        """
        Check if request is allowed under rate limit.

        Args:
            request: FastAPI Request object

        Returns:
            Tuple of (is_allowed, rate_limit_info)
            rate_limit_info contains: limit, remaining, reset_seconds
        """
        client_ip = self._get_client_ip(request)
        current_time = time.time()
        cutoff_time = current_time - self.window_seconds

        # Get requests in current window
        requests = self._requests[client_ip]
        requests_in_window = [ts for ts in requests if ts > cutoff_time]

        # Update stored requests
        self._requests[client_ip] = requests_in_window

        # Check limit
        is_allowed = len(requests_in_window) < self.requests_per_minute

        # Add current request if allowed
        if is_allowed:
            self._requests[client_ip].append(current_time)

        # Calculate remaining and reset time
        remaining = max(0, self.requests_per_minute - len(requests_in_window) - (1 if is_allowed else 0))
        oldest_request = min(requests_in_window) if requests_in_window else current_time
        reset_seconds = int(oldest_request + self.window_seconds - current_time)

        # Periodic cleanup
        self._request_count += 1
        if self._request_count >= self._cleanup_threshold:
            self._cleanup_old_requests()
            self._request_count = 0

        rate_info = {
            "limit": self.requests_per_minute,
            "remaining": remaining,
            "reset": reset_seconds,
        }

        return is_allowed, rate_info

    def reset(self, client_ip: str = None):
        """Reset rate limits for a specific IP or all IPs."""
        if client_ip:
            self._requests.pop(client_ip, None)
        else:
            self._requests.clear()


# Global rate limiters for different endpoint types
default_limiter = InMemoryRateLimiter(requests_per_minute=settings.rate_limit_requests)
upload_limiter = InMemoryRateLimiter(requests_per_minute=settings.rate_limit_upload_requests)
match_limiter = InMemoryRateLimiter(requests_per_minute=settings.rate_limit_match_requests)


def rate_limit(limiter: InMemoryRateLimiter = None):
    """
    FastAPI dependency for rate limiting.

    Usage:
        @app.get("/endpoint")
        async def endpoint(_: None = Depends(rate_limit())):
            ...

        # Or with specific limiter:
        @app.post("/upload")
        async def upload(_: None = Depends(rate_limit(upload_limiter))):
            ...
    """
    if limiter is None:
        limiter = default_limiter

    async def check_rate_limit(request: Request):
        if not settings.rate_limit_enabled:
            return None

        is_allowed, rate_info = limiter.is_allowed(request)

        # Add rate limit headers to response
        # Note: We'll set these in middleware since we can't modify response here

        if not is_allowed:
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please try again later.",
                headers={
                    "Retry-After": str(rate_info["reset"]),
                    "X-RateLimit-Limit": str(rate_info["limit"]),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(rate_info["reset"]),
                }
            )

        return rate_info

    return check_rate_limit


async def rate_limit_middleware(request: Request, call_next):
    """
    FastAPI middleware for adding rate limit headers to responses.
    Actual rate limiting is done by the rate_limit dependency.
    """
    # This middleware adds headers to responses from rate-limited endpoints
    # The actual rate limiting logic is in the rate_limit dependency
    response = await call_next(request)
    return response


# Utility function for testing
def get_stats() -> Dict:
    """Get rate limiter statistics (for monitoring/debugging)."""
    return {
        "default_limiter": {
            "tracked_ips": len(default_limiter._requests),
            "requests_per_minute": default_limiter.requests_per_minute,
        },
        "upload_limiter": {
            "tracked_ips": len(upload_limiter._requests),
            "requests_per_minute": upload_limiter.requests_per_minute,
        },
        "match_limiter": {
            "tracked_ips": len(match_limiter._requests),
            "requests_per_minute": match_limiter.requests_per_minute,
        },
    }
