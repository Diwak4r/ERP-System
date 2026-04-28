from __future__ import annotations

import logging
import threading
from django.core.cache import cache
from django.http import HttpResponseForbidden

logger = logging.getLogger("production")

_thread_locals = threading.local()


def get_current_request_ip() -> str:
    return getattr(_thread_locals, "request_ip", "")


class RequestIPMiddleware:
    """Store request IP in thread-local storage for audit/event logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        # Prevent IP spoofing by taking the last IP in the chain (added by the trusted proxy)
        ip = forwarded_for.split(",")[-1].strip() if forwarded_for else request.META.get("REMOTE_ADDR", "")
        _thread_locals.request_ip = ip
        try:
            return self.get_response(request)
        finally:
            _thread_locals.request_ip = ""


class LoginRateLimitMiddleware:
    """Limits login attempts to 5 per 5 minutes per IP to prevent brute force attacks."""
    
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.path == '/admin/login/' and request.method == 'POST':
            ip = get_current_request_ip()
            if not ip:
                ip = request.META.get("REMOTE_ADDR", "")
                
            if ip:
                cache_key = f"login_attempts_{ip}"
                attempts = cache.get(cache_key, 0)
                
                if attempts >= 5:
                    logger.warning(f"Rate limit exceeded for IP {ip} on admin login.")
                    return HttpResponseForbidden("Too many login attempts. Please try again later.")
                
                cache.set(cache_key, attempts + 1, 300)
                
        return self.get_response(request)

