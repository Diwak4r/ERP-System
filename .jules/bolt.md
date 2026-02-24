# Bolt's Performance Journal

## 2026-02-24 - Django FormSet N+1 and RBAC optimization
**Learning:** Django `ModelChoiceField` within a FormSet triggers a database query for each form during validation, even if the same QuerySet is provided to all forms (due to deepcopying). Additionally, hydration logic in `form.clean()` causes $O(N)$ queries. Caching group names on the `user` object is a simple but effective way to eliminate redundant RBAC queries within a request.
**Action:** Use `BaseFormSet.clean()` for bulk-fetching validation data. Prefer sharing QuerySets in `__init__` even if it only partially reduces queries, and consider in-memory caching for permissions.

## 2026-02-24 - Django Admin list view "auto-joins"
**Learning:** If `ModelAdmin.list_display` includes fields from related models used in `Meta.ordering`, Django might already perform INNER JOINs for those models, making explicit `list_select_related` less impactful than expected (though still good practice).
**Action:** Always verify query counts for Admin list views before assuming `list_select_related` is a necessary optimization.
