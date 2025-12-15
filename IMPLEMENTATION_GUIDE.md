# ERP System Implementation Guide

## Overview

This document outlines the complete implementation roadmap for the production-grade in-house ERP/Tracker system. The system follows a phase-by-phase approach using Codex-assisted development, with each phase building upon the previous one.

## Technology Stack

- **Backend:** Django + Django REST Framework
- **Database:** PostgreSQL
- **Frontend:** Django templates + HTMX (dynamic forms) + Chart.js (reports)
- **Deployment:** Docker + Gunicorn + Nginx
- **Quality Assurance:** pytest, ruff, mypy, GitHub Actions
- **Infrastructure:** Docker Compose (local/dev), production deployment docs

## Phase-by-Phase Implementation Roadmap

### Phase 0: Foundation (Repository + DevOps + Auth + Master Data)

Duration: 1-2 weeks | Priority: CRITICAL

#### Prompt 0A: AGENTS.md (Persistent Instructions) ✅ COMPLETED
- **Status:** ✅ Done
- **Deliverable:** AGENTS.md file with working agreement and non-negotiables
- **Repository:** Yes, file exists at repo root

#### Prompt 0B: Docker Bootstrap + Django Setup
- **Status:** ⏳ Pending
- **Deliverables:**
  - docker-compose.yml with web (Django), db (PostgreSQL), optional pgadmin
  - Django project structure: src/config/settings/ (base.py, dev.py, prod.py)
  - .env.example and dotenv loading
  - Static files + templates configuration
  - Linting setup: ruff, mypy, pytest configs
  - GitHub Actions CI workflow
  - Basic home page + /healthz endpoint
  - README.md with setup instructions
- **Verification Commands:**
  ```bash
  docker compose build
  docker compose up -d
  docker compose exec web python manage.py migrate
  docker compose exec web pytest
  curl http://localhost:8000/healthz
  ```

#### Prompt 0C: Authentication + RBAC
- **Status:** ⏳ Pending
- **Deliverables:**
  - Django auth (sessions)
  - Groups (ADMIN, SUPERVISOR, STORE, VIEWER)
  - Group seed management command
  - Login/logout pages
  - Role-based navbar
  - Permission decorators/mixins
  - Tests for permission boundaries

#### Prompt 0D: Master Data Models
- **Status:** ⏳ Pending
- **Deliverables:**
  - Section model (name, code, is_active)
  - Worker model (name, employee_code, is_daily_wage, is_active)
  - Item model (name, sku, unit: KG/PCS/OTHER, is_active)
  - Machine model (section FK, name, machine_code, is_active)
  - TargetRule model (section, item, target_qty, shift_hours, date range)
  - ProcessFlowEdge model (item, from_section, to_section, lead_days)
  - Django admin registration
  - Migrations and constraints
  - Sample seed data/fixtures
  - Tests for unique constraints

### Phase 1: Core ERP MVP (Production Tracker + Aggregation + No Backdate Edits)

Duration: 2-3 weeks | Priority: CRITICAL

#### Prompt 1A: Production Entry Module (Supervisor Form UI)
- **Status:** ⏳ Pending
- **Core Feature:** Worker production entry with auto-computed targets and overtime
- **Deliverables:**
  - ProductionEntry model with fields:
    - entry_date, section, worker, item
    - target_qty, actual_qty (snapshots)
    - shift_hours, overtime_hours (computed)
    - target_met (boolean), created_by, timestamps
  - HTMX form UI (add/remove rows without reload)
  - Auto-fill targets from TargetRule
  - Overtime calculation: ((actual/target) - 1) * shift_hours
  - Permission checks (Supervisor per section only)
  - Immutability rules (handled in 1C)
  - Tests for overtime calc, snapshots, permissions

#### Prompt 1B: Aggregated Reports
- **Status:** ⏳ Pending
- **Reports:**
  1. Daily Section Summary
     - Total actual per item
     - Total actual per worker
     - Worker count
     - Target hit status (red/green highlight)
  2. Item Aggregate
     - Item-wise totals vs targets
     - Target hit rate %
  3. Worker History Drilldown
     - Per-day performance
     - Daily targets vs actuals
     - Charts (optional: Chart.js)
- **Deliverables:**
  - Optimized Django ORM aggregation queries
  - Report views at /production/reports/*
  - Tests with factory data

#### Prompt 1C: No-Backdate Edits + Audit Logging (MANDATORY)
- **Status:** ⏳ Pending
- **Core Rules:**
  - Supervisors cannot edit/delete entries after cutoff
  - DayLock: section + lock_date with is_locked boolean
  - Admin can unlock with required reason
  - All admin edits create AuditEvent records
- **Deliverables:**
  - DayLock model (section, lock_date, locked_at, locked_by, is_locked)
  - AuditEvent model (actor, action, model_name, object_id, before/after JSON, reason, timestamp, ip)
  - Middleware to capture IP
  - Admin UI for day lock/unlock
  - Tests for edit prevention

### Phase 2: Material Flow "Tracker" + Wastage

Duration: 2 weeks | Priority: CRITICAL

#### Prompt 2A: Inventory/Process Ledger
- **Status:** ⏳ Pending
- **Core Concept:** 
  - Daily balances per (date, section, item)
  - opening_balance + received_from_prev + manual_received - output - waste = closing_balance
  - Flags anomalies: output > available
- **Deliverables:**
  - DailyLedger model
  - Automatic recomputation post-ProductionEntry
  - ProcessFlowEdge tracking (previous section output → next section input)
  - Anomaly flagging
  - Ledger page UI
  - Tests for flow validation

#### Prompt 2B: Wastage Capture + Reporting
- **Status:** ⏳ Pending
- **Deliverables:**
  - Waste entry form (supervisor, locked by DayLock)
  - Waste % = waste_qty / total_available
  - Wastage reports per section

### Phase 3: Attendance Module

Duration: 1 week | Priority: SECONDARY

#### Prompt 3A: Attendance Entry + Report
- **Status:** ⏳ Pending
- **Deliverables:**
  - AttendanceSheet + AttendanceLine models
  - Daily supervisor entry (multi-select workers)
  - Attendance reports (per section per day)
  - Aggregate headcount tracking
  - DayLock rules apply

### Phase 4: Machine Downtime Module

Duration: 1 week | Priority: SECONDARY

#### Prompt 4A: Downtime Logging + Red Machine Alert
- **Status:** ⏳ Pending
- **Deliverables:**
  - MachineDowntime model (machine, downtime_date, start/end times, reason, duration_minutes)
  - Supervisor logging
  - Daily downtime list + dashboard alert
  - Overlap prevention
  - DayLock rules apply

### Phase 5: Store Requisition Module

Duration: 1 week | Priority: SECONDARY

#### Prompt 5A: Requisition Workflow + Approval
- **Status:** ⏳ Pending
- **Deliverables:**
  - Requisition model (item, qty, note, status: PENDING/APPROVED/REJECTED)
  - Store user can request
  - Admin approval workflow
  - Status history
  - Notifications

### Phase 6: Production-Grade Hardening

Duration: 1-2 weeks | Priority: CRITICAL

#### Prompt 6A: CSV Import + Safe Exports
- **Status:** ⏳ Pending
- **Deliverables:**
  - Admin import page (Items, Workers, Machines, Sections)
  - Transaction-based import (all-or-nothing)
  - Error reporting
  - Export CSV endpoints

#### Prompt 6B: Security + Performance + Monitoring + Deployment
- **Status:** ⏳ Pending
- **Deliverables:**
  - Django security settings (SECURE_SSL_REDIRECT, secure cookies, etc.)
  - `manage.py check --deploy` verification
  - Rate limiting (login)
  - Database indexes for report queries
  - Pagination for large tables
  - Structured logging
  - Sentry/error tracking setup (optional)
  - Production docker-compose.yml or K8s docs
  - Gunicorn + Nginx config
  - Database backup/restore docs
  - Deployment playbook
  - End-to-end smoke tests
  - CI gates (ruff, mypy, pytest, manage.py check --deploy)

## Key Requirements (Non-Negotiables)

✅ **Data Integrity:**
- PostgreSQL (production)
- Database constraints
- Migrations for all schema changes
- Tests with factory data

✅ **Security:**
- No secrets in git (.env only)
- RBAC enforced at views and model level
- Audit logs for admin actions
- CSRF protection
- Secure cookies

✅ **Auditability:**
- DayLock prevents backdated edits
- AuditEvent logs all admin overrides
- Clear error messages
- Validation on all inputs

✅ **UI/UX:**
- Simple, intuitive interfaces
- Red/green highlight for target status
- Dropdown lists for master data
- Quick add functionality (optional)
- Mobile-friendly forms

✅ **Code Quality:**
- ruff (linting)
- mypy (type checking)
- pytest (unit + integration tests)
- GitHub Actions CI
- Comprehensive docstrings

## Development Workflow

1. **Environment Setup**
   ```bash
   git clone <repo>
   cd ERP-System
   docker compose up -d
   docker compose exec web python manage.py migrate
   ```

2. **Per-Phase Workflow**
   - Copy Prompt from this document
   - Use ChatGPT/Codex to generate code
   - Implement generated files
   - Run verification commands
   - Run tests
   - Commit with clear messages

3. **Testing Before Commit**
   ```bash
   docker compose exec web ruff check .
   docker compose exec web mypy .
   docker compose exec web pytest
   docker compose exec web python manage.py check --deploy
   ```

4. **Deployment**
   - Tag release
   - Deploy to staging
   - Run smoke tests
   - Deploy to production
   - Monitor logs

## Success Criteria

- ✅ All prompts executed in order
- ✅ All tests passing (100% pass rate)
- ✅ CI gates green (ruff, mypy, pytest, deploy check)
- ✅ No secrets in git
- ✅ Production-grade deployment docs
- ✅ Admin can view all data with audit trail
- ✅ Supervisors cannot backdated edit
- ✅ Material flow tracker validates constraints
- ✅ All secondary modules functional
- ✅ System runs in Docker without errors

## References

- AGENTS.md - Codex working agreement
- ChatGPT conversation - Complete prompt pack and requirements
- README.md - Setup instructions
- Django documentation
- PostgreSQL documentation
- Docker documentation
