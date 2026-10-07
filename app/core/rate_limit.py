import time
import hashlib
from typing import Dict, List, Optional
from fastapi import Request
from app.core.errors import AppException

class RateLimiter:
    """
    In-memory sliding window rate limiter per client IP hash.
    Minimizes data retention: Stores only truncated SHA-256 hashes of client IP,
    never raw IP addresses.
    Zero external Redis dependency required for initial phase.
    """
    def __init__(self, max_requests: int = 5, window_seconds: int = 60):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        # hash -> list of timestamps
        self._history: Dict[str, List[float]] = {}

    def _hash_ip(self, ip: str) -> str:
        return hashlib.sha256(ip.encode()).hexdigest()[:16]

    def check_rate_limit(self, request: Request) -> str:
        client_ip = request.client.host if request.client else "unknown"
        ip_hash = self._hash_ip(client_ip)
        now = time.time()

        timestamps = self._history.get(ip_hash, [])
        # Evict timestamps older than window
        valid_timestamps = [t for t in timestamps if now - t < self.window_seconds]

        if len(valid_timestamps) >= self.max_requests:
            raise AppException(
                status_code=429,
                detail="Rate limit exceeded. Please wait a few moments before transmitting again.",
                code="RATE_LIMITED",
                extra={"retry_after_seconds": int(self.window_seconds - (now - valid_timestamps[0]))}
            )

        valid_timestamps.append(now)
        self._history[ip_hash] = valid_timestamps
        return ip_hash

contact_rate_limiter = RateLimiter(max_requests=5, window_seconds=60)
review_rate_limiter = RateLimiter(max_requests=3, window_seconds=60)
