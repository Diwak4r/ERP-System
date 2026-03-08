## 2025-01-24 - Bulk-fetching in Django FormSets
**Learning:** Django's ModelChoiceField triggers individual database queries during validation (to_python) even if the queryset is pre-evaluated. However, custom business logic (like TargetRule lookups) that occurs during form hydration/cleaning can be fully optimized by bulk-fetching data in the FormSet's __init__ and passing it to forms via form_kwargs.
**Action:** Use a BaseFormSet to pre-fetch related metadata and inject it into individual forms to eliminate N-1 query patterns for non-field lookups.
