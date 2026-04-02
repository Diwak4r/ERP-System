## 2026-03-23 - [Optimized ProductionEntryFormSet with bulk pre-fetching]
**Learning:** Django's `ModelChoiceField` in a bound form triggers a database query during validation (`to_python`) to verify the primary key exists; providing a pre-evaluated queryset or choices in `__init__` does not eliminate these individual validation queries. However, bulk-fetching custom business logic data (like `TargetRule`) and pre-evaluating choices for rendering still provide significant database query savings (N-1 queries saved per business logic lookup).
**Action:** When optimizing FormSets, focus on bulk-fetching business logic data and pre-evaluating choices for rendering, but be aware that individual validation queries for `ModelChoiceField` are harder to eliminate without overriding the field's validation logic.

## 2026-03-24 - [Optimized Production Entry Save with bulk_create]
**Learning:** Using `bulk_create` for batch saves in Django views reduces database round-trips from $O(N)$ to $O(1)$. However, it's critical to manually call any business logic (like `set_outcomes()`) that is normally handled in a `save()` method or signal, as `bulk_create` bypasses them.
**Action:** Always verify that all necessary model computations or side effects are manually executed before performing a `bulk_create` operation.
