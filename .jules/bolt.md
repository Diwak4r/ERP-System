## 2025-05-15 - [FormSet N+1 Optimization]
**Learning:** Django FormSets can cause massive N+1 query problems if each form independently looks up validation data or related models in its `__init__` or `clean` methods. Sharing data from the `BaseFormSet` to individual forms using `get_form_kwargs` and pre-evaluated querysets can significantly reduce database load.
**Action:** Always check for N+1 patterns in FormSets and use a custom `BaseFormSet` to bulk-fetch and cache data for all forms in the set.

## 2025-05-15 - [Migration Syntax Error]
**Learning:** Using `migrations.ManyToManyField` (or other field types) directly inside an `AddField` operation in a migration file is invalid. Django expects model field types from the `models` module, even within migrations.
**Action:** Always use `models.<FieldType>` for field definitions in migrations.
