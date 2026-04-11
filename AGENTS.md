# ERP Tracker — Codex Working Agreement

You are a senior full-stack engineer developing an automated, production-ready in-house ERP/Tracker system.

## Business Context & Client Vision
The core objective is to create a seamless, centralized ERP system to track factory production flow, calculate worker performance and overtime based on targets, monitor machinery health, and strictly manage inventory transfer between production stages. 

**CRITICAL RULE:** Data integrity is paramount. The system must prevent users from manipulating or changing backdated entries (a major pain point with their old Excel spreadsheets) to ensure accurate wastage and production tracking.

### Core Modules
1. **Raw Material Module:** Track initial inputs into the factory.
2. **Daily Production & Target Tracking:** Tracks daily output per person/section. Calculates standard daily targets versus achieved quantities.
3. **Section-to-Section Flow Tracker:** Tracks WIP. The verified output total of Section 1 MUST automatically become the input/opening balance for Section 2.
4. **Machinery Breakdown/Downtime:** Logging system for the factory floor to record machine downtime, duration, and reason.
5. **Automated Overtime Calculator:** Logic engine calculates overtime based on **piece-rate production**, not strictly hours (e.g., Target=100/8hrs. Actual=150 pieces -> Auto-calculate 4 hours overtime).
6. **Attendance & Daily Wage:** Tracks employee presence in specific sections on a given day.
7. **Store Requisition:** Request system where workers request additional materials, sending a notification/popup to Admin or Store Manager for approval.

### User Roles
- **Admin/Boss:** Has access to the high-level dashboard, view aggregated reports, track total factory wastage, and approve requisitions.
- **Supervisor/Data Entry (Factory Floor):** Enters daily production data, logs machine breakdowns, initiates requisitions. Must have an extremely user-friendly interface with pre-filled dropdowns.
- **Store Manager:** Receives and approves/denies store requisition requests.

### Data Variables & Tracking Constraints
- **Dropdowns:** Employee names (e.g., Ram Bahadur), Item names (e.g., "Bhutte Khadkulo 6 inch").
- **Validation Logic:** Strict enforcement. If Section 1 produces 260kg, Section 2 cannot claim 300kg input. Flag mismatches immediately.
- **Wastage:** Automatically calculated. (Input 400kg - Output 350kg = 50kg Wastage).

### Reporting & Dashboards
- **Daily High-Level Summary:** Total production of finished goods.
- **Employee History Report:** Day-by-day historical breakdown comparing target vs achieved output.
- **Section-Wise Aggregation:** Total sum of all individuals within a specific section.
- **Machinery Health Report:** Visual indicator (marked red) for offline machines.
- **Visual Charts:** Daily production trends and finished goods outputs.

## Non-negotiables
- Prioritize correctness, data integrity, auditability, and a simple UI.
- Do NOT remove or change requirements silently. If you must assume something, write it down in docs/ASSUMPTIONS.md.
- Every change must include: tests (unit/integration), migrations, and clear validation.
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
