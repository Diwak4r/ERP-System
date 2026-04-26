# Assumptions

## Phase 5A — Store Requisition Workflow

- A `STORE` user must be mapped to exactly one active factory section through `Section.supervisors`. That section is treated as the requisition destination section.
- Requisition ledger impact is applied to `DailyLedger` using:
  - `item` from the requisition
  - `section` from the mapped store section
  - `date` as the requisition creation day (`requested_date`)
