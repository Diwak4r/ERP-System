#!/bin/sh
set -eu

if [ -n "${DATABASE_URL:-}" ]; then
  python - <<'PY'
import os
import time

import psycopg2

database_url = os.environ.get("DATABASE_URL")
for _ in range(30):
    try:
        connection = psycopg2.connect(database_url)
        connection.close()
        break
    except Exception:
        time.sleep(1)
else:
    raise SystemExit("Database did not become available in time")
PY
fi

exec "$@"

