## 2026-03-23 - [Optimized ProductionEntryFormSet with bulk pre-fetching]
**Learning:** Django's `ModelChoiceField` in a bound form triggers a database query during validation (`to_python`) to verify the primary key exists; providing a pre-evaluated queryset or choices in `__init__` does not eliminate these individual validation queries. However, bulk-fetching custom business logic data (like `TargetRule`) and pre-evaluating choices for rendering still provide significant database query savings (N-1 queries saved per business logic lookup).
**Action:** When optimizing FormSets, focus on bulk-fetching business logic data and pre-evaluating choices for rendering, but be aware that individual validation queries for `ModelChoiceField` are harder to eliminate without overriding the field's validation logic.

## 2026-03-31 - [Optimized Admin List Views with list_select_related]
**Learning:** Django Admin list views for models with foreign keys trigger N+1 queries by default if those keys are in `list_display`. This is a silent performance killer that scales linearly with the number of rows displayed.
**Action:** Always use `list_select_related` in `admin.py` for any ForeignKey fields included in `list_display` or `list_filter` to ensure constant-time query counts.
