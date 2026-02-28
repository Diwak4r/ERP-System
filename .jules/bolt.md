## 2025-02-14 - Optimize ProductionEntry Submission

**Learning:** The current production entry submission process triggers N+1 queries by fetching `TargetRule` objects for each form in the formset during validation and then saving each entry individually. Bulk-fetching validation data and using `bulk_create` can significantly reduce the query count.

**Action:** Implement a custom `BaseFormSet` to pre-fetch validation data and use `bulk_create` for saving.
