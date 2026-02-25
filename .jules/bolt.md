# Bolt's Journal - Critical Performance Learnings

## 2026-02-25 - [FormSet N+1 Optimization]
**Learning:** Django FormSets naturally lead to N+1 query patterns during both hydration (fetching rules/targets) and saving (individual `.save()` calls). `ModelChoiceField` also triggers individual validation queries.
**Action:** Pre-fetch validation/lookup data into a dictionary in the view and pass it via `form_kwargs` to forms for O(1) lookups. Use `bulk_create` for saving.

## 2026-02-25 - [Redundant Role Checks]
**Learning:** Frequent permission checks (e.g. `user.groups.filter(...).exists()`) hit the database every time.
**Action:** Cache group names on the user object (e.g., `user._group_names_cache`) for the duration of the request.
