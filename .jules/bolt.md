## 2026-03-04 - [Optimizing FormSet Validation Queries]
**Learning:** Django's `ModelChoiceField` triggers individual existence checks in the database during `to_python` and `validate`, even if the queryset is pre-evaluated. This creates an N+1 query problem during formset validation.
**Action:** Use a custom `CachedModelChoiceField` that accepts a dictionary cache (id -> object) to resolve and validate instances without hitting the database.

## 2026-03-04 - [Pre-populating QuerySet Result Cache]
**Learning:** To prevent the HTML `select` widget from re-executing queries for every form in a formset, the queryset's internal `_result_cache` should be manually populated with pre-fetched data.
**Action:** In the Form's `__init__`, set `self.fields[field_name].queryset._result_cache = list(cache.values())` and `_prefetch_done = True`.
