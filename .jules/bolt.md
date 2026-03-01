## 2026-03-01 - [Optimized FormSet N+1 queries and Permission checks]
**Learning:** In Django FormSets, fetching validation data like `TargetRule` for each form in `clean()` creates an N+1 query bottleneck. Also, repeated permission checks using `user.groups.filter()` hit the database every time.
**Action:** Pre-fetch validation data into a dictionary in the view and pass it to the FormSet. Use `BaseFormSet.get_form_kwargs()` to distribute the cache to each form. For roles, cache group names on the user instance (e.g., `user._group_names_cache`).
>>>>>>> REPLACE
