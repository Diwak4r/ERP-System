# ERP Tracker — Codex Working Agreement

You are a senior full-stack engineer developing an automated, production-ready in-house ERP/Tracker system.

## Business Context & Client Vision
The core objective is to create a seamless, centralized ERP system to track factory production flow, calculate worker performance, monitor machinery health, and strictly manage inventory transfer.

### 1. Strict Data Immutability (The "Anti-Excel" Rule)
- **The Core Pain Point:** In their current Excel sheets, workers alter historical data.
- **The Requirement:** The ERP must have strict data locking. Once a daily production log is submitted or a day is closed, the system must strictly prohibit users from editing backdated entries ("back date ja ke data change na kare"). Any corrections to past data require an Admin override.

### 2. Granular UI/UX & Interaction Expectations
- **Visual Cues:** The system must use automated visual alerts. If a worker fails their daily target or a machine experiences downtime, the system must automatically highlight that cell/row in red ("laal kar de").
- **Double-Click Drill-Downs:** Highly interactive dashboard. The Admin must be able to double-click a specific worker's name (e.g., Ram Bahadur) on the daily summary to instantly open a pop-up showing their day-by-day historical performance.
- **Strict Dropdown Architecture:** To prevent manual errors by floor supervisors, almost all inputs (employee names, item types, machine IDs) MUST use pre-populated dropdown lists, not text fields.

### 3. The "Hard Block" Inventory Gate
- **The Logic:** If Section 1 submits a verified output of 260kg, that exact number is hardcoded as Section 2's opening balance. If the supervisor in Section 2 attempts to claim they received 300kg, the system must actively block the entry and flag the discrepancy to catch phantom production or material theft.

### 4. Real-Time Requisition Pop-Ups
- **The Logic:** When a factory floor supervisor requests materials, a real-time pop-up notification/alert must appear on the Admin or Store Manager's screen allowing them to review and approve the request immediately.

### 5. Piece-to-Time Overtime Formula
- **The Logic:** Overtime is calculated by a proportional piece-rate formula converted into hours. Example: If the 8-hour target is 100 pieces and the worker makes 150 pieces, the system MUST automatically recognize the 50 extra pieces and convert that exactly into 4 hours of overtime. Needs a configurable background formula defining "difficulty" per item.

### 6. Master Data Migration (Tally/Excel)
- **The Logic:** The client relies on Tally and Excel currently. The system requires a backend capability to import the master list of items and metrics directly via CSV/Excel, ensuring the new ERP dropdown menus perfectly match their current accounting terminology.

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
- Python: Django, HTMX, ruff, mypy, pytest.
- Django best practices: settings split, strict CSRF, secure cookies, timezone-aware datetimes.

## Delivery expectations for each task
- Provide a short "What changed" summary.
- Provide exact run commands to verify.
- If something fails, fix it (do not stop with failing tests).
