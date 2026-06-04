"""
Test-specific Django settings.
Forces SQLite in-memory DB so tests never touch Supabase.
"""
from __future__ import annotations

from .dev import *  # noqa: F401, F403

# ── Override DB to fast in-memory SQLite ────────────────────────────────────
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }
}

# ── Speed: skip password hashing in tests ───────────────────────────────────
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ── Silence unneeded warnings ────────────────────────────────────────────────
LOGGING = {}
