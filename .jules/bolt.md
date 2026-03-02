## 2025-05-15 - Optimizing Django FormSet Batch Processing

**Learning:** Django FormSets can cause massive N+1 query problems if validation or hydration logic performs database lookups for each form. While pre-evaluating ChoiceField querysets reduces queries for rendering, it doesn't eliminate individual existence checks during form validation. However, pre-fetching business logic data (like `TargetRule`) into a local cache within the FormSet and passing it to forms via `get_form_kwargs` provides significant savings.

**Action:** Use a custom `BaseFormSet` to bulk-fetch all data required for form validation/hydration in its `__init__` method, and inject it into individual forms via `get_form_kwargs`.

## 2025-05-15 - Bulk Save with Logic

**Learning:** `ProductionEntry.objects.bulk_create()` is significantly faster than individual `.save()` calls but it bypasses the model's `save()` method and signals.

**Action:** Always call any required derivation logic (like `set_outcomes()`) manually on each instance before passing the list to `bulk_create`.
