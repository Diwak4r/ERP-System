## 2026-03-23 - [Optimized ProductionEntryFormSet with bulk pre-fetching]
**Learning:** Django's `ModelChoiceField` in a bound form triggers a database query during validation (`to_python`) to verify the primary key exists; providing a pre-evaluated queryset or choices in `__init__` does not eliminate these individual validation queries. However, bulk-fetching custom business logic data (like `TargetRule`) and pre-evaluating choices for rendering still provide significant database query savings (N-1 queries saved per business logic lookup).
**Action:** When optimizing FormSets, focus on bulk-fetching business logic data and pre-evaluating choices for rendering, but be aware that individual validation queries for `ModelChoiceField` are harder to eliminate without overriding the field's validation logic.

## 2026-03-24 - [Optimized RBAC checks with role caching]
**Learning:** Redundant database queries during Role-Based Access Control (RBAC) checks (e.g., `user.groups.filter(name=role).exists()`) can be eliminated by caching the user's group names in a set on the user object instance for the duration of the request lifecycle.
**Action:** Use a cached attribute like `user._group_names_cache` to store group names after the first query, enabling O(1) in-memory lookups for subsequent role checks.
