from __future__ import annotations

import threading

_thread_locals = threading.local()


def get_current_request_ip() -> str:
    return getattr(_thread_locals, "request_ip", "")


class RequestIPMiddleware:
    """Store request IP in thread-local storage for audit/event logging."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR", "")
        ip = forwarded_for.split(",")[0].strip() if forwarded_for else request.META.get("REMOTE_ADDR", "")
        _thread_locals.request_ip = ip
        try:
            return self.get_response(request)
        finally:
            _thread_locals.request_ip = ""

