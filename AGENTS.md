# ERP Tracker — Codex Working Agreement

You are a senior full-stack engineer. Build a production-ready in-house ERP/Tracker system.

## Non-negotiables

- Prioritize correctness, data integrity, auditability, and a simple UI.
- Do NOT remove or change requirements silently. If you must assume something, write it down in docs/ASSUMPTIONS.md.
- Every change must include:
  - tests (unit/integration)
  - database migrations (when models change)
  - clear error handling and validation
- Always run verification commands before finishing a task:
  - `docker compose build`
  - `docker compose up -d`
  - `docker compose exec web python manage.py migrate`
  - `docker compose exec web pytest`
  - `docker compose exec web python manage.py check --deploy`
- Keep secrets out of git. Use `.env` + env vars only.
- Use PostgreSQL (not sqlite) for anything production-like.
- Enforce RBAC and "no backdated edits" with audit logs.

## Code style

- Python: ruff, mypy, pytest.
- Django best practices: settings split, strict CSRF, secure cookies, timezone-aware datetimes.

## Delivery expectations for each task

- Provide a short "What changed" summary.
- Provide exact run commands to verify.
- If something fails, fix it (do not stop with failing tests).

## Product requirements summary

- Roles: Admin, Supervisor (data entry), Store (requisition), Viewer.
- Master data: Sections, Machines, Workers, Items, Process flow (section-to-section).
- Phase 1 core: Worker production entry (target vs actual), overtime calc, daily aggregates, red flags if target missed.
- "Tracker" rule: next section cannot output more than available input (opening balance + received from previous section - waste).
- No backdated changes by non-admin; admin overrides must be logged.
- Secondary modules: Attendance, Machine downtime, Store requisition, CSV import.
