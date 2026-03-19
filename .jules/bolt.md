## 2025-03-19 - Django FormSet N+1 Optimization
**Learning:** Django `ModelChoiceField` triggers individual database queries during validation (`to_python`) even if the queryset is pre-evaluated or choices are manually set. However, business logic lookups (like fetching `TargetRule` for each row) can be completely optimized by bulk-fetching in the FormSet's `__init__` and passing a cache to each form.
**Action:** Use a custom `BaseFormSet` to bulk-fetch data and inject it into forms via `get_form_kwargs` to eliminate non-validation N+1 queries.

## 2025-03-19 - Improper QuerySet Reversal
**Learning:** Calling `reversed()` on a Django QuerySet that doesn't implement `__reversed__` (most don't) results in N database queries because it falls back to `__getitem__` with negative offsets, which Django translates to `OFFSET` queries.
**Action:** Always convert a QuerySet to a list using `list(queryset)` before calling `reversed()` to ensure only one query is executed.
