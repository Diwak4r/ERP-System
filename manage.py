#!/usr/bin/env python
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    src_path = base_dir / "src"
    sys.path.append(str(src_path))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
