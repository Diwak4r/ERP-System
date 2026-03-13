## 2026-03-13 - [Django FormSet Optimization Bottleneck]
**Learning:** In Django, `ModelChoiceField` within a bound form triggers individual database queries during `to_python` validation to ensure the primary key exists, even if `choices` are pre-evaluated and passed to the field. This limits the reduction of O(N) queries for validation.
**Action:** Prioritize pre-fetching custom business logic data (like `TargetRule` lookups) which can be fully optimized to O(1) in the FormSet, while accepting that field validation may still incur O(N) queries without more invasive overrides.
