## 2025-05-15 - Django FormSet N+1 Query Pattern
**Learning:** In Django FormSets, performing database lookups within a form's `clean()` method results in N queries (one per form). This can be optimized by bulk-fetching the required data once and caching it on the formset instance.
**Action:** Override `get_form_kwargs` in a custom `BaseFormSet` to fetch and cache shared validation data, then pass it to individual form instances via `kwargs`.

## 2025-05-15 - Django Migration Syntax for ManyToManyField
**Learning:** In Django migration files, `models.ManyToManyField` must be used for field instantiation. Using `migrations.ManyToManyField` inside a `migrations.AddField` operation is invalid and causes an `AttributeError`.
**Action:** Always use `models.<FieldType>` for field definitions within `migrations.AddField` or `migrations.CreateModel` operations.
