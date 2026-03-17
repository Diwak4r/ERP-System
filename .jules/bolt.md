## 2024-05-22 - [FormSet N+1 Query Optimization]
**Learning:** Django FormSets with `ModelChoiceField` trigger a database query per form instance during rendering (to fetch choices) and during validation (to verify the selected ID). Additionally, custom logic in `clean()` that performs lookups (like `TargetRule`) can cause further N+1 issues.
**Action:** Pre-evaluate `choices` in the FormSet's `__init__` and pass them to each form to eliminate rendering queries. For validation lookups, bulk-fetch relevant data into a dictionary in the FormSet and inject it into forms via `get_form_kwargs`.
