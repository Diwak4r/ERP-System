# Bolt's Performance Journal

## 2025-05-22 - [Initial Entry]
**Learning:** To optimize Django Admin list view performance and prevent N+1 queries, always include ForeignKey fields used in `list_display` within the `list_select_related` attribute of the `ModelAdmin` class.
**Action:** Review all `admin.py` files for missing `list_select_related`.

## 2025-05-22 - [FormSet N+1 Queries]
**Learning:** Django FormSets can cause N+1 queries when each form performs a database lookup in its `clean()` method. Bulk-fetching validation data in the FormSet's `__init__` or `clean()` method and passing it to forms can significantly reduce database load.
**Action:** Use a custom `BaseFormSet` to pre-fetch data and pass it to forms via `get_form_kwargs`.
