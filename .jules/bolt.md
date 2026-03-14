## 2025-05-15 - [Avoid N+1 with reversed(queryset)]
**Learning:** Calling `reversed()` on a Django QuerySet that doesn't implement `__reversed__` causes Python to fall back to `__getitem__` with `OFFSET`, leading to one database query per item (N queries).
**Action:** Always convert a QuerySet to a list using `list(queryset)` before calling `reversed()` if you need to iterate in reverse order efficiently.

## 2025-05-15 - [ModelChoiceField validation queries]
**Learning:** Setting `.choices` on a `ModelChoiceField` optimizes template rendering but does not prevent the field from performing a `.get()` query during validation.
**Action:** Provide a pre-evaluated queryset to the field's `queryset` attribute to ensure that validation lookups happen against an in-memory cache if possible, or at least avoid redundant filtering.
