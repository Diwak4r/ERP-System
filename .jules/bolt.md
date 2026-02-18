## 2026-02-18 - Incorrect ManyToManyField in migrations
**Learning:** Manual edits to migrations or incorrect generation can lead to `AttributeError: module 'django.db.migrations' has no attribute 'ManyToManyField'`. Always use `models.ManyToManyField` for field types in migrations.
**Action:** Verify migration field types use `models` and not `migrations` (which only contains operation classes).

## 2026-02-18 - N+1 in FormSet Processing
**Learning:** Django FormSets can easily lead to N+1 queries if each form's `clean` method performs database lookups or if the view saves forms individually.
**Action:** Always consider bulk fetching data needed for validation in the FormSet's `clean` method and use `bulk_create` for saving.
