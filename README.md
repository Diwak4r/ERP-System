# ERP-System

Production-grade in-house ERP/Tracker system for manufacturing facilities. Current scope includes production entry forms, aggregate reporting, and a Docker-based development stack.

## Local Setup (Docker)

1. Copy env file and update values if needed:
   ```bash
   cp .env.example .env
   ```
   **Note for Production (Supabase):** Ensure you set the `DATABASE_URL` environment variable to your Supabase PostgreSQL connection string securely. For example:
   `DATABASE_URL=postgres://postgres:[PASSWORD]@db.[PROJECT_ID].supabase.co:5432/postgres`

2. Start services:
   ```bash
   docker compose build
   docker compose up -d
   ```
3. Run migrations:
   ```bash
   docker compose exec web python manage.py migrate
   ```
4. Open app:
   - App: http://localhost:8000/production/entry/
   - Health check: http://localhost:8000/healthz

## Verification Commands

Run these before finishing any task:

```bash
docker compose build
docker compose up -d
docker compose exec web python manage.py migrate
docker compose exec web pytest
docker compose exec web python manage.py check --deploy
```

## Tooling

- Lint: `ruff check .`
- Type checks: `mypy .`
- Tests: `pytest`
