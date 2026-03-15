## 2025-03-15 - [Optimization of ProductionEntryFormSet]
**Learning:** Django's `ModelChoiceField` triggers an individual database query during validation (`to_python`) to verify the existence of the selected object, even if the `queryset` is pre-evaluated or `choices` are provided. However, custom business logic lookups (like fetching `TargetRule`) can be completely eliminated through bulk-fetching in the FormSet's `__init__`.
**Action:** Use `BaseFormSet` to bulk-fetch data required for custom `clean()` logic and pass it to forms via `get_form_kwargs`.

## 2025-03-15 - [Migration Field Syntax]
**Learning:** Using `migrations.ManyToManyField` inside a migration's `AddField` or `CreateModel` operation is incorrect and causes an `AttributeError`. Model field classes must be accessed via `models`.
**Action:** Always use `models.FieldType` for field definitions in migrations.
