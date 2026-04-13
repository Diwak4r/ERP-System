from __future__ import annotations

import os

from .base import *  # noqa: F403,F401
from .base import _csv_env

DEBUG = os.environ.get("DJANGO_DEBUG", "true").lower() == "true"
ALLOWED_HOSTS = _csv_env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1,0.0.0.0")

