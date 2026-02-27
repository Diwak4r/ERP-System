## 2026-02-27 - [N+1 Query Optimization in ProductionEntryFormSet]
**Learning:** Production entry validation triggered an N+1 query bottleneck by fetching `TargetRule` for each row individually. While Django's `ModelChoiceField` continues to perform individual existence checks, we can eliminate custom business logic N+1 queries by bulk-fetching data in the FormSet's `__init__`.
**Action:** Always pre-fetch validation data in a single query within `BaseFormSet.__init__` and share it with forms via `get_form_kwargs` to reduce database roundtrips.
