## 2025-05-22 - [Optimizing Django FormSets N+1]
**Learning:** In Django `ModelForm` inside a `FormSet`, providing pre-evaluated `choices` to `ModelChoiceField` prevents queries during template rendering, but Django's `to_python` validation still triggers individual existence queries for each bound field. However, custom business logic (like `TargetRule` hydration) can be fully optimized by pre-fetching into a dictionary.
**Action:** Use a custom `BaseFormSet` to bulk-fetch shared data in `__init__` and inject it into form instances via `get_form_kwargs`.
