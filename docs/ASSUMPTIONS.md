# Assumptions

## Phase 5A — Store Requisition Workflow

- A `STORE` user must be mapped to exactly one active factory section through `Section.supervisors`. That section is treated as the requisition destination section.
- Requisition ledger impact is applied to `DailyLedger` using:
  - `item` from the requisition
  - `section` from the mapped store section
  - `date` as the requisition creation day (`requested_date`)

## Phase 6A — CSV Import + Safe Exports

- CSV import is intentionally create-only for master data (`Items`, `Workers`, `Machines`, `Sections`). Existing unique identifiers are treated as validation errors; no upsert/update is performed.
- Boolean import fields must be explicit (`true/false`, `yes/no`, `1/0`). Invalid boolean text fails that row and aborts the transaction.
