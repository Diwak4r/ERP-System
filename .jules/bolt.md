# Bolt's Journal - Critical Learnings Only

## 2026-02-20 - Optimizing FormSet validation with pre-fetching
**Learning:** Django FormSets that perform lookups in the form's `clean()` method suffer from N+1 query problems. Even when using `ModelChoiceField`, validation logic can trigger redundant queries for snapshots or rules.
**Action:** Subclass `BaseFormSet` and override `get_form_kwargs` to pass a shared cache (pre-fetched in the formset) to individual forms. This reduces N queries to 1. Note that parsing `self.data` directly in `BaseFormSet` is necessary for bound forms to identify which items to pre-fetch before individual form validation begins.
**Pattern:**
```python
class BaseMyFormSet(forms.BaseFormSet):
    def _prefetch_data(self):
        ids = [self.data.get(f"{self.prefix}-{i}-item") for i in range(self.total_form_count())]
        return MyModel.objects.filter(id__in=ids)

    def get_form_kwargs(self, index):
        kwargs = super().get_form_kwargs(index)
        if not hasattr(self, '_cache'): self._cache = self._prefetch_data()
        kwargs['cache'] = self._cache
        return kwargs
```
**Warning:** `ModelChoiceField` still hits the DB in `to_python` and `validate`. Pre-fetching for these fields requires custom field implementations or providing a pre-evaluated queryset which still doesn't stop the `to_python` query.
