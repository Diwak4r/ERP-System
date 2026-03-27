## 2026-03-23 - [Optimized ProductionEntryFormSet with bulk pre-fetching]
**Learning:** Django's `ModelChoiceField` in a bound form triggers a database query during validation (`to_python`) to verify the primary key exists; providing a pre-evaluated queryset or choices in `__init__` does not eliminate these individual validation queries. However, bulk-fetching custom business logic data (like `TargetRule`) and pre-evaluating choices for rendering still provide significant database query savings (N-1 queries saved per business logic lookup).
**Action:** When optimizing FormSets, focus on bulk-fetching business logic data and pre-evaluating choices for rendering, but be aware that individual validation queries for `ModelChoiceField` are harder to eliminate without overriding the field's validation logic.

## 2026-03-24 - [Cached RBAC group checks on User instance]
**Learning:** Redundant database queries for user groups during a single request can be eliminated by caching the group names set on the `User` object instance. This is particularly effective when multiple role-based permission checks are performed in a single view or across multiple components (e.g., HTMX rows).
**Action:** Use a simple `hasattr` check and `set(user.groups.values_list("name", flat=True))` to cache roles for the duration of the user object's lifecycle.
